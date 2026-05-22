# xhs-cover-prompt

这是一个 Codex Skill，用来批量生成小红书封面上半部分主视觉，并把主视觉和标题合成进固定的 RockFlow 金融科技封面模板。

核心流程是：

1. 根据标题和正文生成上半部分财经科技主视觉 prompt。
2. 用真实生图模型生成 `upper_image`。
3. 手动按语义把标题拆成 1-3 行，标题文本不改写、不增删。
4. 用固定参考模板合成最终封面。
5. 校验固定模板区域没有被改动。

## 安装

通过 GitHub 安装为 Codex Skill：

```bash
codex skill install https://github.com/xueyuanhuang/xhs-cover-prompt
```

也可以手动放到 Codex skills 目录，例如：

```bash
~/.codex/skills/xhs-cover-prompt
```

## 依赖

```bash
pip install -r requirements.txt
```

仓库已经内置：

- `assets/templates/rockflow-fintech-cover/reference.jpg`
- `assets/templates/rockflow-fintech-cover/template.json`
- `assets/fonts/NotoSansCJKsc-Bold.otf`

所以合成步骤不依赖本机项目路径，也不依赖系统是否安装中文字体。

## 生成上图 Prompt

```bash
python3 scripts/render_prompt.py \
  --template rockflow-fintech-cover \
  --title "AI基建观察顺序：先看电力，再看存储和算力云" \
  --body "正文或主题内容" \
  --json
```

读取输出里的 `upper_visual`，把它交给生图模型生成上半部分主视觉图。

注意：这里生成的是封面上半部分图片，不是完整封面。不要让生图模型生成标题、logo、品牌区、底部紫色条或完整海报。

## 合成封面

```bash
python3 scripts/composite_rockflow_cover.py \
  --upper-image /path/to/upper-image.png \
  --title-line-1 "AI基建观察顺序：" \
  --title-line-2 "先看电力，" \
  --title-line-3 "再看存储和算力云" \
  --output /path/to/final-cover.png \
  --json
```

脚本会输出校验结果。关键字段必须为 `0`：

```json
{
  "changed_pixels_outside_allowed_boxes": 0
}
```

如果不是 `0`，说明固定模板区域被改动了，需要重跑或调整参数。

## 标题分行规则

标题是用户给定文案，不是可优化的广告文案。

- 只允许分行，不允许改写。
- 不允许增删任何字、词、数字、标点。
- `title_line_1 + title_line_2 + title_line_3` 必须等于原标题。
- 优先保持完整语义单元，例如产品名、人名、机构名、英文缩写、固定短语不要拆开。

## 批量生成建议

建议每批输出固定结构：

```text
upper_visuals/
rowXX_标题_cover.png
covers_batch_XX.zip
covers_batch_XX_contact_sheet.jpg
covers_batch_XX_manifest.json
```

每批收尾至少检查：

- 封面数量等于标题数量。
- `upper_visuals/` 里的上图数量等于标题数量。
- 每条标题分行合并后等于原标题。
- 每张封面尺寸正确。
- 每张封面的 `changed_pixels_outside_allowed_boxes` 都是 `0`。
- zip 里只包含最终封面，数量等于标题数量。

如果固定区域校验失败，先定位差异区域。若差异只在标题右侧边界附近，通常是标题溢出，可先尝试 `--font-size 96`，必要时再降到 `88`。不要扩大可变区域来掩盖标题溢出。

## 重要限制

- 不要把整张封面交给生图模型重画。
- 生图模型只能生成上半部分主视觉。
- 最终封面必须由参考模板合成得到。
- 程序化绘图、示意图、旧目录里的上图只能用于排查流程，不能作为合格的 `upper_image`。
- 合格的 `upper_image` 必须能追溯到用户提供的图片或真实生图输出。
