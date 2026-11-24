# Depth (Fugue pack)

The node **Depth Estimate** gives a picture as a depth picture: gray in 3 channels, the nearest part white and the
farthest black (stretched to the full range), at the size of the picture. It is the depth map of ComfyUI's
`AIO_Preprocessor` / `DepthAnythingV2Preprocessor`, and the Klein DA Edit template uses it as the first reference
(`flux2-klein-9b-da-edit-depth`: the node replaces image 1 by its depth picture). Depth Anything V2 through ONNX Runtime, in this pack's
own Python environment.

## Licences (checked 2026-11-23)

| What | Licence | Where |
| --- | --- | --- |
| This pack | MIT | `pack.json` |
| Depth Anything V2 code | Apache-2.0 | https://github.com/DepthAnything/Depth-Anything-V2/blob/main/LICENSE |
| Depth Anything V2 **Small** weights | Apache-2.0 | model card `depth-anything/Depth-Anything-V2-Small`; the ONNX export is `onnx-community/depth-anything-v2-small` (card: apache-2.0); `catalog/depth-anything.json` |
| Depth Anything V2 Base, Large, Giant weights | **CC-BY-NC-4.0** (non-commercial) | their model cards |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| NumPy, Pillow | BSD-3-Clause, MIT-CMU | |

Only the Small model is offered for download. The ComfyUI workflow this follows uses the Large one, whose
non-commercial licence a commercially usable app must not fetch for you: the depth maps differ somewhat (Small is
coarser at edges and thin parts). If you accept the licence for your own use, export or download a Base or Large ONNX file
yourself and put it in the `depth-anything` folder of the models folder; the node takes any Depth Anything V2 ONNX file whose
input is `pixel_values` (any height and width a multiple of 14) and whose first output is the depth.
Nothing is bundled: the weights are downloaded from the model picker after a question that names the licence.

## Develop

```sh
uv sync --extra cpu                 # with the dev group: onnx, pytest
uv run --extra cpu pytest                    # 12 tests, a 199-byte stand-in model, no network
FUGUE_DEPTH_MODEL=$PWD/tests/fixtures/tiny-depth.onnx fugue node test .
```

A node test cannot give a model (a resource), so the node also reads `FUGUE_DEPTH_MODEL` when its `model` input is empty.
`tests/make_fixture.py` rebuilds the stand-in. For the real model, download it from the node's picker (or the URL in
`catalog/depth-anything.json`) and point the variable at it.

GPU: `uv sync --no-dev --extra cuda` swaps in `onnxruntime-gpu` (CUDA and cuDNN must be installed); Device `auto` then uses it.
The node does not declare `needs.gpu`, so Fugue does not schedule its GPU memory against the helper's.

`depth-estimate/onnx_node.py` (the command protocol, execution providers, the picture as a tensor) is the same file as in
`io.github.bmaltais.fugue-remove-background`, `-remove-object` and `-segment`; change all together.
