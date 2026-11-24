"""Find by Text: GroundingDINO through ONNX Runtime, as a Fugue command node.

The person names what to find in words ("red balloon", "dog. cat"); the model gives a box for each
match, in the picture's pixels, as text lines `x1 y1 x2 y2` that the Segment node takes as its Box.
GroundingDINO tiny (IDEA-Research, Apache-2.0, github.com/IDEA-Research/GroundingDINO), the ONNX
export of onnx-community (Apache-2.0): the picture is scaled to fit 800 x 800 and padded, with a
mask of the real part; the words are BERT (uncased) wordpieces, `[CLS] phrase . [SEP]`, one run for each phrase; the model
gives 900 candidate boxes (centre x, centre y, width, height, as fractions of the real part of the
picture) and, for each, a logit per word piece, so a candidate's score is the largest sigmoid among
the phrase's pieces. The matches of the phrases are merged, best first.

The tokenizer is here (a short wordpiece, with `vocab.txt` from bert-base-uncased, Apache-2.0) so that
a model is one file; the models of the Hugging Face repository `onnx-community/grounding-dino-tiny-ONNX`
read it the same way.

Run by run.sh in the pack's own environment (spec 6.8), with `../segment/onnx_node.py`.
"""
import resource
import sys
import unicodedata
from pathlib import Path

NODE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(NODE_DIR.parent / "segment"))  # the pack's one copy of the ONNX Runtime helpers

import numpy as np
import onnx_node
from onnx_node import MEAN, STD, NodeError
from PIL import Image, ImageDraw, ImageFont

MAX_TOKENS = 256  # the model's text length (its logits have this many columns)
DEFAULT_SIDE = 800
NMS_IOU = 0.6  # a box covering this much of a better one's area is the same match
SEPARATORS = str.maketrans({".": "\n", ",": "\n", ";": "\n"})


def parse_query(text: str) -> list[str]:
    """The phrases of the query: pieces between periods, commas, semicolons and line breaks, trimmed."""
    phrases = [" ".join(piece.split()) for piece in str(text or "").translate(SEPARATORS).splitlines()]
    phrases = [p for p in phrases if p]
    if not phrases:
        raise NodeError("prompt_missing", "Nothing to find. Say what to look for in Query, for example: red balloon")
    return phrases


class WordPiece:
    """BERT's uncased tokenizer: lowercase, no accents, split at punctuation, then longest-match wordpieces."""

    def __init__(self, vocab_lines: list[str]):
        self.vocab = {token: i for i, token in enumerate(vocab_lines)}
        self.names = {i: token for token, i in self.vocab.items()}
        self.unk = self.vocab["[UNK]"]

    def tokens(self, ids: list[int]) -> list[str]:
        return [self.names[i] for i in ids]

    @staticmethod
    def words(text: str) -> list[str]:
        text = unicodedata.normalize("NFD", text.lower())
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        out, current = [], ""
        for c in text:
            kind = unicodedata.category(c)
            if c.isspace() or kind in ("Cc", "Cf") or c == "\x00":
                if current and c.isspace():
                    out.append(current)
                    current = ""
            elif kind.startswith("P") or (ord(c) < 128 and not c.isalnum()) or _is_cjk(c):
                if current:
                    out.append(current)
                    current = ""
                out.append(c)
            else:
                current += c
        if current:
            out.append(current)
        return out

    def piece(self, word: str) -> list[int]:
        if len(word) > 100:
            return [self.unk]
        ids, start = [], 0
        while start < len(word):
            end, found = len(word), None
            while end > start:
                part = ("##" if start else "") + word[start:end]
                if part in self.vocab:
                    found = self.vocab[part]
                    break
                end -= 1
            if found is None:
                return [self.unk]
            ids.append(found)
            start = end
        return ids

    def encode(self, text: str) -> list[int]:
        return [i for word in self.words(text) for i in self.piece(word)]


def _is_cjk(c: str) -> bool:
    o = ord(c)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0x20000 <= o <= 0x2A6DF or 0xF900 <= o <= 0xFAFF


