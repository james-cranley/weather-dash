#!/usr/bin/env python3
import os
import io
import requests
import numpy as np
from PIL import Image

ICON_IDS = [
    "01d","01n","02d","02n","03d","03n","04d","04n",
    "09d","09n","10d","10n","11d","11n","13d","13n",
    "50d","50n"
]

SRC_URL = "https://openweathermap.org/img/wn/{icon}@2x.png"
OUT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "icons")

def to_1bit_icon(png_bytes: bytes, white_cutoff: int = 250) -> Image.Image:
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    # Composite onto white background (remove transparency)
    white_bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    rgb = Image.alpha_composite(white_bg, img).convert("RGB")

    arr = np.array(rgb, dtype=np.uint8)  # (H, W, 3)

    # "Ink" if ANY channel is below cutoff (i.e. not extremely close to white)
    ink = np.any(arr < white_cutoff, axis=2)  # bool mask (H, W)

    # Convert to 1-bit: in mode "1", 0 is black, 255 is white
    out = Image.fromarray(np.where(ink, 0, 255).astype(np.uint8), mode="L").convert("1")
    return out

def trim_whitespace(bw: Image.Image, pad: int = 2) -> Image.Image:
    """
    Crop a 1-bit image to the bounding box of black pixels.
    Optionally add `pad` pixels of margin.
    """
    if bw.mode != "1":
        raise ValueError("Expected 1-bit image")

    # Invert: ink becomes white so getbbox() works
    inv = bw.convert("L").point(lambda p: 255 - p)

    bbox = inv.getbbox()
    if bbox is None:
        return bw  # nothing to trim

    left, top, right, bottom = bbox

    # Apply padding, clamped to image bounds
    left   = max(0, left - pad)
    top    = max(0, top - pad)
    right  = min(bw.width,  right + pad)
    bottom = min(bw.height, bottom + pad)

    return bw.crop((left, top, right, bottom))

def square_icon(bw: Image.Image) -> Image.Image:
    """
    Take a 1-bit trimmed icon and center it in a square canvas
    whose side length is max(width, height).
    """
    if bw.mode != "1":
        raise ValueError("Expected 1-bit image")

    w, h = bw.size
    side = max(w, h)

    # White square canvas
    sq = Image.new("1", (side, side), 1)  # 1 = white in mode "1"

    # Center paste
    x = (side - w) // 2
    y = (side - h) // 2
    sq.paste(bw, (x, y))

    return sq


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    for icon in ICON_IDS:
        url = SRC_URL.format(icon=icon)
        print(f"Downloading {icon} ...")

        r = requests.get(url, timeout=15)
        r.raise_for_status()

        bw = to_1bit_icon(r.content, white_cutoff=250)
        bw = trim_whitespace(bw, pad=3)
        bw = square_icon(bw)

        out_path = os.path.join(OUT_DIR, f"{icon}.png")
        bw.save(out_path)
        print(f"  -> saved {out_path}")

    print("\nDone. Icons are in ./icons as 1-bit PNGs.")

if __name__ == "__main__":
    main()
