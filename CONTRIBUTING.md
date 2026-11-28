# Contributing a template

You made a workflow in [Fugue](https://github.com/bmaltais/fugue) that others could use. Here is how to add it.
You do not need git for the first way.

A merged template reaches every Fugue user within hours (see the README), so a maintainer looks at each one.

## Way 1: no git, an issue

1. In Fugue, open your workflow. Run it once, so the package gets a picture of the result.
2. File > Export for sharing…. Fugue writes a `.fuguepack` file with your workflow and its sample pictures.
   No model is in it.
3. GitHub does not take `.fuguepack` files on an issue, but the file is a zip. Rename it to `my-template.zip`
   (or zip it) and it attaches fine.
4. Open a [Submit a template](../../issues/new?template=submit-template.yml) issue. Drag the zip in. Fill in the
   title, a description, the category, and the models it uses with a link to each. Drag in a preview picture too
   (PNG or JPEG), if the package has none.
5. A maintainer adds the `import` label. An Action (`.github/workflows/import-submission.yml`) downloads your zip, runs
   `bin/import-fuguepack` and `bin/check-all`, asks a model for an advisory review (when the repo has a key for it) and opens
   the pull request, or comments here with what to change. A person reads the pull request before it is merged. You can comment there.

## Way 2: a pull request

1. Fork this repo and clone it.
2. Start the folder, one of two ways:
   - From a package you exported: `bin/import-fuguepack my-template.fuguepack my-id --category edit --author <your GitHub login>`
   - From a workflow you saved: `bin/new-template my-id --from my.fugue --category edit`
     (without `--from` you get an empty folder to fill)

   `--author` marks it as a community template (below); `--issue <number>` is optional. `new-template` takes the same two flags.

   Both copy the pictures your Load nodes use into `my-id/inputs/` and point the nodes at `inputs/<name>`. They
   print what is still missing.
3. Open `my-id/template.json` and fill in what says `TODO`.
4. Add a preview (below).
5. Run `bin/check-all`. Without a Fugue binary it runs the shape check only. With one it runs everything CI runs:
   `bin/check-all path/to/fugue` (also read from `$FUGUE`, `fugue` on your PATH, or `../fugue/build/fugue`).
   CI checks against Fugue's `main` branch. An installed Fugue that is older may not list a template that uses a
   newer node: build Fugue from `main`, or let CI judge.
6. Push and open a pull request. CI runs the same checks.

## The rules

### Id and folder

The folder name is the id: lowercase letters, digits and dashes (`flux2-klein-9b-edit`). Name it for what it does.
**An id is permanent once merged.** Renaming a folder deletes the old template for everyone, so pick well.

### The files

```
my-id/template.json    title, description, category, tags (and optional app, preview, poster, source)
my-id/workflow.fugue   the workflow
my-id/preview.webp     what it makes (.png or .jpg also work)
my-id/inputs/          sample pictures, audio or video that its Load nodes name as inputs/<name>
my-id/packs/<pack id>/ a pack it needs, copied in (optional)
```

`template.json`:

- `title`: short, what a person looks for.
- `description`: what it makes, what it needs, in two sentences. Name a model licence restriction here (below).
- `category`: one id from `categories.json`: `image`, `edit`, `canvas`, `video`, `audio`, `upscale`, `text`.
- `tags`: a few words, a list of text.
- `source` (optional): where the workflow comes from, when it is not all yours:
  `{"name": "...", "author": "...", "url": "https://...", "note": "..."}`. Each field is optional. The card says "Based on
  name by author" and links to the `url`.

### Community templates

A template that comes from a contributor is marked in `template.json`:
`"community": {"author": "<GitHub login or name>", "issue": 12}` (`issue` is optional). `bin/import-fuguepack` writes it. In Fugue the card shows a
"Community · by <author>" badge (Fugue is still to show it; the file is already read and ignored without a warning).
What it means:

- It may use **built-in Fugue nodes only**: no pack, no `packs/` folder. Packs run code on every user's machine, so
  a template with a pack is added only by the maintainer, as the maintainer's own, with `bin/import-fuguepack --own-with-packs`
  (which marks nothing as community).
- `bin/check` fails a community template that has a pack node or a `packs/` folder. With a Fugue binary
  (`bin/check-all`) a node is built in when `fugue node list` lists it, or the workflow defines it as an embedded group;
  without a binary only the `fugue/` prefix is checked.
- `author` is plain text, `issue` (optional) a positive number.
- No `requires.packs`. Each model's `source` is `https://huggingface.co/<owner>/<repo>/resolve/<40-hex commit>/<path>` and the file
  is a `.safetensors` or a `.gguf`.
- A Save node's `name` and `folder` hold no `..` and do not start with `/`, `\` or `~` (Fugue refuses a `..` in a name, and a
  relative folder that leads out of the output folder, itself; an absolute folder is allowed there only by the write roots).
- A pull request from someone without write access (CI: `bin/check-pr-scope`) may only add a community template whose `author` is
  the pull request's author, or change one that already is theirs (same author at the base). Anything else, a deletion and a change
  outside the template folders included, is a maintainer's. CI judges it with the base branch's copy of the scripts, not the pull
  request's own.

### Preview

- `preview.webp` (or `.png` or `.jpg`), at most **300 KB**, about 768 px wide. It shows what the template makes.
- To make one from your own result picture: `cwebp -resize 768 0 -q 80 result.png -o my-id/preview.webp`
  (`cwebp` is part of libwebp and reads only PNG, JPEG, TIFF and WebP), or use any image tool that writes WebP.