def build_text(phrase: str, tokenizer: WordPiece) -> tuple[np.ndarray, tuple[int, int]]:
    """`input_ids` [1, n] for `[CLS] phrase . [SEP]` and the [start, end) word pieces of the phrase."""
    pieces = tokenizer.encode(phrase)
    ids = [tokenizer.vocab["[CLS]"], *pieces, tokenizer.vocab["."], tokenizer.vocab["[SEP]"]]
    if len(ids) > MAX_TOKENS:
        raise NodeError("prompt_too_long", f"A phrase is {len(ids)} word pieces; the model reads at most {MAX_TOKENS}. Shorten it.")
    return np.asarray([ids], np.int64), (1, 1 + len(pieces))


def letterbox(image: Image.Image, side: int, dtype) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    """The picture as `pixel_values` [1, 3, side, side] (scaled to fit, ImageNet mean and deviation, zero padding at the
    bottom and right), `pixel_mask` [1, side, side] (1 on the picture) and the picture's scaled size (width, height)."""
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        image = Image.alpha_composite(Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba)
    width, height = image.size
    scale = side / max(width, height)
    valid = (max(1, min(side, round(width * scale))), max(1, min(side, round(height * scale))))
    rgb = np.asarray(image.convert("RGB").resize(valid, Image.BILINEAR), np.float32).transpose(2, 0, 1) / 255.0
    pixels = np.zeros((1, 3, side, side), np.float32)
    pixels[0, :, :valid[1], :valid[0]] = (rgb[None] - MEAN) / STD
    mask = np.zeros((1, side, side), np.int64)
    mask[0, :valid[1], :valid[0]] = 1
    return pixels.astype(dtype), mask, valid


def iou_covering(a: tuple, b: tuple) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def decode(logits, boxes, span, phrase, size, threshold) -> list[dict]:
    """Matches of one phrase, best first: `{"box": (x1, y1, x2, y2), "score", "phrase"}` in the picture's pixels (`size` is
    (width, height)). `span` is the phrase's [start, end) word pieces; the score is the largest sigmoid among them.

    `logits` [1, n, tokens] and `boxes` [1, n, 4] (centre x, centre y, width, height) are the model's. Boxes are fractions of the
    real part of the picture, so the picture's own size scales them."""
    width, height = size
    scores = 1.0 / (1.0 + np.exp(-np.clip(np.asarray(logits, np.float32)[0], -50.0, 50.0)))
    top = scores[:, span[0]:span[1]].max(axis=1)
    found: list[dict] = []
    for i in np.argsort(-top, kind="stable"):
        if top[i] < threshold:
            break
        cx, cy, w, h = (float(v) for v in np.asarray(boxes)[0, i])
        box = (max(0.0, (cx - w / 2) * width), max(0.0, (cy - h / 2) * height),
               min(float(width), (cx + w / 2) * width), min(float(height), (cy + h / 2) * height))
        if box[2] - box[0] < 1 or box[3] - box[1] < 1 or any(iou_covering(box, f["box"]) > NMS_IOU for f in found):
            continue
        found.append({"box": box, "score": float(top[i]), "phrase": phrase})
    return found


def merge(per_phrase: list[list[dict]], max_results: int) -> list[dict]:
    """The matches of all the phrases, best first; a box the same as a better one of another phrase is dropped
    (a person is also a man); `max_results` 0 keeps them all."""
    found: list[dict] = []
    for match in sorted((m for matches in per_phrase for m in matches), key=lambda m: -m["score"]):
        if not any(iou_covering(match["box"], f["box"]) > NMS_IOU for f in found):
            found.append(match)
    return found[:max_results] if max_results else found


def format_boxes(found: list[dict]) -> str:
    """One `x1 y1 x2 y2` line per match, whole pixels: the Box input of the Segment node."""
    return "\n".join(" ".join(str(round(v)) for v in f["box"]) for f in found)


