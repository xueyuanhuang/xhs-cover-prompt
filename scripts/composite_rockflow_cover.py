#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

try:
    from scipy import ndimage
except Exception:  # pragma: no cover - fallback for slimmer local environments
    ndimage = None


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = str(SKILL_DIR / "assets" / "templates" / "rockflow-fintech-cover" / "reference.jpg")
DEFAULT_FONT = str(SKILL_DIR / "assets" / "fonts" / "NotoSansCJKsc-Bold.otf")
FALLBACK_FONTS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
]


def parse_box(value):
    parts = [int(item.strip()) for item in value.split(",")]
    if len(parts) != 4:
        raise SystemExit(f"Expected box as left,top,right,bottom, got: {value}")
    left, top, right, bottom = parts
    if right <= left or bottom <= top:
        raise SystemExit(f"Invalid box: {value}")
    return left, top, right, bottom


def parse_color(value):
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise SystemExit(f"Expected color as #RRGGBB, got: {value}")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def auto_source_upper_box(image):
    arr = np.asarray(image.convert("RGB"))
    height, width = arr.shape[:2]
    luminance = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    white_fraction = np.mean(np.all(arr > 235, axis=2), axis=1)
    row_luminance = luminance.mean(axis=1)

    search_start = int(height * 0.35)
    search_end = int(height * 0.75)
    for y in range(search_start, search_end):
        if row_luminance[y] > 220 and white_fraction[y] > 0.45:
            return 0, 0, width, y
    return 0, 0, width, height


def dilate_mask(mask, iterations):
    if ndimage is not None:
        return ndimage.binary_dilation(mask, iterations=iterations)
    image = Image.fromarray((mask * 255).astype(np.uint8))
    for _ in range(iterations):
        image = image.filter(ImageFilter.MaxFilter(3))
    return np.asarray(image) > 0


def inpaint_masked_pixels(zone, mask):
    if not mask.any():
        return zone
    if ndimage is None:
        result = zone.copy()
        known_pixels = zone[~mask]
        fill = np.median(known_pixels, axis=0).astype(np.uint8) if len(known_pixels) else np.array([242, 242, 242], dtype=np.uint8)
        result[mask] = fill
        return result

    filled = zone.astype(np.float32)
    known = ~mask
    kernel = np.ones((3, 3), dtype=np.float32)
    for _ in range(260):
        if known.all():
            break
        next_filled = filled.copy()
        new_known = known.copy()
        for channel in range(3):
            values = filled[:, :, channel]
            sums = ndimage.convolve(values * known, kernel, mode="nearest")
            counts = ndimage.convolve(known.astype(np.float32), kernel, mode="nearest")
            update = (~known) & (counts > 0)
            next_filled[:, :, channel][update] = sums[update] / counts[update]
            new_known[update] = True
        filled = next_filled
        known = new_known
    result = zone.copy()
    result[mask] = np.clip(filled[mask], 0, 255).astype(np.uint8)
    return result


def clean_old_title(base, box):
    arr = np.asarray(base).copy()
    left, top, right, bottom = box
    zone = arr[top:bottom, left:right].copy()
    luminance = 0.299 * zone[:, :, 0] + 0.587 * zone[:, :, 1] + 0.114 * zone[:, :, 2]
    purple = (
        (zone[:, :, 0] > 95)
        & (zone[:, :, 2] > 135)
        & (zone[:, :, 1] < 135)
        & ((zone[:, :, 2] - zone[:, :, 1]) > 65)
    )
    black = luminance < 125
    mask = dilate_mask(purple | black, iterations=7)
    cleaned = inpaint_masked_pixels(zone, mask)
    arr[top:bottom, left:right] = cleaned
    output = Image.fromarray(arr)

    smooth = output.crop(box).filter(ImageFilter.GaussianBlur(radius=0.35))
    mask_image = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius=0.6))
    output.paste(smooth, (left, top), mask_image)
    return output, mask


