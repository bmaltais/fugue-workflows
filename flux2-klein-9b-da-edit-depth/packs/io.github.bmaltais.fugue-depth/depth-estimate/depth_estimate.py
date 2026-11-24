"""Depth Estimate: Depth Anything V2 through ONNX Runtime, as a Fugue command node.

The model gives a relative inverse depth: the nearest part has the largest value. The result
is stretched to the full range and written as a 3-channel gray picture, near light and far
dark, the way ControlNet's depth preprocessors give it. The pre-processing is Depth Anything
V2's own (github.com/DepthAnything/Depth-Anything-V2, Apache-2.0): resize keeping the aspect
ratio so the shorter side reaches `resolution`, both sides a multiple of 14, ImageNet mean and
standard deviation; the output is resized back to the picture's size.

Run by run.sh in the pack's own environment (spec 6.8). One-shot or persistent, see main().
"""
import resource
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import onnx_node
from onnx_node import NodeError, choose_providers  # noqa: F401  (the tests use these names)
from onnx_node import image_tensor as preprocess

MULTIPLE = 14  # the patch size of the ViT: the model takes sizes that are a multiple of it


def model_size(width: int, height: int, resolution: int) -> tuple[int, int]:
    """The (height, width) the picture is given to the model at: the shorter side `resolution`,
    the aspect ratio kept, both a multiple of 14 (Depth Anything V2's `lower_bound` resize)."""
    scale = max(resolution / width, resolution / height)

    def snap(side: float) -> int:
        snapped = round(side / MULTIPLE) * MULTIPLE
        return int(np.ceil(side / MULTIPLE) * MULTIPLE) if snapped < resolution else snapped

    return snap(height * scale), snap(width * scale)


def postprocess(output: np.ndarray, size: tuple[int, int]) -> Image.Image:
    """The model's depth as an 8-bit RGB picture of `size` (width, height), near light, stretched to 0..255."""
    depth = np.asarray(output, np.float32).reshape(output.shape[-2:])
    depth = np.asarray(Image.fromarray(depth, "F").resize(size, Image.BILINEAR))
    low, high = float(depth.min()), float(depth.max())
    scaled = (depth - low) / (high - low) if high > low else np.zeros_like(depth)  # a flat scene is black
    gray = np.rint(np.clip(scaled, 0.0, 1.0) * 255.0).astype(np.uint8)
    return Image.fromarray(np.stack([gray] * 3, axis=-1), "RGB")


def model_path(inputs: dict) -> Path:
    return onnx_node.model_path(inputs, "FUGUE_DEPTH_MODEL",
                                "No Depth Anything model. Pick one in Model (the picker offers the "
                                "download of this pack) or put a .onnx file in the depth-anything models folder.")


class Runner:
    """Keeps the ONNX Runtime session between runs, so a persistent program loads the model once."""

    def __init__(self):
        self.session = None
        self.key = None

    def load(self, path: Path, device: str):
        key = (str(path), path.stat().st_mtime_ns, device)
        if self.session is None or key != self.key:
            self.session = None  # free the old model before the new one is read
            self.session = onnx_node.open_session(str(path), device, path.name)
            self.key = key
        return self.session

    def run(self, request: dict, say) -> dict:
        inputs = request["inputs"]
        work = Path(request["work_dir"])
        say(0.05, "loading the model")
        session = self.load(model_path(inputs), inputs.get("device", "auto"))
        meta = session.get_inputs()[0]
        dtype = np.float16 if meta.type == "tensor(float16)" else np.float32
        say(0.3, "reading the picture")
        image = Image.open(inputs["image"]["path"])
        image.load()
        size = model_size(*image.size, int(inputs.get("resolution", 832)))
        tensor = preprocess(image, size, dtype)
        say(0.4, "estimating the depth")
        output = session.run(None, {meta.name: tensor})[0]
        say(0.9, "making the picture")
        work.mkdir(parents=True, exist_ok=True)
        postprocess(output, image.size).save(work / "depth.png")
        return {"depth": {"path": "depth.png"},
                "_stats": {"peak_memory_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}}


def serve(stdin, stdout, persistent: bool) -> int:
    return onnx_node.serve(stdin, stdout, persistent, Runner())


def main() -> int:
    return serve(sys.stdin, sys.stdout, onnx_node.node_is_persistent())


if __name__ == "__main__":
    sys.exit(main())
