#!/usr/bin/env python3
import argparse
import json
import os
import re
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
FALLBACK_TEMPLATES_DIR = SKILL_DIR / "assets" / "templates"


def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def template_search_dirs(templates_dir=""):
    dirs = []
    if templates_dir:
        dirs.append(Path(templates_dir).expanduser())
    env_dir = os.environ.get("XHS_COVER_TEMPLATE_DIR", "")
    if env_dir:
        dirs.append(Path(env_dir).expanduser())
    dirs.extend([Path.cwd() / "xhs-cover-templates", FALLBACK_TEMPLATES_DIR])

    seen = set()
    unique_dirs = []
    for item in dirs:
        resolved = item.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_dirs.append(resolved)
    return unique_dirs


def load_template_file(path):
    with path.open("r", encoding="utf-8") as file:
        template = json.load(file)
    template["_path"] = str(path)
    template["_dir"] = str(path.parent)
    return template


def template_files_from_dir(directory):
    files = []
    direct = directory / "template.json"
    if direct.exists():
        files.append(direct)
    files.extend(sorted(directory.glob("*/template.json")))
    files.extend(path for path in sorted(directory.glob("*.json")) if path.name != "template.json")
    return files


def load_templates(search_dirs):
    templates = []
    seen_paths = set()
    seen_ids = set()
    for directory in search_dirs:
        if not directory.exists():
            continue
        for path in template_files_from_dir(directory):
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            template = load_template_file(resolved)
            template_id = template.get("id")
            if template_id and template_id in seen_ids:
                continue
            if template_id:
                seen_ids.add(template_id)
            templates.append(template)
    return templates


def list_templates(search_dirs):
    return [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "description": item.get("description", ""),
            "reference_image": item.get("reference_image", ""),
            "template_path": item.get("_path", ""),
        }
        for item in load_templates(search_dirs)
    ]


def find_template(template_id, search_dirs):
    if template_id:
        path = Path(template_id).expanduser()
        if path.exists():
            template_path = path / "template.json" if path.is_dir() else path
            if not template_path.exists():
                raise SystemExit(f"Template path does not contain template.json: {path}")
            return load_template_file(template_path.resolve())

    templates = load_templates(search_dirs)
    if not templates:
        raise SystemExit("No templates found.")
    if not template_id:
        return templates[0]
    for template in templates:
        if template.get("id") == template_id or template.get("name") == template_id:
            return template
    ids = ", ".join(item.get("id", "<missing>") for item in templates)
    raise SystemExit(f"Template not found: {template_id}. Available: {ids}")


def template_from_prompt_file(prompt_file, reference_image):
    prompt_path = Path(prompt_file).expanduser().resolve()
    if not prompt_path.exists():
        raise SystemExit(f"Prompt file not found: {prompt_path}")
    return {
        "id": "custom-prompt-file",
        "name": prompt_path.stem,
        "description": "用户指定的模板 prompt 文件",
        "reference_image": reference_image,
        "prompt": prompt_path.read_text(encoding="utf-8"),
        "variables": {},
        "_path": str(prompt_path),
        "_dir": str(prompt_path.parent),
    }


def token_visual_width(token):
    width = 0.0
    for char in token:
        if char.isspace():
            width += 0.35
        elif re.match(r"[A-Za-z0-9]", char):
            width += 0.62
        elif char in "，,。.!！?？：:；;、":
            width += 0.45
        else:
            width += 1.0
    return width


def title_tokens(text):
    return re.findall(r"[A-Za-z0-9]+(?:[\u4e00-\u9fff]{1,3})?|\s+|.", text, flags=re.S)


def choose_title_line_count(text):
    width = token_visual_width(text)
    if width <= 8:
        return 1
    return 3


