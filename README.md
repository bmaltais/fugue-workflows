# Fugue workflow templates

Ready-to-run workflows for [Fugue](https://github.com/bmaltais/fugue), listed in its window under
File > Browse templates and by `fugue template list`. Each Fugue release bundles this repo at a
pinned commit (the `templates` submodule), so a first run works offline.

## New templates without a release

Fugue follows `main` on its own, so a merged template reaches people without a Fugue release
(spec 11.10 in the fugue repo, `src/engine/template_feed.h`).

- **When.** Once after the window shows, and at most once in 6 hours (a failed try counts). `fugue template update`
  checks at once, whatever the setting says.
- **Setting.** Settings > General > Get new templates, on by default. Off: only the bundled templates and the
  person's own. Settings shows "Last checked" with the time, or the last error.
- **What it downloads.** It asks GitHub for the latest commit of `main` and its file list, then downloads only
  the files whose git blob sha it does not already have, and checks each against that sha. The new copy is built
  aside and switched in whole; any failure keeps the copy in use and shows no notice.
- **Limits.** Plain files only (no links, no submodules; dot files such as `.github` are left out), at most 50 MB per
  file, 200 MB and 5000 files in all. A list that breaks a limit refuses the whole update.
- **Which template wins, by id.** The person's own, then the fetched one, then the bundled one.
  - A fetched template that this Fugue cannot open (a node it lacks, an older node version, an unreadable
    `template.json` or workflow, no title) does not take its id: the bundled one of that id stays. A template
    that needs a newer Fugue is safe to merge.
  - While a fetched copy is in use, a bundled template whose id is not in it (deleted or renamed here) is hidden.
  - `categories.json` is taken from the fetched copy when it has one.
- **Who does not fetch on their own.** A `FUGUE_HOME` or `--home` root (scripts, tests), a development build of
  Fugue (its `templates` folder is the developer's own checkout), and any session with `FUGUE_TEMPLATES` set
  (it reads that folder only). `fugue template update` still works in a `FUGUE_HOME` root.
- **Nothing runs from the feed.** A pack a template carries still asks Install and Trust before anything of it runs.

What this means when you merge:

- **A merge reaches every user within hours.** Review it as a release.
- **Renaming a folder deletes the template for everyone**, and adds a new one. Ids are permanent.
- **An edit replaces the template everywhere**. Test an edit to a
  template that people use as carefully as a new one.

## A template

One folder per template; the folder's name is its id.

```
<id>/template.json    {"title", "description", "category", "tags": [...]}, and optionally "app", "preview", "poster", "source"
<id>/workflow.fugue   the workflow
<id>/preview.webp     what it makes (preview.png or .jpg also work)
<id>/preview.webm     optional: a moving preview (VP9, no audio, 640x640, a 3 to 4 s loop); template.json names it
                      ("preview": "preview.webm") and its still ("poster": "poster.png")
<id>/inputs/          sample pictures its Load Image nodes name as inputs/<name>, and a painted
                      mask's PNG (8-bit gray, white is redrawn) when a node has one
```

- `source` (optional) says where a workflow comes from: `{"name", "author", "url", "note"}`, each optional text, `url` starting
  `http://` or `https://`. The card says "Based on <name> by <author>" and links to the `url`. A field that is not as said, or an unknown one, is
  left out and is a warning of `fugue template list` (CI fails on warnings).
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
- No models in this repo. Sample pictures are small JPEGs.

## Adding one

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: export your workflow with File > Export for sharing…, and
either open a "Submit a template" issue with the file, or turn it into a folder with `bin/import-fuguepack` and open a
pull request. `bin/check-all` runs the checks CI runs.
