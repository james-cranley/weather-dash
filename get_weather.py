#!/usr/bin/env python3
import os
import sys
import argparse
import json
import requests

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


def get_api_key(cli_key: str | None) -> str:
    if cli_key:
        return cli_key

    env_key = os.getenv("OPENWEATHER_API_KEY")
    if env_key:
        return env_key

    print(
        "Error: OpenWeather API key not provided.\n"
        "Set OPENWEATHER_API_KEY or pass --api-key.",
        file=sys.stderr,
    )
    sys.exit(1)


def fetch_weather(city: str, country: str, api_key: str) -> dict:
    params = {
        "q": f"{city},{country}",
        "appid": api_key,
        "units": "metric",
    }

    r = requests.get(OPENWEATHER_URL, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def format_text(data: dict) -> str:
    return (
        f"Location: {data['name']}, {data['sys']['country']}\n"
        f"Temperature: {data['main']['temp']:.1f} °C\n"
        f"Feels like: {data['main']['feels_like']:.1f} °C\n"
        f"Humidity: {data['main']['humidity']} %\n"
        f"Pressure: {data['main']['pressure']} hPa\n"
        f"Wind: {data['wind']['speed']} m/s\n"
        f"Conditions: {data['weather'][0]['description']}\n"
        f"Icon: {data['weather'][0]['icon']}"
    )


def format_json(data: dict) -> str:
    summary = {
        "location": {
            "city": data["name"],
            "country": data["sys"]["country"],
        },
        "temperature_c": data["main"]["temp"],
        "feels_like_c": data["main"]["feels_like"],
        "humidity_pct": data["main"]["humidity"],
        "pressure_hpa": data["main"]["pressure"],
        "wind_m_s": data["wind"]["speed"],
        "conditions": data["weather"][0]["description"],
        "icon": data["weather"][0]["icon"],  # <-- added for dashboard icon mapping
    }
    return json.dumps(summary, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Get current weather from OpenWeatherMap"
    )

    parser.add_argument("--city", required=True, help="City or town name")
    parser.add_argument("--country", required=True, help="Country code (e.g. UK)")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--api-key",
        help="OpenWeather API key (overrides OPENWEATHER_API_KEY)",
    )

    args = parser.parse_args()

    api_key = get_api_key(args.api_key)

    try:
        weather = fetch_weather(args.city, args.country, api_key)
    except requests.HTTPError as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        sys.exit(2)
    except requests.RequestException as e:
        print(f"Network error: {e}", file=sys.stderr)
        sys.exit(3)

    if args.format == "json":
        print(format_json(weather))
    else:
        print(format_text(weather))


if __name__ == "__main__":
    main()