def split_title_exact(text, line_count):
    tokens = title_tokens(text)
    total_width = sum(token_visual_width(token) for token in tokens)
    target_width = total_width / line_count if line_count else total_width
    best_lines = None
    best_cost = float("inf")

    def split_cost(lines):
        widths = [token_visual_width(line) for line in lines]
        cost = sum((width - target_width) ** 2 for width in widths)
        for line in lines:
            if not line:
                cost += 1000
                continue
            if line[0].isspace() or line[-1].isspace():
                cost += 20
            if line[0] in "，,。.!！?？：:；;、":
                cost += 80
            if line[0] in "的了啦":
                cost += 30
        return cost

    if line_count <= 1:
        best_lines = [text]
    elif line_count == 2:
        for first_cut in range(1, len(tokens)):
            candidate = ["".join(tokens[:first_cut]), "".join(tokens[first_cut:])]
            cost = split_cost(candidate)
            if cost < best_cost:
                best_cost = cost
                best_lines = candidate
    else:
        for first_cut in range(1, len(tokens) - 1):
            for second_cut in range(first_cut + 1, len(tokens)):
                candidate = [
                    "".join(tokens[:first_cut]),
                    "".join(tokens[first_cut:second_cut]),
                    "".join(tokens[second_cut:]),
                ]
                cost = split_cost(candidate)
                if cost < best_cost:
                    best_cost = cost
                    best_lines = candidate

    lines = best_lines or [text]
    lines.extend([""] * (3 - len(lines)))
    return lines[:3]


def split_title(title):
    original = str(title or "").strip()
    if not original:
        return ["封面标题", "", ""]

    explicit_lines = [line.strip() for line in re.split(r"[\r\n]+", original) if line.strip()]
    if len(explicit_lines) >= 2:
        if len(explicit_lines) > 3:
            explicit_lines = explicit_lines[:2] + ["".join(explicit_lines[2:])]
        explicit_lines.extend([""] * (3 - len(explicit_lines)))
        return explicit_lines[:3]

    line_count = choose_title_line_count(original)
    lines = split_title_exact(original, line_count)
    if "".join(lines) != original:
        raise SystemExit("Title split changed the title text; refusing to render.")
    return lines


def includes_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def build_fintech_upper_visual(title, body, focus=""):
    focus_sentence = f"\n\n可优先纳入的核心视觉对象：{focus}" if focus else ""
    return (
        "请生成一张用于小红书财经科技封面上半部分的主视觉图，不要生成完整封面，不要出现标题文字、logo、"
        "品牌标识、真实 UI、可读数字或可读图表。\n\n"
        f"主题标题：{title}\n\n"
        f"内容背景：{body}"
        f"{focus_sentence}\n\n"
        "请先从标题和正文中提炼 3-5 个核心视觉对象，例如：行业资产、资金流向、风险变量、基础设施、"
        "市场指标、企业经营场景等。然后把这些对象组合成一个高端财经科技编辑视觉。\n\n"
        "画面风格固定为：深色专业金融科技场景，真实感高级数字插画或电影感商业摄影质感，深海军蓝、"
        "青蓝色、亮紫色为主色，少量金色线条表达资金流、资本开支或价值流动。构图干净、聚焦、"
        "适合作为竖版小红书封面的上半部分主视觉，横向裁切，上方和中部有视觉重点，"
        "下方可以略暗以便衔接白色标题区。\n\n"
        "画面应表达“复杂市场问题被结构化分析”的感觉，而不是营销海报。可以使用抽象金融图表、数据流、"
        "服务器、芯片、城市金融区、会议室、研究桌面、产业设施等元素，但所有图表都必须不可读，"
        "不能出现任何文字、数字、股票代码或真实品牌。\n\n"
        "输出：只生成主视觉图片。"
    )


