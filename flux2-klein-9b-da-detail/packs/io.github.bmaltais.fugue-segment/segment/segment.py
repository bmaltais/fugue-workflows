"""Segment by Points or Box: SAM 2.1 through ONNX Runtime, as a Fugue command node.

The person says what to cut out with points (to include, to leave out) and/or a box, in the
picture's pixels, and the model gives the mask of that object. SAM 2.1 (Meta, Apache-2.0,
github.com/facebookresearch/sam2): the picture is squashed to 1024 x 1024 and normalised with
the ImageNet mean and deviation; the encoder makes an embedding of it once, and the small decoder
turns the embedding and the prompts into three low-resolution logit masks and their predicted IoUs.
A point is a coordinate with the label 1 (include) or 0 (leave out); a box is two coordinates
with the labels 2 (top left) and 3 (bottom right), put before the points.

The model is a bundle (a .zip with `*.encoder.onnx` and `*.decoder.onnx`, as the Hugging Face
repository vietanhdev/segment-anything-2.1-onnx-models has them), read in memory, never unpacked.

Run by run.sh in the pack's own environment (spec 6.8). One-shot or persistent, see main().
"""
import hashlib
import re
import resource
import sys
import zipfile
from pathlib import Path

import numpy as np
import onnx_node
from onnx_node import NodeError, image_tensor
from PIL import Image

MODEL_SIZE = 1024  # SAM 2.1's input side; the prompts are given in this space
POSITIVE, NEGATIVE, BOX_START, BOX_END = 1.0, 0.0, 2.0, 3.0
NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
MAX_BUNDLE_PART = 2 << 30  # a model file larger than this is not a SAM 2.1 export


