# Fugue workflow templates

Ready-to-run workflows for [Fugue](https://github.com/bmaltais/fugue), listed in its window under
File > Browse templates and by `fugue template list`. Each Fugue release bundles this repo at a
pinned commit (the `templates` submodule), so the templates work offline.

## A template

One folder per template; the folder's name is its id.

```
<id>/template.json    {"title", "description", "category", "tags": [...]}
<id>/workflow.fugue   the workflow
<id>/preview.webp     what it makes (preview.png or .jpg also work)
<id>/preview.webm     optional: a moving preview (VP9, no audio, 640x640, a 3 to 4 s loop); template.json names it
                      ("preview": "preview.webm") and its still ("poster": "poster.png")
<id>/inputs/          sample pictures its Load Image nodes name as inputs/<name>, and a painted
                      mask's PNG (8-bit gray, white is redrawn) when a node has one
```

- `category` is one of the ids in `categories.json`, which also orders the categories.
- A template whose `workflow.fugue` has a top-level `action` block is also a **canvas action**: the Canvas view's
  task bar lists it (category `canvas`, by convention). The block names the inputs the canvas fills in (design:
  `docs/canvas-actions-design.md` in the fugue repo); `generative-fill` is the model (`harmonize` is a second: its prompt is optional and its selection too; `refine`, `remove` and `expand` follow, Expand with `selection: "bounds"`: the bar grows the canvas first). It is part of the workflow
  file, so it travels with every copy; it opens from Browse templates as a plain workflow too.
- A template whose `workflow.fugue` has a top-level `app` block is also an **app**: Fugue's App view shows the block's
  inputs as one simple form with a Run button, and `fugue app info|run <id>` reads it (spec 4.9 and 11.10 in the fugue repo).
  `template.json` may carry `"app": {"title", "summary", "kind"}` for the card (`true` takes them from the block, `false`
  keeps a block out of the Apps). One input list serves the `action` block and the `app` block alike: roles `image`, `prompt`,
  `seed`, `model`, a plain `name` for the rest, `section: "Advanced"` for what a hobbyist leaves alone. The apps are
  `remove-background`, `image-upscale`, `flux2-klein-9b-da-restore` (Restore) and `outpaint` (Expand). An app is the template's own
  workflow, so it still opens as a graph; `bin/check-apps` makes sure every block reads.
- What a template needs is read from its workflow, never written twice:
  - every model it names, by hash, with a `source` and a `size` in the workflow's
    `requires.models`: an https URL whose file has exactly that hash, and its bytes. Fugue
    offers to download a missing model into the folder it goes in, and keeps it only when the
    hash matches;
  - the node versions it was made with. A Fugue that lacks a built-in node, or has an older minor
    of it, does not list the template.
- A template that needs a pack carries it as `<id>/packs/<pack id>/` (a copy of the pack folder without its tests),
  so the window can offer to install it; `remove-background` and `pose-from-description-keep-background` carry `io.github.bmaltais.fugue-remove-background`, `flux2-klein-9b-da-edit-depth` carries `io.github.bmaltais.fugue-depth`,
  copied from `examples/packs/` in the fugue repo. Copy it again when the pack changes, and keep `requires.packs`
  at the same version.
- No models in this repo. Sample pictures are small JPEGs made with Fugue itself.

## Adding one

1. Make the workflow in Fugue and save it. Put the pictures it loads in `<id>/inputs/` and point
   its Load Image nodes at `inputs/<name>`.
2. Add `template.json` and a preview (about 768 px wide, WebP).
3. Give each model in `requires.models` a `source` and a `size`. For a Hugging Face file,
   `curl -sI <source>` shows both checks: `x-linked-size` and `x-linked-etag` (the sha256).
4. Run `bin/check`, then `bin/check-apps <fugue binary>` (when it has an `app` block), then `FUGUE_TEMPLATES=$PWD fugue template list` (no warnings) and
   `bin/validate-all <fugue binary>` (every workflow validates; a node of a pack the template carries in `packs/` is allowed, since CI cannot install and trust packs).

CI runs the same checks, the last two against Fugue's main branch.