def build_upper_visual(title, body):
    original = f"{title}\n{body}"
    lower = original.lower()
    if includes_any(original, ["HBM", "DRAM", "DDR5", "SSD", "存储", "内存", "Memory", "芯片", "晶圆", "半导体"]):
        return build_fintech_upper_visual(
            title,
            body,
            "HBM 堆叠存储芯片、GPU/AI 加速器封装、数据中心机柜、DDR5 内存条、企业级 SSD、"
            "晶圆厂或洁净室抽象轮廓、供需周期波动、金色资金流。"
        )
    if includes_any(original, ["AI泡沫", "泡沫", "数据中心", "云厂商", "capex", "Capex", "资本开支", "电力", "推理"]):
        return build_fintech_upper_visual(
            title,
            body,
            "AI 数据中心服务器、GPU/AI 芯片、云基础设施、电力瓶颈、资本开支流线、收入转化或利用率的抽象图形。"
        )
    if includes_any(original, ["导演", "电影", "视频", "Sora", "Runway", "Veo", "Flick", "创作者", "分镜"]):
        return "一个 AI 电影创作者的工作室场景：一位年轻创作者坐在桌前，面前有笔记本电脑、分镜草图、电影镜头参考图、摄像机、小型补光灯和散落的创作便签。画面中有几束半透明的 AI 光影从电脑中延展出来，像是在把脑海里的画面转化成电影分镜和影像片段。背景有柔和的暗色工作室环境和一点电影片场灯光，整体表达“AI 帮创作者把灵感拍成电影”。不要出现任何文字、真实 UI、品牌 logo 或可读界面。风格真实商务摄影结合轻微科技感，干净、高级、有创作者气质。"
    if includes_any(original, ["创业", "MVP", "Founder", "创始人", "融资", "投资人", "验证"]):
        return "一个 AI 原生创业验证场景：深夜办公室里，一位年轻创始人坐在桌前，神情疲惫但冷静专注，面前有笔记本电脑、原型草图、用户访谈记录、便签和投资人评审材料。周围有几个半透明的 AI agent 光影正在协助整理信息，但画面不出现任何文字或真实 UI。窗外是安静城市夜景，室内为冷暖对比光，整体表达“AI 可以加速执行，但真正关键是验证问题、判断方向、证明用户需求”。"
    if includes_any(original, ["CFO", "现金流", "流动性", "Treasury", "FP&A", "DSO", "DPO", "AP aging", "Capex", "现金转换周期"]):
        return "一个冷静专业的企业现金流管理场景：深色办公室里，财务负责人和分析师面对抽象的现金预测仪表盘、滚动趋势图、付款节奏看板和几份财务资料。画面强调“流动性可见度、差异解释、经营驱动因素追踪”，不要出现任何可读文字、真实数字、品牌 logo 或真实 UI。整体真实商务摄影质感，带轻微金融科技感。"
    if includes_any(original, ["美股", "13F", "财报", "仓位", "投资", "基金", "股票", "估值"]):
        return "一个冷静专业的投资研究场景：一位年轻分析师坐在深色办公桌前，面前有多屏数据图表、财报材料、研究笔记和资产配置草稿，背景是暗色金融研究室和城市夜景。画面强调“研究、判断、风险管理”，不要出现任何可读文字、真实股票代码、品牌 logo 或 UI 界面。整体真实摄影质感，带轻微金融科技感。"
    if includes_any(original, ["护肤", "抗老", "面霜", "胶原", "成分", "618"]):
        return "一个高端护肤成分研究场景：干净的实验室台面上摆放精致护肤品瓶罐、成分样本、柔和补光和浅色背景，一位年轻女性研究员正在观察产品质地。整体表达“理性成分选择和长期护肤投资”，不要出现文字、品牌 logo 或可读包装。画面清爽、高级、专业。"
    if includes_any(original, ["期权", "交易", "IV", "波动率", "sell put", "covered call"]):
        return "一个期权交易复盘场景：一位冷静的交易者坐在桌前，面前是多屏抽象波动曲线、风险表格、交易日志和咖啡杯。画面不出现可读数字、股票代码或真实 UI，只保留抽象金融图形和光影。整体表达“纪律、复盘、风控”，真实摄影质感，专业克制。"
    if "港股" in lower or "ipo" in lower or "基石" in lower:
        return "一个港股 IPO 投资决策场景：会议室里几位投资人围坐在长桌旁，桌面有项目材料、合规文件、笔记本电脑和城市金融区窗景。画面强调“机构配售、关系网络、合规判断”，不出现任何可读文字、公司 logo 或真实文件内容。风格专业、克制、金融科技感。"
    return build_fintech_upper_visual(title, body)


