"""Shared by bin/import-fuguepack and bin/new-template (Python 3 standard library only).

Makes a template folder from a workflow: copies the pictures its nodes load into `<id>/inputs/`, points the
nodes at `inputs/<name>`, writes a template.json skeleton and lists what is still missing. It never writes
outside the new folder and never overwrites anything.

A package from an issue is written by a stranger. So: no picture is ever decoded or converted here (a preview or sample is
copied only when its first bytes say PNG, JPEG or WebP, and the like), every string that came from the package is
escaped before it is printed, and no local path is left in what is written.
"""
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PREVIEWS = ("preview.webp", "preview.png", "preview.jpg")
MAX_PREVIEW = 300 * 1024  # as bin/check
MAX_INPUT = 600 * 1024  # as bin/check
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")
FILE_INPUTS = ("file", "mask")  # node inputs that name a file: Load Image's picture and its painted mask
# A path on somebody's machine: absolute, `~`, a Windows drive or a share. bin/check refuses these in a workflow.
LOCAL_PATH = re.compile(r"^(/[^\s/]|~(/|\\|$)|[A-Za-z]:[\\/]|\\\\)")
# What a terminal or a reader can be fooled by: C0 and C1 controls, DEL, bidi marks and overrides, line and paragraph separators.
DANGEROUS = re.compile("[\x00-\x1f\x7f-\x9f؜‎‏  ‪-‮⁦-⁩﻿]")


def safe(value):
    """A string that came from a package, made safe to print: each dangerous character becomes \\xNN or \\uNNNN."""
    return DANGEROUS.sub(lambda m: f"\\x{ord(m.group()):02x}" if ord(m.group()) < 256 else f"\\u{ord(m.group()):04x}", str(value))


def say(message=""):
    print(message)


