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
<id>/inputs/          sample pictures its Load Image nodes name as inputs/<name>
```

- `category` is one of the ids in `categories.json`, which also orders the categories.
- What a template needs is read from its workflow, never written twice:
  - every model it names, by hash, with a `source` and a `size` in the workflow's
    `requires.models`: an https URL whose file has exactly that hash, and its bytes. Fugue
    offers to download a missing model into the folder it goes in, and keeps it only when the
    hash matches;
  - the node versions it was made with. A Fugue that lacks a built-in node, or has an older minor
    of it, does not list the template.
- No models in this repo. Sample pictures are small JPEGs made with Fugue itself.

## Adding one

1. Make the workflow in Fugue and save it. Put the pictures it loads in `<id>/inputs/` and point
   its Load Image nodes at `inputs/<name>`.
2. Add `template.json` and a preview (about 768 px wide, WebP).
3. Give each model in `requires.models` a `source` and a `size`. For a Hugging Face file,
   `curl -sI <source>` shows both checks: `x-linked-size` and `x-linked-etag` (the sha256).
4. Run `bin/check`, then `FUGUE_TEMPLATES=$PWD fugue template list` (no warnings) and
   `fugue validate <id>/workflow.fugue`.

CI runs the same checks, the last two against Fugue's main branch.
