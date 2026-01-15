#!/usr/bin/env python3
import os
import sys
import json
import argparse
import subprocess
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# Waveshare 2.13" b V4 landscape canvas
W, H = 250, 122

HERE = os.path.dirname(os.path.realpath(__file__))
ICONS_DIR = os.path.join(HERE, "icons")


def load_font(paths, size):
    for p in paths:
        try:
            if p and os.path.exists(p):
                return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def text_bbox(draw, text, font):
    return draw.textbbox((0, 0), text, font=font)


def text_size(draw, text, font):
    x0, y0, x1, y1 = text_bbox(draw, text, font)
    return (x1 - x0, y1 - y0)


def fit_font_max(draw, text, max_w, max_h, font_paths, start_size, min_size=8):
    """
    Find the largest font size that fits within max_w and max_h.
    """
    size = start_size
    while size >= min_size:
        f = load_font(font_paths, size)
        w, h = text_size(draw, text, f)
        if w <= max_w and h <= max_h:
            return f
        size -= 1
    return load_font(font_paths, min_size)


def fit_font_width(draw, text, max_w, font_paths, start_size, min_size=10):
    size = start_size
    while size >= min_size:
        f = load_font(font_paths, size)
        if text_size(draw, text, f)[0] <= max_w:
            return f
        size -= 1
    return load_font(font_paths, min_size)


def read_weather_json(args) -> dict:
    if args.from_get_weather:
        cmd = [
            sys.executable,
            os.path.join(HERE, "get_weather.py"),
            "--city", args.city,
            "--country", args.country,
            "--format", "json",
        ]
        if args.api_key:
            cmd += ["--api-key", args.api_key]

        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"get_weather.py failed:\n{p.stderr.strip()}")
        return json.loads(p.stdout)

    if args.json_file:
        with open(args.json_file, "r", encoding="utf-8") as f:
            return json.load(f)

    raw = sys.stdin.read().strip()
    if not raw:
        raise RuntimeError("No JSON provided. Pipe JSON in, or use --json-file, or use --from-get-weather.")
    return json.loads(raw)


def load_icon(icon_key: str):
    if not icon_key:
        return None
    path = os.path.join(ICONS_DIR, f"{icon_key}.png")
    if not os.path.exists(path):
        return None
    return Image.open(path).convert("1")


def composite_preview(black_1bit: Image.Image, red_1bit: Image.Image) -> Image.Image:
    """RGB preview for normal screens."""
    preview = Image.new("RGB", (W, H), (255, 255, 255))
    pb = preview.load()
    b = black_1bit.load()
    r = red_1bit.load()

    for y in range(H):
        for x in range(W):
            if b[x, y] == 0:
                pb[x, y] = (0, 0, 0)
            elif r[x, y] == 0:
                pb[x, y] = (200, 0, 0)
    return preview