def die(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def dump_json(value, path):
    """JSON with the dangerous characters escaped, so a bidi override or a C1 control never lands raw in a published file."""
    text = json.dumps(value, indent=2, ensure_ascii=False)
    text = DANGEROUS.sub(lambda m: f"\\u{ord(m.group()):04x}", text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n")


def categories():
    with open(os.path.join(ROOT, "categories.json"), encoding="utf-8") as f:
        return [c["id"] for c in json.load(f)["categories"]]


def check_id(template_id):
    if not ID_RE.match(template_id):
        die(f"{safe(template_id)!r} is not a good id: use lowercase letters, digits and dashes (for example my-style-transfer).")
    folder = os.path.join(ROOT, template_id)
    if os.path.lexists(folder):
        die(f"{template_id}/ already exists. Pick another id, or remove the folder first.")
    return folder


def check_category(category):
    if category is not None and category not in categories():
        die(f"category {safe(category)!r} is not one of: {', '.join(categories())}")


# What a file's first bytes say it is. Nothing here decodes a file.
def media_kind(path):
    """'image', 'audio' or 'video' by magic bytes (PNG, JPEG, WebP; MP3, WAV, FLAC, Ogg; MP4/MOV, WebM/MKV, AVI), else None."""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return None
    if head.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")) or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
        return "image"
    if head.startswith((b"ID3", b"fLaC", b"OggS")) or (head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3")) or (head[:4] == b"RIFF" and head[8:12] == b"WAVE"):
        return "audio"
    if head[4:8] == b"ftyp" or head.startswith(b"\x1a\x45\xdf\xa3") or (head[:4] == b"RIFF" and head[8:12] == b"AVI "):
        return "video"
    return None


def preview_ext(path):
    """png, jpg or webp by magic bytes, else None."""
    with open(path, "rb") as f:
        head = f.read(16)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


LOADS = {"fugue/load-image": "image", "fugue/load-audio": "audio", "fugue/load-video": "video"}


def nodes_of(workflow):
    """Every node dict of the graph and of the groups the workflow holds."""
    scopes = []
    graph = workflow.get("graph")
    if isinstance(graph, dict) and isinstance(graph.get("nodes"), dict):
        scopes.append(graph["nodes"])
    groups = workflow.get("groups")
    if isinstance(groups, dict):
        scopes += [g["nodes"] for g in groups.values() if isinstance(g, dict) and isinstance(g.get("nodes"), dict)]
    for scope in scopes:
        for node in scope.values():
            if isinstance(node, dict):
                yield node


def gather_inputs(workflow, folder, find):
    """Copy the files that load nodes name into folder/inputs/ and point the nodes at `inputs/<name>`.

    `find(value)` returns the path of the file a node names, or None when it is not there. Only a file whose
    first bytes say the media kind the node takes is copied. A file two nodes name is copied once.
    Returns (notes, missing): lines for the report.
    """
    notes, missing = [], []
    done = {}  # real source path -> name in inputs/
    used = set()  # case-folded names taken
    for node in nodes_of(workflow):
        inputs = node.get("inputs")
        kind = LOADS.get(node.get("type")) if isinstance(node.get("type"), str) else None
        if not isinstance(inputs, dict) or not kind:
            continue
        for key in FILE_INPUTS:
            value = inputs.get(key)
            if not isinstance(value, str) or not value:
                continue
            wanted = "image" if key == "mask" else kind
            source = find(value)
            if source is None:
                missing.append(f"{safe(value)} (a {safe(node.get('type'))} node names it, and the file was not found)")
                continue
            real = os.path.realpath(source)
            if real not in done:
                if media_kind(real) != wanted:
                    missing.append(f"{safe(value)} is not a {wanted} file by its first bytes: not copied")
                    continue
                name = SAFE_NAME.sub("_", os.path.basename(value)) or "input"
                stem, ext = os.path.splitext(name)
                n = 1
                while name.casefold() in used:
                    n += 1
                    name = f"{stem}-{n}{ext}"
                used.add(name.casefold())
                os.makedirs(os.path.join(folder, "inputs"), exist_ok=True)
                shutil.copyfile(real, os.path.join(folder, "inputs", name))
                done[real] = name
                size = os.path.getsize(real)
                notes.append(f"{safe(value)} -> inputs/{name}" + (f" ({size // 1024} KB: samples stay under {MAX_INPUT // 1024} KB, make it smaller)" if size > MAX_INPUT else ""))
            inputs[key] = f"inputs/{done[real]}"
    return notes, missing


def strip_local_paths(value, found):
    """Reduce every string that is a path on someone's machine to its bare name, in place (lists and dicts), noting each in `found`."""
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, str) and LOCAL_PATH.match(v):
                value[k] = re.split(r"[\\/]", v.rstrip("\\/"))[-1] or "TODO"
                found.append(value[k])
            else:
                strip_local_paths(v, found)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            if isinstance(v, str) and LOCAL_PATH.match(v):
                value[i] = re.split(r"[\\/]", v.rstrip("\\/"))[-1] or "TODO"
                found.append(value[i])
            else:
                strip_local_paths(v, found)


def loose_files(workflow):
    """Load-node file inputs that are still not `inputs/<name>`."""
    out = []
    for node in nodes_of(workflow):
        inputs = node.get("inputs")
        if isinstance(inputs, dict) and node.get("type") in LOADS:
            for key in FILE_INPUTS:
                v = inputs.get(key)
                if isinstance(v, str) and v and not v.startswith("inputs/"):
                    out.append(v)
    return out


def finish_paths(workflow):
    """No local path stays in the published workflow. Returns report lines."""
    found = []
    strip_local_paths(workflow, found)
    lines = [f"a local path was cut to its bare name {safe(n)!r}: put the file in inputs/ and point the node at inputs/<name>, or clear it" for n in found]
    lines += [f"{safe(v)}: a file a node names that is not in inputs/ yet" for v in loose_files(workflow)]
    return lines


def dicts(value):
    return [m for m in value if isinstance(m, dict)] if isinstance(value, list) else []


def handles(value, out):
    if isinstance(value, dict):
        if "resource" in value and isinstance(value.get("hash"), str):
            out[value["hash"]] = value
        for item in value.values():
            handles(item, out)
    elif isinstance(value, list):
        for item in value:
            handles(item, out)


def write_template(folder, workflow, title, description, category, about=None):
    """workflow.fugue and a template.json skeleton. TODO marks what bin/check refuses until it is filled in."""
    dump_json(workflow, os.path.join(folder, "workflow.fugue"))
    skeleton = {
        "title": title,
        "description": description,
        "category": category or "TODO: one of " + ", ".join(categories()),
        "tags": [],
    }
    if isinstance(workflow.get("app"), dict):
        skeleton["app"] = True  # Fugue lists the workflow as an app only when template.json says so (its title, summary and kind come from the block)
    skeleton.update(about or {})
    dump_json(skeleton, os.path.join(folder, "template.json"))


def text_of(value, default):
    return value.strip() if isinstance(value, str) and value.strip() else default


def make_preview(folder, picture):
    """Copy `picture` as the preview when its first bytes say PNG, JPEG or WebP and it is at most 300 KB.
    Nothing is decoded or converted. Returns a line for the report, or None when the preview is in place."""
    ext = preview_ext(picture)
    size = os.path.getsize(picture)
    if ext and size <= MAX_PREVIEW:
        shutil.copyfile(picture, os.path.join(folder, f"preview.{ext}"))
        return None
    why = "it is not a PNG, JPEG or WebP picture" if not ext else f"it is {size // 1024} KB (at most {MAX_PREVIEW // 1024} KB)"
    return (f"preview: the package's picture was not used ({why}). Make one from the template's own result, at most {MAX_PREVIEW // 1024} KB, about 768 px wide: "
            "cwebp -resize 768 0 -q 80 result.png -o preview.webp (libwebp). Never convert a stranger's file with ImageMagick")


def todo(folder, extra=()):
    """What bin/check would still complain about, plus the notes of this run."""
    items = list(extra)
    try:
        with open(os.path.join(folder, "template.json"), encoding="utf-8") as f:
            about = json.load(f)
        for key in ("title", "description", "category"):
            if "TODO" in str(about.get(key, "")):
                items.append(f"template.json: write the {key}" + (f" (one of {', '.join(categories())})" if key == "category" else ""))
    except (OSError, ValueError, AttributeError):
        items.append("template.json is missing or unreadable")
    if not any(os.path.isfile(os.path.join(folder, p)) for p in PREVIEWS) and not any("preview" in i for i in items):
        items.append("preview.webp: a picture of what it makes, about 768 px wide, at most 300 KB")
    try:
        with open(os.path.join(folder, "workflow.fugue"), encoding="utf-8") as f:
            flow = json.load(f)
        flow.get("graph")
    except (OSError, ValueError, AttributeError):
        return items if any(i.startswith("workflow.fugue") for i in items) else items + ["workflow.fugue is missing or unreadable"]
    used = {}
    handles(flow.get("graph", {}), used)
    handles(flow.get("groups", {}), used)
    requires = flow.get("requires") if isinstance(flow.get("requires"), dict) else {}
    recorded = {m["hash"]: m for m in dicts(requires.get("models")) if isinstance(m.get("hash"), str)}
    for digest, handle in sorted(used.items()):
        entry = recorded.get(digest, {})
        label = safe(handle.get("name", digest))
        if not entry.get("source") or not isinstance(entry.get("size"), int):
            items.append(f"requires.models: {label} needs a source (an https link to the file) and a size (its bytes); see CONTRIBUTING.md, Models")
    return items


def report(template_id, items):
    print(f"\nMade {template_id}/")
    if items:
        print("Still to do:")
        for item in items:
            print(f"  - {item}")
    print("Then run bin/check-all, and see CONTRIBUTING.md.")
