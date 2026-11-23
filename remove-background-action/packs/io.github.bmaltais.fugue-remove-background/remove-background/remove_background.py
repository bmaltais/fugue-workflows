"""Remove Background: BiRefNet through ONNX Runtime, as a Fugue command node.

The model finds the salient subject of a picture and gives a soft mask of it (white is the
subject). The pre- and post-processing are BiRefNet's own (github.com/ZhengPeng7/BiRefNet,
MIT): resize to the model's input size, ImageNet mean and standard deviation, sigmoid on the
output, resize back to the picture's size.

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

DEFAULT_SIZE = (1024, 1024)  # BiRefNet's training size, used when the model's input is dynamic


def postprocess(output: np.ndarray, size: tuple[int, int], invert: bool, threshold: float) -> Image.Image:
    """The model's logits as an 8-bit gray mask of `size` (width, height). 0 threshold keeps it soft."""
    logits = np.asarray(output, np.float32).reshape(output.shape[-2:])
    probability = 1.0 / (1.0 + np.exp(-np.clip(logits, -50.0, 50.0)))
    resized = np.asarray(Image.fromarray(probability, "F").resize(size, Image.BILINEAR))
    if threshold > 0:
        resized = (resized >= threshold).astype(np.float32)
    if invert:
        resized = 1.0 - resized
    return Image.fromarray(np.rint(np.clip(resized, 0.0, 1.0) * 255.0).astype(np.uint8), "L")


def model_path(inputs: dict) -> Path:
    return onnx_node.model_path(inputs, "FUGUE_BIREFNET_MODEL",
                                "No BiRefNet model. Pick one in Model (the picker offers the "
                                "downloads of this pack) or put a .onnx file in the birefnet models folder.")


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
        shape = meta.shape[2:4]
        size = tuple(shape) if all(isinstance(n, int) for n in shape) else DEFAULT_SIZE
        dtype = np.float16 if meta.type == "tensor(float16)" else np.float32
        say(0.3, "reading the picture")
        image = Image.open(inputs["image"]["path"])
        image.load()
        tensor = preprocess(image, size, dtype)
        say(0.4, "finding the subject")
        output = session.run(None, {meta.name: tensor})[0]
        say(0.9, "making the mask")
        mask = postprocess(output, image.size, bool(inputs.get("invert")), float(inputs.get("threshold", 0.0)))
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