def parse_coordinates(text: str, count: int, what: str) -> list[list[float]]:
    """Lines of `count` numbers each (separated by spaces, commas or semicolons); blank lines are skipped."""
    rows = []
    for number, line in enumerate(str(text or "").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.sub(NUMBER, "", line).strip(" \t,;"):
            raise NodeError("prompt_invalid", f"{what}, line {number}: \"{line.strip()}\" is not numbers.")
        values = [float(v) for v in NUMBER.findall(line)]
        if len(values) != count:
            raise NodeError("prompt_invalid", f"{what}, line {number}: expected {count} numbers, got {len(values)}.")
        rows.append(values)
    return rows


def check_inside(x: float, y: float, size: tuple[int, int], what: str):
    width, height = size
    if not (0 <= x <= width and 0 <= y <= height):
        raise NodeError("prompt_outside", f"{what} ({x:g}, {y:g}) is outside the picture, which is {width} x {height} pixels "
                        "(x goes right, y goes down from the top left).")


def parse_prompts(positive: str, negative: str, box: str, size: tuple[int, int]) -> dict:
    """Points and box from the node's text inputs, in the picture's pixels. `size` is (width, height)."""
    include = parse_coordinates(positive, 2, "Include points")
    exclude = parse_coordinates(negative, 2, "Exclude points")
    rows = parse_coordinates(box, 4, "Box")
    for x, y in include + exclude:
        check_inside(x, y, size, "A point")
    rectangles = []
    for x1, y1, x2, y2 in rows:
        check_inside(x1, y1, size, "The box corner")
        check_inside(x2, y2, size, "The box corner")
        rectangle = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        if rectangle[0] == rectangle[2] or rectangle[1] == rectangle[3]:
            raise NodeError("prompt_invalid", "The box has no area: its two corners share an x or a y.")
        rectangles.append(rectangle)
    if len(rectangles) > 1 and (include or exclude):
        raise NodeError("prompt_invalid", "Points go with one box: with several boxes (one object each, as Find by Text gives) "
                        "leave Include points and Exclude points empty.")
    if not rectangles and not include:
        raise NodeError("prompt_missing", "Nothing to segment. Give at least one Include point, or a Box.")
    return {"include": include, "exclude": exclude, "boxes": rectangles}


def objects(prompts: dict) -> list[dict]:
    """One prompt set per object: each box is an object (the points go with the only box, or with no box)."""
    boxes = prompts["boxes"] or [None]
    return [{"include": prompts["include"], "exclude": prompts["exclude"], "box": box} for box in boxes]


def decoder_prompts(prompts: dict, size: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """The decoder's `point_coords` [1, n, 2] and `point_labels` [1, n]: the box corners first, then the points."""
    width, height = size
    scale = np.array([MODEL_SIZE / width, MODEL_SIZE / height], np.float32)
    coords, labels = [], []
    if prompts["box"]:
        x1, y1, x2, y2 = prompts["box"]
        coords += [[x1, y1], [x2, y2]]
        labels += [BOX_START, BOX_END]
    for points, label in ((prompts["include"], POSITIVE), (prompts["exclude"], NEGATIVE)):
        coords += points
        labels += [label] * len(points)
    return (np.asarray(coords, np.float32)[None] * scale).astype(np.float32), np.asarray(labels, np.float32)[None]


def to_mask(logits: np.ndarray, size: tuple[int, int], invert: bool, soft: bool) -> Image.Image:
    """A [h, w] logit map as an 8-bit gray mask of `size` (width, height): 255 where the model says the object is.
    The logits are scaled up first and cut after, so the edge is as fine as the picture."""
    resized = np.asarray(Image.fromarray(np.asarray(logits, np.float32), "F").resize(size, Image.BILINEAR))
    if soft:
        value = 1.0 / (1.0 + np.exp(-np.clip(resized, -50.0, 50.0)))
    else:
        value = (resized > 0).astype(np.float32)
    if invert:
        value = 1.0 - value
    return Image.fromarray(np.rint(np.clip(value, 0.0, 1.0) * 255.0).astype(np.uint8), "L")


def read_bundle(path: Path) -> tuple[bytes, bytes]:
    """The encoder and decoder bytes of a model bundle, read from the zip in memory (nothing is unpacked)."""
    try:
        with zipfile.ZipFile(path) as bundle:
            parts = {}
            for part in bundle.infolist():
                for role in ("encoder", "decoder"):
                    if part.filename.endswith(f".{role}.onnx") and ".." not in part.filename.split("/"):
                        if part.file_size > MAX_BUNDLE_PART:
                            raise NodeError("model_invalid", f"{path.name}: {part.filename} is too large to be a SAM 2.1 model.")
                        parts[role] = bundle.read(part)
    except zipfile.BadZipFile as error:
        raise NodeError("model_invalid", f"{path.name} is not a zip file: a SAM 2.1 model is a bundle with "
                        "*.encoder.onnx and *.decoder.onnx inside.") from error
    if len(parts) != 2:
        raise NodeError("model_invalid", f"{path.name} has no *.encoder.onnx and *.decoder.onnx inside.")
    return parts["encoder"], parts["decoder"]


def model_path(inputs: dict) -> Path:
    return onnx_node.model_path(inputs, "FUGUE_SAM_MODEL",
                                "No SAM 2.1 model. Pick one in Model (the picker offers the downloads of this pack) "
                                "or put a SAM 2.1 bundle (.zip) in the sam2 models folder.")


class Runner:
    """Keeps the sessions between runs, and the embedding of the last picture: changing only the
    prompts then costs the decoder alone (tens of milliseconds), not the encoder (a second or more)."""

    def __init__(self):
        self.encoder = self.decoder = None
        self.key = None
        self.embedding_key = self.embedding = None
        self.encoder_runs = 0

    def load(self, path: Path, device: str):
        key = (str(path), path.stat().st_mtime_ns, device)
        if self.encoder is None or key != self.key:
            self.encoder = self.decoder = None  # free the old model before the new one is read
            self.embedding_key = self.embedding = None
            encoder, decoder = read_bundle(path)
            self.encoder = onnx_node.open_session(encoder, device, f"{path.name} (encoder)")
            self.decoder = onnx_node.open_session(decoder, device, f"{path.name} (decoder)")
            self.key = key
        return self.encoder, self.decoder

    def embed(self, image_path: Path, image: Image.Image):
        key = (self.key, hashlib.sha256(image_path.read_bytes()).hexdigest())
        if key != self.embedding_key:
            meta = self.encoder.get_inputs()[0]
            shape = meta.shape[2:4]
            size = tuple(shape) if all(isinstance(n, int) for n in shape) else (MODEL_SIZE, MODEL_SIZE)
            dtype = np.float16 if meta.type == "tensor(float16)" else np.float32
            names = [o.name for o in self.encoder.get_outputs()]
            outputs = self.encoder.run(names, {meta.name: image_tensor(image, size, dtype)})
            self.embedding = dict(zip(names, outputs))
            self.embedding_key = key
            self.encoder_runs += 1
        return self.embedding

    def run(self, request: dict, say) -> dict:
        inputs = request["inputs"]
        work = Path(request["work_dir"])
        image = Image.open(inputs["image"]["path"])
        image.load()
        prompts = parse_prompts(inputs.get("positive", ""), inputs.get("negative", ""), inputs.get("box", ""), image.size)
        say(0.05, "loading the model")
        self.load(model_path(inputs), inputs.get("device", "auto"))
        say(0.2, "looking at the picture")
        embedding = self.embed(Path(inputs["image"]["path"]), image)
        say(0.8, "finding the object")
        wanted = {i.name for i in self.decoder.get_inputs()}
        union = None  # the logits of the objects, each cell the largest: the union of their masks
        for each in objects(prompts):
            coords, labels = decoder_prompts(each, image.size)
            feed = {"point_coords": coords, "point_labels": labels,
                    "mask_input": np.zeros((1, 1, 256, 256), np.float32), "has_mask_input": np.zeros(1, np.float32), **embedding}
            masks, scores = self.decoder.run(None, {k: v for k, v in feed.items() if k in wanted})[:2]
            best = np.asarray(masks)[0, int(np.argmax(np.asarray(scores).reshape(-1)))]
            union = best if union is None else np.maximum(union, best)
        say(0.95, "making the mask")
        mask = to_mask(union, image.size, bool(inputs.get("invert")), bool(inputs.get("soft")))
        work.mkdir(parents=True, exist_ok=True)
        mask.save(work / "mask.png")
        return {"mask": {"path": "mask.png"},
                "_stats": {"peak_memory_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}}


def serve(stdin, stdout, persistent: bool) -> int:
    return onnx_node.serve(stdin, stdout, persistent, Runner())


def main() -> int:
    return serve(sys.stdin, sys.stdout, onnx_node.node_is_persistent())


if __name__ == "__main__":
    sys.exit(main())
