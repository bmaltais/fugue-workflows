"""What the ONNX Runtime command nodes of Fugue's example packs share (the command protocol, spec 7).

This file is kept identical in `io.github.bmaltais.fugue-remove-background` and
`io.github.bmaltais.fugue-segment` (a pack is installed on its own, so it cannot import from another).
Change both together. With a third pack, extract it to one small library each pack depends on.
"""
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

MEAN = np.array([0.485, 0.456, 0.406], np.float32).reshape(1, 3, 1, 1)
STD = np.array([0.229, 0.224, 0.225], np.float32).reshape(1, 3, 1, 1)


class NodeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def image_tensor(image: Image.Image, size: tuple[int, int], dtype) -> np.ndarray:
    """A picture as a model's input: [1, 3, h, w], ImageNet mean and deviation. `size` is (height, width)."""
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        base = Image.new("RGBA", rgba.size, (255, 255, 255, 255))  # a transparent part is white
        image = Image.alpha_composite(base, rgba)
    rgb = image.convert("RGB").resize((size[1], size[0]), Image.BILINEAR)
    array = np.asarray(rgb, np.float32).transpose(2, 0, 1)[None] / 255.0
    return ((array - MEAN) / STD).astype(dtype)


def choose_providers(device: str, available: list[str]) -> list[str]:
    cuda = "CUDAExecutionProvider"
    if device == "cpu":
        return ["CPUExecutionProvider"]
    if device == "cuda" and cuda not in available:
        raise NodeError("gpu_unavailable", "ONNX Runtime has no CUDA provider here. Install the GPU build "
                        "(uv sync --no-dev --extra cuda in the pack folder) with CUDA and cuDNN, or set Device to CPU or Auto.")
    return [cuda, "CPUExecutionProvider"] if cuda in available else ["CPUExecutionProvider"]


def open_session(model, device: str, name: str):
    """An ONNX Runtime session over a file path or the model's bytes. `name` is for the error."""
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.log_severity_level = 3
    options.enable_cpu_mem_arena = False  # the arena keeps every size it ever grew to: GBs on a big model
    options.enable_mem_pattern = False
    providers = choose_providers(device, ort.get_available_providers())
    try:
        return ort.InferenceSession(model, options, providers=providers)
    except Exception as error:  # a file that is not an ONNX model, or a provider that cannot start
        raise NodeError("model_invalid", f"{name} could not be loaded by ONNX Runtime: {error}") from error


def model_path(inputs: dict, env_var: str, missing: str) -> Path:
    """The file of the node's `model` input (a resource handle with its path), else the environment's (tests)."""
    handle = inputs.get("model")
    path = (handle or {}).get("path") if isinstance(handle, dict) else None
    path = path or os.environ.get(env_var)
    if not path or not Path(path).is_file():
        raise NodeError("model_missing", missing)
    return Path(path)


def serve(stdin, stdout, persistent: bool, runner) -> int:
    """The command protocol (spec 7) around `runner.run(request, say) -> outputs`. Returns the exit code.

    `outputs` may carry `_stats`, which becomes the result's stats."""

    def send(message: dict):
        stdout.write(json.dumps(message) + "\n")
        stdout.flush()

    def handle(request: dict) -> bool:
        ident = {"id": request["id"]} if persistent and "id" in request else {}
        try:
            outputs = runner.run(request, lambda v, m: send({"op": "progress", "value": v, "message": m, **ident}))
            stats = outputs.pop("_stats")
            send({"op": "result", "outputs": outputs, "stats": stats, **ident})
            return True
        except NodeError as error:
            send({"op": "error", "code": error.code, "message": str(error), **ident})
        except MemoryError:
            send({"op": "error", "code": "out_of_memory", "message": "Out of memory.", **ident})
        except Exception as error:  # noqa: BLE001  an unreadable picture, a model of another shape: say what it was
            send({"op": "error", "code": "node_failed", "message": f"{type(error).__name__}: {error}", **ident})
        return False

    if not persistent:
        return 0 if handle(json.loads(stdin.read())) else 1
    send({"op": "ready"})
    for line in stdin:
        if not line.strip():
            continue
        message = json.loads(line)
        if message.get("op") == "shutdown":
            return 0
        if message.get("op") == "run":
            handle(message)
        # "cancel": a run is not interruptible, and it answers when it ends or Fugue kills it
    return 0


def node_is_persistent() -> bool:
    with open(Path(os.environ["FUGUE_NODE_DIR"]) / "node.json") as file:
        node = json.load(file)
    return node["runtime"].get("mode") == "persistent"
