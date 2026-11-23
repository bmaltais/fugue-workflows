# Remove Background (Fugue pack)

One node, **Remove Background**: gives the subject of a picture as a mask (`role: mask`, white is the
subject). BiRefNet through ONNX Runtime, in this pack's own Python environment. User guide:
[docs/masking.md](../../../docs/masking.md#remove-a-background).

## Licences (checked 2026-11-22)

| What | Licence | Where |
| --- | --- | --- |
| This pack | MIT | `pack.json` |
| BiRefNet code | MIT | https://github.com/ZhengPeng7/BiRefNet/blob/main/LICENSE |
| BiRefNet weights (`.onnx`, released by the author, release `v1`) | MIT | model cards `ZhengPeng7/BiRefNet`, `BiRefNet_lite`; `catalog/birefnet.json` |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| NumPy, Pillow | BSD-3-Clause, MIT-CMU | |

The model cards do not speak for BiRefNet's training datasets. Not BRIA RMBG (non-commercial).
Nothing is bundled: the weights are downloaded from the model picker after a question that names the licence.

## Develop

```sh
uv sync --extra cpu                 # with the dev group: onnx, pytest
uv run --extra cpu pytest                    # 14 tests, a 176-byte stand-in model, no network
FUGUE_BIREFNET_MODEL=$PWD/tests/fixtures/tiny-birefnet.onnx fugue node test .
```

A node test cannot give a model (a resource), so the node also reads `FUGUE_BIREFNET_MODEL` when its `model` input is empty.
`tests/make_fixture.py` rebuilds the stand-in. For the real model, download one from the node's picker (or the release
page in `catalog/birefnet.json`) and point the variable at it.

GPU: `uv sync --no-dev --extra cuda` swaps in `onnxruntime-gpu` (CUDA and cuDNN must be installed); Device `auto` then uses it.
The node does not declare `needs.gpu`, so Fugue does not schedule its GPU memory against the helper's.

`remove-background/onnx_node.py` (the command protocol, execution providers, the picture as a tensor) is the same file as in
`io.github.bmaltais.fugue-segment`; change both together.
