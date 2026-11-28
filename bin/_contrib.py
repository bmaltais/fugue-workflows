"""Shared by bin/import-fuguepack and bin/new-template (Python 3 standard library only).

Makes a template folder from a workflow: copies the pictures its nodes load into `<id>/inputs/`, points the
nodes at `inputs/<name>`, writes a template.json skeleton and lists what is still missing. It never writes
outside the new folder and never overwrites anything.
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
PREVIEWS = ("preview.webp", "preview.png", "preview.jpg")
MAX_PREVIEW = 300 * 1024  # as bin/check
MAX_INPUT = 600 * 1024  # as bin/check
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")
FILE_INPUTS = ("file", "mask")  # node inputs that name a file: Load Image's picture and its painted mask


def die(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def categories():
    with open(os.path.join(ROOT, "categories.json"), encoding="utf-8") as f:
        return [c["id"] for c in json.load(f)["categories"]]


def check_id(template_id):
    if not ID_RE.match(template_id):
        die(f"{template_id!r} is not a good id: use lowercase letters, digits and dashes (for example my-style-transfer).")
    folder = os.path.join(ROOT, template_id)
    if os.path.lexists(folder):
        die(f"{template_id}/ already exists. Pick another id, or remove the folder first.")
    return folder


def check_category(category):
    if category is not None and category not in categories():
        die(f"category {category!r} is not one of: {', '.join(categories())}")


def nodes_of(workflow):
    """Every node dict of the graph and of the groups the workflow holds."""
    scopes = [workflow.get("graph", {}).get("nodes", {})]
    scopes += [g.get("nodes", {}) for g in workflow.get("groups", {}).values() if isinstance(g, dict)]
    for scope in scopes:
        for node in scope.values():
            if isinstance(node, dict):
                yield node


def gather_inputs(workflow, folder, find):
    """Move the files that nodes name into folder/inputs/ and point the nodes at `inputs/<name>`.

    `find(value)` returns the path of the file a node names, or None when it is not there. A value that is
    already `inputs/<name>` and found stays as it is. Returns (notes, missing): lines for the report.
    """
    notes, missing, taken = [], [], {}
    for node in nodes_of(workflow):
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for key in FILE_INPUTS:
            value = inputs.get(key)
            if not isinstance(value, str) or not value or not node.get("type", "").startswith("fugue/load-"):
                continue
            source = find(value)
            if source is None:
                missing.append(f"{value} (a {node['type']} node names it, and the file was not found)")
                continue
            name = SAFE_NAME.sub("_", os.path.basename(value)) or "input"
            if taken.get(name, source) != source:  # two different files with one name
                stem, ext = os.path.splitext(name)
                n = 2
                while f"{stem}-{n}{ext}" in taken:
                    n += 1
                name = f"{stem}-{n}{ext}"
            if name not in taken:
                os.makedirs(os.path.join(folder, "inputs"), exist_ok=True)
                shutil.copyfile(source, os.path.join(folder, "inputs", name))
                taken[name] = source
                size = os.path.getsize(source)
                notes.append(f"inputs/{name}" + (f" is {size // 1024} KB: samples stay under {MAX_INPUT // 1024} KB, make it smaller" if size > MAX_INPUT else ""))
            inputs[key] = f"inputs/{name}"
    return notes, missing


def handles(value, out):
    if isinstance(value, dict):
        if "resource" in value and "hash" in value:
            out[value["hash"]] = value
        for item in value.values():
            handles(item, out)
    elif isinstance(value, list):
        for item in value:
            handles(item, out)


def write_template(folder, workflow, title, description, category, about=None):
    """workflow.fugue and a template.json skeleton. TODO marks what bin/check refuses until it is filled in."""
    with open(os.path.join(folder, "workflow.fugue"), "w", encoding="utf-8") as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)
        f.write("\n")
    skeleton = {
        "title": title,
        "description": description,
        "category": category or "TODO: one of " + ", ".join(categories()),
        "tags": [],
    }
    if isinstance(workflow.get("app"), dict):
        skeleton["app"] = True  # Fugue lists the workflow as an app only when template.json says so (its title, summary and kind come from the block)
    skeleton.update(about or {})
    with open(os.path.join(folder, "template.json"), "w", encoding="utf-8") as f:
        json.dump(skeleton, f, indent=2, ensure_ascii=False)
        f.write("\n")


def make_preview(folder, picture):
    """Put `picture` (a path) in as the preview when it fits; else convert it when a tool is installed.
    Returns a line for the report, or None when the preview is in place."""
    ext = os.path.splitext(picture)[1].lower().lstrip(".")
    ext = "jpg" if ext == "jpeg" else ext
    target = os.path.join(folder, f"preview.{ext}")
    if ext in ("webp", "png", "jpg") and os.path.getsize(picture) <= MAX_PREVIEW:
        shutil.copyfile(picture, target)
        return None
    for tool in (["magick"], ["convert"]):
        if shutil.which(tool[0]):
            out = os.path.join(folder, "preview.webp")
            args = tool + [picture + ("[0]" if ext != "webp" else ""), "-resize", "768x>", "-quality", "80", out]
            if subprocess.run(args, capture_output=True).returncode == 0 and os.path.getsize(out) <= MAX_PREVIEW:
                return None
            if os.path.exists(out):
                os.remove(out)
    return (f"preview: the package's picture is not a preview yet (it must be WebP, PNG or JPEG, at most {MAX_PREVIEW // 1024} KB, "
            f"about 768 px wide). Make one, for example: magick <picture> -resize 768x -quality 80 {os.path.basename(folder)}/preview.webp")


def todo(folder, extra=()):
    """What bin/check would still complain about, plus the notes of this run."""
    items = list(extra)
    try:
        with open(os.path.join(folder, "template.json"), encoding="utf-8") as f:
            about = json.load(f)
        for key in ("title", "description", "category"):
            if "TODO" in str(about.get(key, "")):
                items.append(f"template.json: write the {key}" + (f" (one of {', '.join(categories())})" if key == "category" else ""))
    except (OSError, ValueError):
        items.append("template.json is missing or unreadable")
    if not any(os.path.isfile(os.path.join(folder, p)) for p in PREVIEWS) and not any("preview" in i for i in items):
        items.append("preview.webp: a picture of what it makes, about 768 px wide, at most 300 KB")
    try:
        with open(os.path.join(folder, "workflow.fugue"), encoding="utf-8") as f:
            flow = json.load(f)
    except (OSError, ValueError):
        return items if any(i.startswith("workflow.fugue") for i in items) else items + ["workflow.fugue is missing or unreadable"]
    used = {}
    handles(flow.get("graph", {}), used)
    handles(flow.get("groups", {}), used)
    recorded = {m.get("hash"): m for m in flow.get("requires", {}).get("models", [])}
    for digest, handle in sorted(used.items()):
        entry = recorded.get(digest, {})
        label = handle.get("name", digest)
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
