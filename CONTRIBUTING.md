# Contributing a template

You made a workflow in [Fugue](https://github.com/bmaltais/fugue) that others could use. Here is how to add it.
You do not need git for the first way.

A merged template reaches every Fugue user within hours (see the README), so a maintainer looks at each one.

## Way 1: no git, an issue

1. In Fugue, open your workflow. Run it once, so the package gets a picture of the result.
2. File > Export for sharing…. Fugue writes a `.fuguepack` file with your workflow and its sample pictures.
   No model is in it.
3. GitHub does not take `.fuguepack` files on an issue, but the file is a zip. Rename it to `my-template.zip`
   (or zip it) and it attaches fine. Fugue opens a renamed zip the same way.
4. Open a [Submit a template](../../issues/new?template=submit-template.yml) issue. Drag the zip in. Fill in the
   title, a description, the category, and the models it uses with a link to each. Drag in a preview picture too
   (PNG or JPEG), if the package has none.
5. A maintainer turns it into a folder with `bin/import-fuguepack` and opens the pull request. You can
   comment there.

## Way 2: a pull request

1. Fork this repo and clone it.
2. Start the folder, one of two ways:
   - From a package you exported: `bin/import-fuguepack my-template.fuguepack my-id --category edit`
   - From a workflow you saved: `bin/new-template my-id --from my.fugue --category edit`
     (without `--from` you get an empty folder to fill)

   Both copy the pictures your Load nodes use into `my-id/inputs/` and point the nodes at `inputs/<name>`. They
   print what is still missing.
3. Open `my-id/template.json` and fill in what says `TODO`.
4. Add a preview (below).
5. Run `bin/check-all`. Without a Fugue binary it runs the shape check only. With one it runs everything CI runs:
   `bin/check-all path/to/fugue` (also read from `$FUGUE`, `fugue` on your PATH, or `../fugue/build/fugue`).
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

### Preview

- `preview.webp` (or `.png` or `.jpg`), at most **300 KB**, about 768 px wide. It shows what the template makes.
- To make one from any picture: `magick result.png -resize 768x -quality 80 my-id/preview.webp`
  (ImageMagick), or use any image tool that writes WebP.
- A moving preview is optional: `preview.webm` (VP9, no audio, 640x640, a 3 to 4 second loop, at most 600 KB) with
  `"preview": "preview.webm"` and a `"poster": "poster.png"` in `template.json`. Keep the still preview as well.

### Sample inputs

- Each file in `inputs/` is at most **600 KB**. Small JPEGs are best.
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
before the person says Install and Trust. A `.fugueapp` export carries its packs, and `bin/import-fuguepack` copies them in. Otherwise copy
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

- CI: `bin/check-all` against Fugue's main branch. It runs `bin/check` (shape, sizes, models have a source and size),
  `fugue template list` (no warnings), `fugue validate` on every workflow, and every app block.
- A human look, because a merge reaches every user: does it run as described, are the models and licences honest,
  are the samples fine to publish, is the id one we want to keep for good.