def load_font(size, font_path, font_index):
    candidates = [Path(font_path), Path(DEFAULT_FONT)]
    candidates.extend(Path(item) for item in FALLBACK_FONTS)
    attempted = []
    for path in candidates:
        if not path.exists() or path in attempted:
            continue
        attempted.append(path)
        try:
            return ImageFont.truetype(str(path), size, index=font_index)
        except TypeError:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    raise SystemExit(
        "No usable Chinese font found. Provide one with --font, or keep "
        "assets/fonts/NotoSansCJKsc-Bold.otf with the skill."
    )


def changed_pixels_outside(reference, result, mutable_boxes):
    ref = np.asarray(reference.convert("RGB"))
    out = np.asarray(result.convert("RGB"))
    if ref.shape != out.shape:
        return None
    changed = np.any(ref != out, axis=2)
    mutable = np.zeros(changed.shape, dtype=bool)
    for left, top, right, bottom in mutable_boxes:
        mutable[top:bottom, left:right] = True
    return int((changed & ~mutable).sum())


def main():
    parser = argparse.ArgumentParser(
        description="Compose a RockFlow cover by preserving the reference image and replacing only the upper visual and title."
    )
    parser.add_argument("--reference-image", default=DEFAULT_REFERENCE)
    parser.add_argument("--upper-image", required=True, help="Generated upper visual image, or a generated full cover whose top image will be cropped.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--title-line-1", required=True)
    parser.add_argument("--title-line-2", required=True)
    parser.add_argument("--title-line-3", required=True)
    parser.add_argument("--target-image-box", default="0,7,1080,730")
    parser.add_argument("--source-upper-box", default="auto")
    parser.add_argument("--title-clean-box", default="40,820,1070,1215")
    parser.add_argument("--text-x", type=int, default=63)
    parser.add_argument("--line-y", default="842,955,1068")
    parser.add_argument("--font", default=DEFAULT_FONT)
    parser.add_argument("--font-index", type=int, default=0)
    parser.add_argument("--font-size", type=int, default=104)
    parser.add_argument("--purple", default="#9E54F3")
    parser.add_argument("--black", default="#000000")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    reference = Image.open(args.reference_image).convert("RGB")
    upper_source = Image.open(args.upper_image).convert("RGB")
    target_box = parse_box(args.target_image_box)
    title_box = parse_box(args.title_clean_box)
    source_box = auto_source_upper_box(upper_source) if args.source_upper_box == "auto" else parse_box(args.source_upper_box)
    line_y = [int(item.strip()) for item in args.line_y.split(",")]
    if len(line_y) != 3:
        raise SystemExit("--line-y must contain three comma-separated y positions.")

    result = reference.copy()
    target_width = target_box[2] - target_box[0]
    target_height = target_box[3] - target_box[1]
    upper = upper_source.crop(source_box)
    upper = ImageOps.fit(upper, (target_width, target_height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    result.paste(upper, (target_box[0], target_box[1]))

    result, _ = clean_old_title(result, title_box)
    draw = ImageDraw.Draw(result)
    font = load_font(args.font_size, args.font, args.font_index)
    purple = parse_color(args.purple)
    black = parse_color(args.black)
    draw.text((args.text_x, line_y[0]), args.title_line_1, font=font, fill=purple)
    draw.text((args.text_x, line_y[1]), args.title_line_2, font=font, fill=black)
    draw.text((args.text_x, line_y[2]), args.title_line_3, font=font, fill=purple)

    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output)

    changed_outside = changed_pixels_outside(reference, result, [target_box, title_box])
    report = {
        "output": str(output.resolve()),
        "reference_image": str(Path(args.reference_image).expanduser().resolve()),
        "upper_image": str(Path(args.upper_image).expanduser().resolve()),
        "source_upper_box": source_box,
        "target_image_box": target_box,
        "title_clean_box": title_box,
        "changed_pixels_outside_allowed_boxes": changed_outside,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else str(output.resolve()))


if __name__ == "__main__":
    main()