def preview(image: Image.Image, found: list[dict]) -> Image.Image:
    """The picture with each match's box, phrase and score drawn on it, to tune Threshold by eye."""
    canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    size = max(12, round(max(canvas.size) / 60))
    try:
        font = ImageFont.load_default(size=size)
    except (TypeError, OSError):  # an old Pillow, or no font engine
        font = ImageFont.load_default()
    palette = [(230, 60, 60), (60, 170, 80), (60, 110, 230), (230, 170, 30), (170, 70, 200)]
    for n, f in enumerate(found):
        color = palette[n % len(palette)]
        draw.rectangle(f["box"], outline=color, width=max(2, size // 4))
        label = f"{f['phrase']} {f['score']:.2f}"
        x, y = f["box"][0], max(0, f["box"][1] - size - 2)
        draw.rectangle(draw.textbbox((x, y), label, font=font), fill=color)
        draw.text((x, y), label, fill=(255, 255, 255), font=font)
    return canvas


def model_path(inputs: dict) -> Path:
    return onnx_node.model_path(inputs, "FUGUE_DINO_MODEL",
                                "No GroundingDINO model. Pick one in Model (the picker offers the downloads of this pack) "
                                "or put a GroundingDINO ONNX file in the grounding-dino models folder.")


class Runner:
    """Keeps the model and the tokenizer between runs."""

    def __init__(self):
        self.session = self.key = None
        self.tokenizer = None

    def load(self, path: Path, device: str):
        key = (str(path), path.stat().st_mtime_ns, device)
        if self.session is None or key != self.key:
            self.session = None  # free the old model before the new one is read
            self.session = onnx_node.open_session(str(path), device, path.name)
            self.key = key
        if self.tokenizer is None:
            self.tokenizer = WordPiece((NODE_DIR / "vocab.txt").read_text(encoding="utf-8").splitlines())
        return self.session

    def run(self, request: dict, say) -> dict:
        inputs = request["inputs"]
        work = Path(request["work_dir"])
        phrases = parse_query(inputs.get("query", ""))
        threshold = float(inputs.get("threshold", 0.3))
        image = Image.open(inputs["image"]["path"])
        image.load()
        say(0.05, "loading the model")
        session = self.load(model_path(inputs), inputs.get("device", "auto"))
        meta = {i.name: i for i in session.get_inputs()}
        shape = meta["pixel_values"].shape[2:4]
        side = int(shape[0]) if all(isinstance(n, int) for n in shape) else DEFAULT_SIDE
        dtype = np.float16 if meta["pixel_values"].type == "tensor(float16)" else np.float32
        pixels, mask, _ = letterbox(image, side, dtype)
        per_phrase = []
        for n, phrase in enumerate(phrases):
            # One run per phrase: with several phrases in one prompt the model scores the later ones far lower
            # (a glove 0.8 alone, 0.14 as the second phrase), whatever the order.
            say(0.2 + 0.7 * n / len(phrases), f"looking for {phrase}")
            ids, span = build_text(phrase, self.tokenizer)
            feed = {"pixel_values": pixels, "pixel_mask": mask, "input_ids": ids,
                    "token_type_ids": np.zeros_like(ids), "attention_mask": np.ones_like(ids)}
            logits, boxes = session.run(["logits", "pred_boxes"], {k: v for k, v in feed.items() if k in meta})[:2]
            per_phrase.append(decode(logits, boxes, span, phrase, image.size, threshold))
        say(0.9, "drawing the preview")
        found = merge(per_phrase, int(inputs.get("max_results", 0) or 0))
        work.mkdir(parents=True, exist_ok=True)
        preview(image, found).save(work / "preview.png")
        return {"boxes": format_boxes(found), "preview": {"path": "preview.png"},
                "_stats": {"peak_memory_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}}


def serve(stdin, stdout, persistent: bool) -> int:
    return onnx_node.serve(stdin, stdout, persistent, Runner())


def main() -> int:
    return serve(sys.stdin, sys.stdout, onnx_node.node_is_persistent())


if __name__ == "__main__":
    sys.exit(main())
