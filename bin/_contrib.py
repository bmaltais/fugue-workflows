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
import struct
import sys
import unicodedata
import zlib

ROOT = os.environ.get("FUGUE_TEMPLATES_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the env var is for bin/test-import
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PREVIEWS = ("preview.webp", "preview.png", "preview.jpg")
MAX_PREVIEW = 300 * 1024  # as bin/check
MAX_INPUT = 600 * 1024  # as bin/check
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")
FILE_INPUTS = ("file", "mask")  # node inputs that name a file: Load Image's picture and its painted mask
# A path on somebody's machine: absolute (also //host), `~`, a Windows drive or share, file:. Refused where a node names a file.
LOCAL_PATH = re.compile(r"^(/|~(/|\\|$)|[A-Za-z]:[\\/]|\\\\|file:)", re.IGNORECASE)
PATH_KEYS = ("file", "mask", "path", "folder", "directory")  # node inputs that name a file or folder
# What a terminal or a reader can be fooled by: C0 and C1 controls, DEL, bidi marks and overrides, zero-width and invisible
# characters, soft hyphen, line and paragraph separators, Hangul fillers, interlinear marks, tag characters.
BAD_CHARS = ("\x7f-\x9f\u00ad\u061c\u115f\u1160\u180e\u200b-\u200f\u2028-\u202e\u2060-\u2064\u2066-\u2069"
             "\u3164\ufeff\uffa0\ufff9-\ufffb\U000e0000-\U000e007f")
DANGEROUS = re.compile("[\x00-\x1f" + BAD_CHARS + "]")
NOT_C0 = re.compile("[" + BAD_CHARS + "]")  # json.dumps already escapes C0 inside strings; between tokens it is layout


def safe(value):
    """A string that came from a package, made safe to print: each dangerous character becomes \\xNN, \\uNNNN or \\UNNNNNNNN."""
    def one(m):
        n = ord(m.group())
        return f"\\x{n:02x}" if n < 256 else f"\\u{n:04x}" if n < 0x10000 else f"\\U{n:08x}"
    return DANGEROUS.sub(one, str(value))


def say(message=""):
    print(message)


def die(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def dump_json(value, path):
    """JSON with the dangerous characters escaped, so a bidi override or a C1 control never lands raw in a published file."""
    text = json.dumps(value, indent=2, ensure_ascii=False)
    text = NOT_C0.sub(lambda m: f"\\u{ord(m.group()):04x}" if ord(m.group()) < 0x10000 else "".join(f"\\u{u:04x}" for u in struct.unpack(">2H", m.group().encode("utf-16-be"))), text)
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
MAX_SIDE = 8192
PICTURE_EXTS = ("png", "jpg", "webp")


def sniff(path):
    """(kind, extension) by magic bytes: image (png, jpg, webp), audio (mp3, wav, flac, ogg), video (mp4, webm, avi), else (None, None)."""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return None, None
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image", "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image", "webp"
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3"):
        return "audio", "mp3"
    if head.startswith(b"fLaC"):
        return "audio", "flac"
    if head.startswith(b"OggS"):
        return "audio", "ogg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio", "wav"
    if head[4:8] == b"ftyp":
        return "video", "mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video", "webm"
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "video", "avi"
    return None, None


def media_kind(path):
    return sniff(path)[0]


def preview_ext(path):
    kind, ext = sniff(path)
    return ext if kind == "image" else None


def picture_problem(path):
    """Why a PNG, JPEG or WebP is not what it says, from its structure alone (no decoding), or None when it is sound."""
    try:
        size = os.path.getsize(path)
        if size > 64 << 20:
            return "over 64 MB"
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return str(e)
    ext = preview_ext(path)
    if ext == "png":
        pos, first = 8, True
        while pos + 12 <= len(data):
            length, kind = struct.unpack(">I4s", data[pos:pos + 8])
            end = pos + 12 + length
            if end > len(data):
                return "a PNG chunk runs past the end of the file"
            if first:
                if kind != b"IHDR" or length != 13:
                    return "a PNG must start with its IHDR"
                width, height = struct.unpack(">II", data[pos + 8:pos + 16])
                if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
                    return f"a PNG of {width}x{height} (at most {MAX_SIDE}x{MAX_SIDE})"
                first = False
            if zlib.crc32(data[pos + 4:end - 4]) != struct.unpack(">I", data[end - 4:end])[0]:
                return "a PNG chunk has a wrong checksum"
            pos = end
            if kind == b"IEND":
                return None if pos == len(data) else "bytes after the PNG's IEND"
        return "a PNG with no IEND at its end"
    if ext == "webp":
        if struct.unpack("<I", data[4:8])[0] != len(data) - 8:
            return "a WebP whose RIFF size is not the file's size"
        pos = 12
        while pos + 8 <= len(data):
            kind, length = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
            body = data[pos + 8:pos + 8 + length]
            if pos + 8 + length > len(data):
                return "a WebP chunk runs past the end of the file"
            dims = None
            if kind == b"VP8X" and len(body) >= 10:
                dims = (int.from_bytes(body[4:7], "little") + 1, int.from_bytes(body[7:10], "little") + 1)
            elif kind == b"VP8L" and len(body) >= 5:
                bits = int.from_bytes(body[1:5], "little")
                dims = ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
            elif kind == b"VP8 " and len(body) >= 10:
                dims = (struct.unpack("<H", body[6:8])[0] & 0x3FFF, struct.unpack("<H", body[8:10])[0] & 0x3FFF)
            if dims and not (0 < dims[0] <= MAX_SIDE and 0 < dims[1] <= MAX_SIDE):
                return f"a WebP of {dims[0]}x{dims[1]} (at most {MAX_SIDE}x{MAX_SIDE})"
            pos += 8 + length + (length & 1)
        return None
    if ext == "jpg":
        if not data.endswith(b"\xff\xd9"):
            return "a JPEG that does not end with its end marker"
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 0xFF:
                return "a JPEG with a broken marker"
            marker = data[pos + 1]
            if marker == 0xFF:
                pos += 1
                continue
            if marker in (0x01, *range(0xD0, 0xD8)):
                pos += 2
                continue
            length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                if length < 8 or pos + 9 > len(data):
                    return "a JPEG with a broken frame header"
                height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
                if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
                    return f"a JPEG of {width}x{height} (at most {MAX_SIDE}x{MAX_SIDE})"
                return None
            if marker == 0xDA:
                break
            pos += 2 + length
        return "a JPEG with no frame header"
    return "not a PNG, JPEG or WebP"


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


def file_inputs(workflow):
    """(inputs dict, key, node) for every input of a node that names a file or folder."""
    for node in nodes_of(workflow):
        inputs = node.get("inputs")
        if isinstance(inputs, dict):
            for key in PATH_KEYS:
                if isinstance(inputs.get(key), str) and inputs[key]:
                    yield inputs, key, node


def gather_inputs(workflow, folder, find, show_real=False):
    """Copy the files that load nodes name into folder/inputs/ and point the nodes at `inputs/<name>`.

    `find(value)` returns the path of the file a node names, or None when it is not there. Only a file whose first bytes
    say the media kind the node takes is copied (a picture must also be sound, see picture_problem), named by its bytes'
    extension, never starting with a dot. A file two nodes name is copied once.
    Returns (notes, missing): lines for the report.
    """
    notes, missing = [], []
    done = {}  # real source path -> name in inputs/
    used = set()  # case-folded names taken
    for inputs, key, node in file_inputs(workflow):
        kind = LOADS.get(node.get("type")) if isinstance(node.get("type"), str) else None
        if not kind or key not in FILE_INPUTS:
            continue
        value = inputs[key]
        wanted = "image" if key == "mask" else kind
        source = find(value)
        if source is None:
            missing.append(f"{safe(value)} (a {safe(node.get('type'))} node names it, and the file was not found)")
            continue
        real = os.path.realpath(source)
        if real not in done:
            found, ext = sniff(real)
            if found != wanted:
                missing.append(f"{safe(value)} is not a {wanted} file by its first bytes: not copied")
                continue
            problem = picture_problem(real) if found == "image" else None
            if problem:
                missing.append(f"{safe(value)} was not copied: {problem}")
                continue
            stem = os.path.splitext(SAFE_NAME.sub("_", os.path.basename(value)))[0].lstrip(".") or "input"
            name, n = f"{stem}.{ext}", 1
            while name.casefold() in used:
                n += 1
                name = f"{stem}-{n}.{ext}"
            used.add(name.casefold())
            os.makedirs(os.path.join(folder, "inputs"), exist_ok=True)
            shutil.copyfile(real, os.path.join(folder, "inputs", name))
            done[real] = name
            size = os.path.getsize(real)
            notes.append(f"{safe(real) if show_real else safe(value)} -> inputs/{name}" + (f" ({size // 1024} KB: samples stay under {MAX_INPUT // 1024} KB, make it smaller)" if size > MAX_INPUT else ""))
        inputs[key] = f"inputs/{done[real]}"
    return notes, missing


def bare_name(value):
    return re.split(r"[\\/]", value.rstrip("\\/"))[-1].lstrip(".") or "TODO"


def finish_paths(workflow):
    """No local path stays in the published workflow: a file input that is one is cut to its bare name. Returns report lines."""
    lines = []
    for inputs, key, _node in file_inputs(workflow):
        if LOCAL_PATH.match(inputs[key]):
            inputs[key] = bare_name(inputs[key])
            lines.append(f"a local path was cut to its bare name {safe(inputs[key])!r}: put the file in inputs/ and point the node at inputs/<name>, or clear it")
    for item in dicts((workflow.get("app") or {}).get("inputs")) if isinstance(workflow.get("app"), dict) else []:
        if isinstance(item.get("default"), str) and LOCAL_PATH.match(item["default"]):
            item["default"] = bare_name(item["default"])
            lines.append(f"an app input's default was a local path, now {safe(item['default'])!r}: point it at inputs/<name>")
    for inputs, key, node in file_inputs(workflow):
        if node.get("type") in LOADS and key in FILE_INPUTS and not inputs[key].startswith("inputs/"):
            lines.append(f"{safe(inputs[key])}: a file a node names that is not in inputs/ yet")
    return lines


def local_path_values(workflow):
    """The local paths a workflow still holds (file inputs and app defaults): bin/check refuses them."""
    found = [inputs[key] for inputs, key, _ in file_inputs(workflow) if LOCAL_PATH.match(inputs[key])]
    app = workflow.get("app")
    if isinstance(app, dict):
        found += [i["default"] for i in dicts(app.get("inputs")) if isinstance(i.get("default"), str) and LOCAL_PATH.match(i["default"])]
    return found


def foreign_nodes(workflow, builtin=None):
    """The node types that are not built in: not in `builtin` (the ids `fugue node list` gives; None means any `fugue/` id) and not a group the workflow defines."""
    groups = workflow.get("groups") if isinstance(workflow.get("groups"), dict) else {}
    out = set()
    for node in nodes_of(workflow):
        kind = node.get("type")
        if not isinstance(kind, str):
            out.add(repr(kind))
        elif kind not in groups and not (kind in builtin if builtin is not None else kind.startswith("fugue/")):
            out.add(kind)
    return sorted(out)


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
    problem = picture_problem(picture) if ext else None
    if ext and not problem and size <= MAX_PREVIEW:
        shutil.copyfile(picture, os.path.join(folder, f"preview.{ext}"))
        return None
    why = problem or ("it is not a PNG, JPEG or WebP picture" if not ext else f"it is {size // 1024} KB (at most {MAX_PREVIEW // 1024} KB)")
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
    if isinstance(about, dict) and "community" in about:
        for kind in foreign_nodes(flow)[:5]:
            items.append(f"a community template may use only built-in nodes: {safe(kind)} is not one (bin/check-all with a Fugue binary checks this against its node list)")
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