def auto_kind(name):
    compact = re.sub(r"[\s_-]", "", name.lower())
    if compact in {"uppervisual", "mainvisual"} or name in {"主视觉", "上半部分主视觉", "主视觉描述"}:
        return "upper_visual"
    if compact in {"titleline1", "title1"} or name in {"标题第1行", "标题第一行", "第一行标题", "标题1"}:
        return "title_line_1"
    if compact in {"titleline2", "title2"} or name in {"标题第2行", "标题第二行", "第二行标题", "标题2"}:
        return "title_line_2"
    if compact in {"titleline3", "title3"} or name in {"标题第3行", "标题第三行", "第三行标题", "标题3"}:
        return "title_line_3"
    if compact in {"highlightterms", "highlight"} or name in {"高亮词", "重点词"}:
        return "highlight_terms"
    if compact == "title" or name == "标题":
        return "title"
    if compact == "body" or name == "正文":
        return "body"
    return ""


def extract_variables(prompt):
    names = []
    seen = set()
    for match in re.finditer(r"{{\s*([^{}]+?)\s*}}", prompt):
        name = clean(match.group(1)).replace("{", "").replace("}", "")
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def parse_vars(values):
    parsed = {}
    for item in values or []:
        if "=" not in item:
            raise SystemExit(f"--var expects name=value, got: {item}")
        name, value = item.split("=", 1)
        parsed[clean(name)] = value
    return parsed


def render_prompt(template, title, body, manual_vars):
    prompt_template = template.get("prompt", "")
    title_lines = split_title(title)
    context = {
        "title": title,
        "body": body,
        "upper_visual": build_upper_visual(title, body),
        "title_line_1": title_lines[0],
        "title_line_2": title_lines[1],
        "title_line_3": title_lines[2],
        "highlight_terms": "首行和末行" if title_lines[2] else "首行",
    }
    definitions = template.get("variables", {})
    variables = {}
    for name in extract_variables(prompt_template):
        definition = definitions.get(name, {})
        kind = auto_kind(name) or name
        mode = definition.get("mode", "auto" if kind in context else "manual")
        if name in manual_vars:
            value = manual_vars[name]
        elif mode == "auto" and kind in context:
            value = context[kind]
        else:
            value = definition.get("defaultValue", "")
        variables[name] = {"mode": mode, "value": value}

    def replace(match):
        name = clean(match.group(1)).replace("{", "").replace("}", "")
        return variables.get(name, {}).get("value", "") if name in variables else match.group(0)

    prompt = re.sub(r"{{\s*([^{}]+?)\s*}}", replace, prompt_template)
    reference = template.get("reference_image", "")
    reference_path = ""
    if reference:
        raw_reference = Path(reference).expanduser()
        if raw_reference.is_absolute():
            reference_path = str(raw_reference.resolve())
        else:
            template_dir = Path(template.get("_dir", SKILL_DIR))
            candidate = (template_dir / raw_reference).resolve()
            fallback = (SKILL_DIR / raw_reference).resolve()
            reference_path = str(candidate if candidate.exists() else fallback)
    return {
        "template": {
            "id": template.get("id"),
            "name": template.get("name"),
            "description": template.get("description", ""),
        },
        "reference_image_path": reference_path,
        "variables": variables,
        "prompt": prompt,
    }


def main():
    parser = argparse.ArgumentParser(description="Render an XHS cover prompt from a saved template.")
    parser.add_argument("--list-templates", action="store_true")
    parser.add_argument("--templates-dir", default="")
    parser.add_argument("--template", default="")
    parser.add_argument("--prompt-file", default="")
    parser.add_argument("--reference-image", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--body", default="")
    parser.add_argument("--body-file", default="")
    parser.add_argument("--var", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    search_dirs = template_search_dirs(args.templates_dir)

    if args.list_templates:
        data = {
            "template_dirs": [str(item) for item in search_dirs if item.exists()],
            "templates": list_templates(search_dirs),
        }
        print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else data)
        return

    body = args.body
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    if not args.title or not body:
        raise SystemExit("--title and --body/--body-file are required unless --list-templates is used.")

    if args.prompt_file:
        if not args.reference_image:
            raise SystemExit("--reference-image is required when --prompt-file is used.")
        template = template_from_prompt_file(args.prompt_file, args.reference_image)
    else:
        template = find_template(args.template, search_dirs)
        if args.reference_image:
            template["reference_image"] = args.reference_image

    data = render_prompt(template, args.title, body, parse_vars(args.var))
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(data["prompt"])


if __name__ == "__main__":
    main()
