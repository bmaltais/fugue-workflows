#!/bin/sh
# Runs in the pack's own environment (made by the pack's setup, `uv sync`).
pack=$(cd "$FUGUE_NODE_DIR/.." && pwd)
python="$pack/.venv/bin/python"
if [ ! -x "$python" ]; then
    printf '{"op":"error","code":"setup_missing","message":"The pack has no Python environment. Run `uv sync --no-dev --extra cpu` in %s."}\n' "$pack"
    exit 1
fi
exec "$python" "$FUGUE_NODE_DIR/find_by_text.py"