def render(data: dict, country_for_banner: str | None) -> tuple[Image.Image, Image.Image, Image.Image]:
    black = Image.new("1", (W, H), 255)
    red = Image.new("1", (W, H), 255)

    db = ImageDraw.Draw(black)
    dr = ImageDraw.Draw(red)

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]

    pad = 4

    # --- Banner: ~33% of height ---
    banner_h = int(round(H * 0.33))  # 122 -> 40
    banner_h = max(34, min(46, banner_h))  # clamp

    # Fill banner in red plane
    dr.rectangle((0, 0, W, banner_h), fill=0)

    # Banner left: location
    city = data.get("location", {}).get("city", "Unknown")
    banner_country = (country_for_banner or data.get("location", {}).get("country", "")).upper()
    left_text = f"{city}, {banner_country}"

    # Banner right: 2-line time/date, right aligned
    now = datetime.now()
    time_line = now.strftime("%H:%M")
    date_line = now.strftime("%Y-%m-%d")

    # Right block geometry
    right_block_max_w = int(W * 0.40) - pad * 2  # cap to avoid eating the banner
    right_block_max_h = banner_h - pad * 2
    line_gap = 4  # minimal; lets font get larger

    # Fit a single font size for both lines, constrained by width and total height
    best_font = load_font(font_candidates, 12)
    for size in range(34, 9, -1):
        f = load_font(font_candidates, size)
        tw, th = text_size(dr, time_line, f)
        dw, dh = text_size(dr, date_line, f)
        total_h = th + line_gap + dh
        max_w = max(tw, dw)
        if max_w <= right_block_max_w and total_h <= right_block_max_h:
            best_font = f
            break
    font_right = best_font

    # Compute right block dims with chosen font
    tw, th = text_size(dr, time_line, font_right)
    dw, dh = text_size(dr, date_line, font_right)
    right_w = max(tw, dw)
    right_h = th + line_gap + dh

    # Position right block: right aligned, vertically centered in banner
    rx = W - pad - right_w
    ry = (banner_h - right_h) // 2

    # Fit left text to remaining width (everything left of the right block minus a gap)
    gap_between = 6
    left_max_w = max(20, rx - pad - gap_between)
    font_left = fit_font_width(dr, left_text, left_max_w, font_candidates, start_size=22, min_size=12)
    lw, lh = text_size(dr, left_text, font_left)
    ly = (banner_h - lh) // 2

    # Draw banner text as white by knocking out red pixels (fill=255 on red plane)
    dr.text((pad, ly), left_text, font=font_left, fill=255)

    # Right block: two lines, right-aligned
    time_x = W - pad - tw
    date_x = W - pad - dw
    dr.text((time_x, ry), time_line, font=font_right, fill=255)
    dr.text((date_x, ry + th + line_gap), date_line, font=font_right, fill=255)

    # --- Content block (vertically centered in remaining white area) ---
    temp = data.get("temperature_c")
    feels = data.get("feels_like_c")
    humidity = data.get("humidity_pct")
    cond = data.get("conditions", "")
    icon_key = data.get("icon", "")

    # Temperature: big digits + smaller "°C"
    temp_num = f"{temp:.0f}" if isinstance(temp, (int, float)) else "--"
    temp_unit = "°C"

    line1 = f"Feels: {feels:.0f}°C" if isinstance(feels, (int, float)) else "Feels: --°C"
    line2 = f"Humid: {humidity:.0f}%" if isinstance(humidity, (int, float)) else "Humid: --%"

    if cond:
        cond = cond[:1].upper() + cond[1:]

    # Fonts
    font_temp_num = load_font(font_candidates, 46)
    # Start unit at ~half size of the digits
    unit_size = max(12, int(getattr(font_temp_num, "size", 46) * 0.5))
    font_temp_unit = load_font(font_candidates, unit_size)

    # Fit to max width: digits + unit
    max_temp_w = 125
    while getattr(font_temp_num, "size", 46) > 30:
        num_w, num_h = text_size(db, temp_num, font_temp_num)
        unit_w, unit_h = text_size(db, temp_unit, font_temp_unit)
        if (num_w + unit_w) <= max_temp_w:
            break
        font_temp_num = load_font(font_candidates, getattr(font_temp_num, "size", 46) - 2)
        font_temp_unit = load_font(font_candidates, max(12, int(getattr(font_temp_num, "size", 46) * 0.5)))

    font_small = load_font(font_candidates, 14)

    # Icon size
    icon_size = 60

    # Precompute layout to center vertically
    num_w, num_h = text_size(db, temp_num, font_temp_num)
    unit_w, unit_h = text_size(db, temp_unit, font_temp_unit)
    temp_w = num_w + unit_w
    temp_h = max(num_h, unit_h)

    metrics_top_offset = 8
    metrics_line_gap = 18
    cond_top_offset = 40

    metrics_y_rel = metrics_top_offset
    cond_y_rel = metrics_y_rel + cond_top_offset

    cond_font_guess = font_small
    cond_h_guess = text_size(db, cond or "", cond_font_guess)[1] if cond else 0

    content_h_est = max(temp_h, cond_y_rel + cond_h_guess, icon_size)

    avail_h = H - banner_h
    top = banner_h + max(0, (avail_h - content_h_est) // 2)

    # Draw temperature (big digits + small unit)
    db.text((pad, top), temp_num, font=font_temp_num, fill=0)
    # Raise the unit slightly so it looks better next to the large digits
    unit_x = pad + num_w
    unit_y = top + max(0, (num_h - unit_h) // 2) - 2
    db.text((unit_x, unit_y), temp_unit, font=font_temp_unit, fill=0)

    # Recompute in case fonts changed during fit loop
    num_w, num_h = text_size(db, temp_num, font_temp_num)
    unit_w, unit_h = text_size(db, temp_unit, font_temp_unit)
    temp_w = num_w + unit_w
    temp_h = max(num_h, unit_h)

    metrics_x = pad + temp_w + 10
    metrics_y = top + metrics_y_rel

    db.text((metrics_x, metrics_y), line1, font=font_small, fill=0)
    db.text((metrics_x, metrics_y + metrics_line_gap), line2, font=font_small, fill=0)

    if cond:
        max_cond_w = W - metrics_x - (icon_size + pad + 4)
        font_cond = fit_font_width(db, cond, max_cond_w, font_candidates, start_size=16, min_size=10)
        cond_y = top + cond_y_rel
        db.text((metrics_x, cond_y), cond, font=font_cond, fill=0)
        cond_h = text_size(db, cond, font_cond)[1]
        content_h = max(temp_h, cond_y_rel + cond_h, icon_size)
    else:
        content_h = max(temp_h, icon_size)

    # Refine vertical centering once (so cond font changes don't shift content oddly)
    refined_top = banner_h + max(0, (avail_h - content_h) // 2)
    if refined_top != top:
        db.rectangle((0, banner_h, W, H), fill=255)
        dr.rectangle((0, banner_h, W, H), fill=255)
        top = refined_top

        # Redraw temp
        db.text((pad, top), temp_num, font=font_temp_num, fill=0)
        num_w, num_h = text_size(db, temp_num, font_temp_num)
        unit_w, unit_h = text_size(db, temp_unit, font_temp_unit)
        temp_w = num_w + unit_w
        temp_h = max(num_h, unit_h)

        unit_x = pad + num_w
        unit_y = top + max(0, (num_h - unit_h) // 2) - 2
        db.text((unit_x, unit_y), temp_unit, font=font_temp_unit, fill=0)

        metrics_x = pad + temp_w + 10
        metrics_y = top + metrics_y_rel

        db.text((metrics_x, metrics_y), line1, font=font_small, fill=0)
        db.text((metrics_x, metrics_y + metrics_line_gap), line2, font=font_small, fill=0)

        if cond:
            max_cond_w = W - metrics_x - (icon_size + pad + 4)
            font_cond = fit_font_width(db, cond, max_cond_w, font_candidates, start_size=16, min_size=10)
            cond_y = top + cond_y_rel
            db.text((metrics_x, cond_y), cond, font=font_cond, fill=0)

    # Icon: vertically centered within content block, on the right
    icon = load_icon(icon_key)
    if icon:
        icon = icon.resize((icon_size, icon_size))
        ix = W - pad - icon_size
        iy = top + (content_h - icon_size) // 2

        red.paste(icon, (ix, iy))
        db.rectangle((ix, iy, ix + icon_size, iy + icon_size), fill=255)

    preview = composite_preview(black, red)
    return black, red, preview


def main():
    p = argparse.ArgumentParser(description="Render a 250x122 landscape dashboard from get_weather JSON.")
    p.add_argument("--json-file", help="Read JSON from file (otherwise stdin).")
    p.add_argument("--from-get-weather", action="store_true", help="Call get_weather.py internally.")
    p.add_argument("--city", help="City (required with --from-get-weather).")
    p.add_argument("--country", help="Country code/label (optional; helps banner show UK vs GB).")
    p.add_argument("--api-key", help="API key override (used only with --from-get-weather).")
    p.add_argument("--out-prefix", default="dash", help="Output prefix (default: dash).")
    args = p.parse_args()

    if args.from_get_weather and (not args.city or not args.country):
        print("Error: --from-get-weather requires --city and --country", file=sys.stderr)
        sys.exit(2)

    try:
        data = read_weather_json(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(3)

    black, red, preview = render(data, args.country)

    prefix = os.path.join(HERE, args.out_prefix)
    black_path = f"{prefix}_black.png"
    red_path = f"{prefix}_red.png"
    preview_path = f"{prefix}_preview.png"

    black.save(black_path)
    red.save(red_path)
    preview.save(preview_path)

    print("Wrote:")
    print(f"  {black_path}")
    print(f"  {red_path}")
    print(f"  {preview_path}")


if __name__ == "__main__":
    main()
