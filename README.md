# xhs-cover-prompt

Codex skill for generating Xiaohongshu cover visuals and compositing them into the fixed RockFlow fintech cover template.

The workflow is:

1. Generate an upper-half finance/technology visual from a title and body.
2. Manually split the title into 1-3 semantic lines without changing the text.
3. Composite the upper image and title into the bundled reference template.
4. Verify fixed template areas were not changed.

## Install

Install as a Codex skill from this repository:

```bash
codex skill install https://github.com/xueyuanhuang/xhs-cover-prompt
```

If installing manually, place this folder under your Codex skills directory, for example:

```bash
~/.codex/skills/xhs-cover-prompt
```

## Requirements

```bash
pip install -r requirements.txt
```

The repo includes:

- `assets/templates/rockflow-fintech-cover/reference.jpg`
- `assets/templates/rockflow-fintech-cover/template.json`
- `assets/fonts/NotoSansCJKsc-Bold.otf`

So the composite step does not depend on local project paths or system Chinese fonts.

## Generate Prompt

```bash
python3 scripts/render_prompt.py \
  --template rockflow-fintech-cover \
  --title "AI基建观察顺序：先看电力，再看存储和算力云" \
  --body "正文或主题内容" \
  --json
```

Use the `upper_visual` output as the prompt for image generation. The image generator should create only the upper-half main visual, not a full cover.

## Composite Cover

```bash
python3 scripts/composite_rockflow_cover.py \
  --upper-image /path/to/upper-image.png \
  --title-line-1 "AI基建观察顺序：" \
  --title-line-2 "先看电力，" \
  --title-line-3 "再看存储和算力云" \
  --output /path/to/final-cover.png \
  --json
```

The JSON output should report:

```json
{
  "changed_pixels_outside_allowed_boxes": 0
}
```

If the value is not `0`, the fixed template area changed. For title overflow near the right edge, retry with a smaller font size, for example `--font-size 96`.

## Notes

- Do not ask an image model to regenerate the whole cover.
- Only the upper image and title area should change.
- Programmatic placeholder drawings are not valid `upper_image` assets; use a user-provided image or a real image generation output.
