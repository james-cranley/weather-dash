#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import logging
import time
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

HERE = os.path.dirname(os.path.realpath(__file__))

# Make local Waveshare library importable: ./lib/waveshare_epd
LIBDIR = os.path.join(HERE, "lib")
if os.path.exists(LIBDIR):
    sys.path.insert(0, LIBDIR)

GET_WEATHER = os.path.join(HERE, "get_weather.py")
RENDER = os.path.join(HERE, "render_dashboard.py")

DEFAULT_PREFIX = "dash"
BLACK_PNG = lambda prefix: os.path.join(HERE, f"{prefix}_black.png")
RED_PNG = lambda prefix: os.path.join(HERE, f"{prefix}_red.png")


def run_cmd(cmd: list[str]) -> str:
    """Run a command and return stdout; raise RuntimeError on failure."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed:\n{' '.join(cmd)}\n\nSTDERR:\n{p.stderr.strip()}")
    return p.stdout


def generate_dashboard(city: str, country: str, api_key: str | None, out_prefix: str) -> None:
    """
    Calls get_weather.py -> JSON, then pipes into render_dashboard.py.
    Produces {prefix}_black.png and {prefix}_red.png.
    """
    gw_cmd = [
        sys.executable, GET_WEATHER,
        "--city", city,
        "--country", country,
        "--format", "json",
    ]
    if api_key:
        gw_cmd += ["--api-key", api_key]

    logging.info("Fetching weather…")
    weather_json = run_cmd(gw_cmd)

    rd_cmd = [
        sys.executable, RENDER,
        "--out-prefix", out_prefix,
        # optional: pass country label so banner shows "UK" not "GB"
        "--country", country,
    ]

    logging.info("Rendering dashboard…")
    p = subprocess.run(rd_cmd, input=weather_json, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"render_dashboard.py failed:\n{p.stderr.strip()}")
    logging.info(p.stdout.strip())


def display_on_epaper(black_path: str, red_path: str, rotate_180: bool, sleep_after: bool) -> None:
    """
    Load two 1-bit PNGs and send them to Waveshare 2.13" tri-color (b) V4.
    """
    # Now import from local ./lib
    from waveshare_epd import epd2in13b_V4

    epd = epd2in13b_V4.EPD()
    logging.info("Init display…")
    epd.init()

    black = Image.open(black_path).convert("1")
    red = Image.open(red_path).convert("1")

    if rotate_180:
        black = black.rotate(180, expand=False)
        red = red.rotate(180, expand=False)

    # Landscape buffers expected: (epd.height, epd.width) == (250, 122)
    target_size = (epd.height, epd.width)
    if black.size != target_size:
        logging.warning(f"Resizing black from {black.size} to {target_size}")
        black = black.resize(target_size)
    if red.size != target_size:
        logging.warning(f"Resizing red from {red.size} to {target_size}")
        red = red.resize(target_size)

    logging.info("Updating panel… (full refresh)")
    epd.display(epd.getbuffer(black), epd.getbuffer(red))

    # Give the panel time to finish waveform update
    time.sleep(2)

    if sleep_after:
        logging.info("Sleep display…")
        epd.sleep()


def main():
    ap = argparse.ArgumentParser(
        description="Fetch weather, render dashboard, and update Waveshare 2.13\" b V4 e-paper."
    )
    ap.add_argument("--city", required=True, help='City or town name, e.g. "Cambridge"')
    ap.add_argument("--country", required=True, help='Country code/label, e.g. "UK"')
    ap.add_argument("--api-key", help="OpenWeather API key (overrides OPENWEATHER_API_KEY)")
    ap.add_argument("--prefix", default=DEFAULT_PREFIX, help=f"Output prefix (default: {DEFAULT_PREFIX})")
    ap.add_argument("--no-render", action="store_true", help="Skip rendering; just display existing PNGs")
    ap.add_argument("--rotate-180", action="store_true", help="Rotate output 180 degrees before displaying")
    ap.add_argument("--no-sleep", action="store_true", help="Do not put the display to sleep after update")
    args = ap.parse_args()

    # Prefer env var if not explicitly provided
    api_key = args.api_key or os.getenv("OPENWEATHER_API_KEY")

    black_path = BLACK_PNG(args.prefix)
    red_path = RED_PNG(args.prefix)

    try:
        if not args.no_render:
            generate_dashboard(args.city, args.country, api_key, args.prefix)

        if not (os.path.exists(black_path) and os.path.exists(red_path)):
            raise FileNotFoundError(f"Missing {black_path} or {red_path}. Did rendering succeed?")

        display_on_epaper(
            black_path=black_path,
            red_path=red_path,
            rotate_180=args.rotate_180,
            sleep_after=(not args.no_sleep),
        )

        logging.info("Done.")
    except KeyboardInterrupt:
        logging.info("Interrupted.")
        try:
            from waveshare_epd import epd2in13b_V4
            epd2in13b_V4.epdconfig.module_exit(cleanup=True)
        except Exception:
            pass
        sys.exit(130)
    except Exception as e:
        logging.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
