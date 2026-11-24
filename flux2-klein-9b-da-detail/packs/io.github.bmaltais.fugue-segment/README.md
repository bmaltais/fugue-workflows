# Segment: by Points, Box or Words (Fugue pack)

Two nodes, in this pack's own Python environment (ONNX Runtime):

- **Segment by Points or Box** gives objects of a picture as a mask (`role: mask`, white is the object). You say which object with
  points to include, points to leave out and/or a box, in the picture's pixels; several boxes (one per line) are several objects
  joined in one mask. SAM 2.1. Guide: [docs/masking.md](../../../docs/masking.md#select-an-object-by-points-or-a-box).
- **Find by Text** gives a box around each match of what you name in words (`red balloon`, `glove, tree`) as text lines
  `x1 y1 x2 y2`, and a preview with the scores. GroundingDINO tiny. Wire its `Boxes` to Segment's `Box` for **text to mask**.
  Guide: [docs/masking.md](../../../docs/masking.md#select-by-words).

## Licences (checked 2026-11-22)

| What | Licence | Where |
| --- | --- | --- |
| This pack | MIT | `pack.json` |
| SAM 2.1 code and checkpoints (Meta) | Apache-2.0 | https://github.com/facebookresearch/sam2/blob/main/LICENSE ("The SAM 2 model checkpoints, SAM 2 demo code and SAM 2 training code are licensed under Apache 2.0"); model cards `facebook/sam2.1-hiera-*` |
| The ONNX files (an export of those checkpoints by Viet-Anh Nguyen, one zip per size) | Apache-2.0, "license unchanged from upstream" | https://huggingface.co/vietanhdev/segment-anything-2.1-onnx-models; `catalog/sam2.json` |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| GroundingDINO code | Apache-2.0 | https://github.com/IDEA-Research/GroundingDINO/blob/main/LICENSE |
| GroundingDINO tiny weights (`IDEA-Research/grounding-dino-tiny`) and their ONNX export (`onnx-community/grounding-dino-tiny-ONNX`) | Apache-2.0 | the model cards, `license: apache-2.0`; `catalog/grounding-dino.json` |
| `find-by-text/vocab.txt` (the BERT uncased word list the model reads its words with, byte-identical to `google-bert/bert-base-uncased`) | Apache-2.0 | https://huggingface.co/google-bert/bert-base-uncased |
| NumPy, Pillow | BSD-3-Clause, MIT-CMU | |

Apache-2.0 asks for the licence and a notice with a copy. The model cards do not speak for the training data (SA-V and
SA-1B, whose own terms were not read): not verified here, so the catalog says "Apache-2.0" and links the licence.
The export is a third party's, not Meta's: the weights are the checkpoints' (checked by running them, below), the
graph is the exporter's. Nothing is bundled: the weights are downloaded from the model picker after a question that names
the licence. MobileSAM (Apache-2.0 code, Acly's ONNX files) is not offered: see the spec's decisions.

## The model

Two bundles in `catalog/sam2.json`, each one `.zip` with `*.encoder.onnx` and `*.decoder.onnx` (the zip is the file
Fugue downloads and checks by sha256; the node reads the two parts in memory and never unpacks it): **tiny** (117 MB)
and **base+** (272 MB). `small` and `large` of the same repository work if their zip is put in the `sam2` models folder
(same layout). The encoder takes `image` `[1, 3, 1024, 1024]` (ImageNet mean and deviation, the picture squashed to
the square) and gives `image_embed`, `high_res_feats_0` and `high_res_feats_1`; the decoder takes those and
`point_coords` (the picture's pixels scaled to 1024), `point_labels` (1 include, 0 leave out, 2 and 3 the box corners)
and gives three logit maps and their predicted IoUs; the node takes the best-scored map, scales its logits up to the
picture and cuts at 0. A persistent run keeps the embedding of the last picture, so changing only the prompts costs the
decoder (0.05 s) and not the encoder.

Measured here (12 threads, CPU, a 1200 x 900 picture): tiny 2.6 s for the first run (loading the model, the encoder
1 s), base+ 4.9 s (encoder 2.5 s), then 0.05 s for each change of prompts; peak memory 1.1 GB and 2.0 GB.

## Find by Text: the model

One `.onnx` file (`catalog/grounding-dino.json`): **half precision** (360 MB, the default) or full precision (719 MB). Inputs
`pixel_values` [1, 3, 800, 800] (a fixed size; the node scales the picture to fit and pads it, with a `pixel_mask` of the real
part), `input_ids`, `token_type_ids`, `attention_mask` (`[CLS] phrase . [SEP]`); outputs `logits` [1, 900, 256] (one per word
piece) and `pred_boxes` [1, 900, 4] (centre x, centre y, width, height, as fractions of the real part). A candidate's score is the
largest sigmoid among the phrase's pieces; the node keeps those above Threshold, drops a box that is the same as a better one,
and runs the model once per phrase (with several phrases in one prompt this export scores the later ones far lower).
The 8-bit file of the same repository was tried and is not offered: its boxes are tens of pixels off.

Measured here (RTX 3090 with another job holding 15 GB of it, and a 12-thread CPU; a 832 x 1216 picture): half precision 0.9 s a phrase
on the GPU, 4 s on the CPU; full precision 3 to 7 s on the CPU (it did not fit the 4 GB of GPU memory left). Peak memory 1.7 GB.
Real pictures (see the spec's decision rows): "clown", "red balloon", "glove" (two gloves), "fox" give a box on the object and
a clean SAM mask; "tree" in a dense forest gives boxes that overlap into one big mask (raise the threshold, or use points).

## Develop

```sh
uv sync --extra cpu                 # with the dev group: onnx, pytest
uv run --extra cpu pytest           # 55 tests, 2 KB stand-in models, no network
FUGUE_SAM_MODEL=$PWD/tests/fixtures/tiny-sam.zip fugue node test segment
# the real model: any bundle, from the node's picker or the repository above
FUGUE_SAM_REAL_MODEL=/path/to/sam2.1_hiera_tiny_20260221.zip uv run --extra cpu pytest -k real
FUGUE_DINO_MODEL=$PWD/tests/fixtures/tiny-dino.onnx fugue node test find-by-text
# the real GroundingDINO file (a red square found by its name):
FUGUE_DINO_REAL_MODEL=/path/to/grounding-dino-tiny_fp16.onnx uv run --extra cpu pytest -k real
```

A node test cannot give a model (a resource), so the nodes also read `FUGUE_SAM_MODEL` and `FUGUE_DINO_MODEL` when their `model`
input is empty. `tests/make_fixture.py` rebuilds the SAM stand-in (its decoder gives the box of the box corners and Include points),
`tests/make_dino_fixture.py` the GroundingDINO one (two constant boxes, 0.9 and 0.2).

GPU: `uv sync --no-dev --extra cuda` swaps in `onnxruntime-gpu` (CUDA and cuDNN must be installed); Device `auto` then uses it
(Find by Text with the half-precision model is tried on an RTX 3090 here; Segment on the GPU gave the same mask as on the CPU for the glove and balloon boxes). The node does not declare `needs.gpu`, so Fugue does not schedule its GPU memory against the helper's.

`segment/onnx_node.py` (the command protocol, execution providers, the picture as a tensor) is the same file as in
`io.github.bmaltais.fugue-remove-background`; change both together (Find by Text imports this pack's copy). A third ONNX pack is the time to make it a library.