- Maintainers: `bin/import-fuguepack` copies a package's preview only when its first bytes say PNG, JPEG or WebP and it is at
  most 300 KB. It never converts or decodes a picture. **Do not convert a stranger's file with ImageMagick**: its formats
  (MVG, SVG, EPS) can read files from your machine into the picture. Ask the contributor for a smaller PNG, or make a
  preview yourself by running the workflow.
- A moving preview is optional: `preview.webm` (VP9, no audio, 640x640, a 3 to 4 second loop, at most 600 KB) with
  `"preview": "preview.webm"` and a `"poster": "poster.png"` in `template.json`. Keep the still preview as well.

### Sample inputs

- Each file in `inputs/` is at most **600 KB**. Small JPEGs are best. Pictures must be real PNG, JPEG or WebP files, at most
  4096 x 4096 (and 16 megapixels), named by what they are (`.png` for a PNG): `bin/check` reads their structure (it never decodes them) and
  the import scripts copy only files that pass. A PNG has image data and only the usual chunks (text, gamma, colour profile, size,
  time, background, transparency; no private chunks, no APNG), a JPEG ends at its first end marker (at most 64 scans), a WebP is a plain VP8, VP8L or
  VP8X file with at most 64 frames (64 megapixels in all). Every file under `inputs/` (sub-folders too) is a picture, a known audio or video kind
  by its bytes, or a `.cube` colour table (ASCII, at most 2 MB), named by what it is; no GIF, SVG or unknown kind.
  A **community** template's samples are pictures only: a maintainer adds audio, video or a `.cube` by hand. No local paths in the workflow: a Load node names `inputs/<name>`.
- Make them with Fugue, or use a picture you have the right to share. No photos of other people without their
  consent, and no private pictures.
- If a node has a painted mask, its file goes in `inputs/` too (an 8-bit gray PNG, white is redrawn).

### Models

No model file goes in this repo. The workflow names each model by hash, and `requires.models` in `workflow.fugue`
gives each one a **`source`** (an https link to the file, which must have exactly that hash) and a **`size`** (bytes).
Fugue offers to download a missing model and keeps it only when the hash matches. `bin/check` fails on any model without both.

For a Hugging Face file, use the `resolve` link and read both values from the headers:

```
curl -sI https://huggingface.co/<owner>/<repo>/resolve/<commit>/<file>
```

`x-linked-size` is the size, and `x-linked-etag` is the sha256 (it must match the hash in the workflow).
Link to a commit (`resolve/<40-hex commit>/...`), not `main`, so the file cannot change under the hash.

**Licences.** Read the model's licence. If it limits use (non-commercial, research only, a gated download), say so in
the `description`. Do not add a template for a model you may not point people to.

### Packs

A template that needs a pack carries a copy as `my-id/packs/<pack id>/` (the pack folder without its tests), so
Fugue can offer to install it. Keep `requires.packs` in the workflow at the same version. Nothing of the pack runs
before the person says Install and Trust. A `.fugueapp` export carries its packs. `bin/import-fuguepack` refuses a package with packs unless a maintainer passes
`--own-with-packs`, then lists every file so it can be read before the pack is published. Otherwise copy
the pack folder from its repo or from `examples/packs/` in the fugue repo.

### Apps and canvas actions

If `workflow.fugue` has an `app` block, the template is also an app: Fugue shows a simple form with a Run button.
`template.json` must then say `"app": true` (the import scripts add it), and each picture input needs a sample in `inputs/`.
`bin/check-apps` checks this. A top-level `action` block makes it a canvas action; use category `canvas`.
Both are described in the README. Start from `edit-keep-the-rest` (app) or `generative-fill` (canvas action).

### Licence of your contribution

This repo is MIT (see `LICENSE`). By opening an issue or a pull request you agree that what you send is yours to share
and is released under it. If part of it comes from someone else, name them in `source` and say which licence applies.

### What review checks

- The import Action's pull request does not start CI (GitHub does not run workflows for a pull request made with the workflow's
  token); its `import` job ran `bin/check-all` and put the report in the pull request.
- CI: `bin/check-all` against Fugue's main branch. It runs `bin/check` (shape, sizes, models have a source and size),
  `fugue template list` (no warnings), `fugue validate` on every workflow, and every app block.
- A human look, because a merge reaches every user: does it run as described, are the models and licences honest,
  are the samples fine to publish, is the id one we want to keep for good.

### For maintainers: the import label

Adding the `import` label to a submission issue runs the Action. Before you add it, read the issue and open the zip yourself if
anything looks odd: the label is the only gate. The pull request records the zip's size and **sha256**; on the pull request, download
the attachment again from the issue and compare, because a contributor can edit the issue and swap the file after the Action ran.
Do not add `CLAUDE.md`, `.claude/` or `.mcp.json` to the repo root: the review job refuses to run with them, and an outside pull request that adds them fails the scope check. A pull request from outside that touches `.github/` or `bin/` is closed, not reviewed for merge (a fork can edit `check.yml` and show a false green).
The AI review is advisory and is dropped if it holds anything key-like. If the label is added again, the Action pushes a new branch
(`submission/<issue>-<id>-2`) and opens a new pull request; it never overwrites a branch.
