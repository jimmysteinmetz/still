"""Weather module — Open-Meteo, no API key (spec §6).

One GET to Open-Meteo returns the current temperature, today's high/low, and a
WMO weather code (an integer, 0–99, standardized by the World Meteorological
Organization). We bucket that code into a handful of icon keys; the renderer
maps each key to a tiny monochrome SVG (see render/icons.py).

Compact by design: the whole forecast is current temp + hi/lo + one glyph.
Fails gracefully — a dead API returns None and the masthead ear collapses.
"""

import logging

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather-interpretation code → icon key. Ranges collapsed to buckets.
# Reference: https://open-meteo.com/en/docs (WMO Weather interpretation codes)
# Keep the bucket table compact and aligned, not one code per line:
# fmt: off
_CODE_TO_ICON: dict[int, str] = {
    0: "clear",
    1: "clear",
    2: "partly",
    3: "cloudy",
    45: "fog", 48: "fog",
    51: "rain", 53: "rain", 55: "rain",  # drizzle
    56: "rain", 57: "rain",              # freezing drizzle
    61: "rain", 63: "rain", 65: "rain",  # rain
    66: "rain", 67: "rain",              # freezing rain
    80: "rain", 81: "rain", 82: "rain",  # showers
    71: "snow", 73: "snow", 75: "snow", 77: "snow",
    85: "snow", 86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}
# fmt: on

_CONDITION: dict[str, str] = {
    "clear": "Clear",
    "partly": "Partly cloudy",
    "cloudy": "Cloudy",
    "fog": "Fog",
    "rain": "Rain",
    "snow": "Snow",
    "storm": "Thunderstorms",
}


class Weather(BaseModel):
    label: str  # location name, e.g. "New York"
    high: int  # today's high, °F
    low: int  # today's low, °F
    icon: str  # icon key (clear/partly/cloudy/fog/rain/snow/storm)
    condition: str  # human-readable condition
    precip_icon: str | None = None  # "rain" / "snow" if precip expected today


def fetch(lat: float, lng: float, label: str, client: httpx.Client) -> Weather | None:
    """Fetch today's general conditions, high/low, and precipitation probability."""
    try:
        resp = client.get(
            API_URL,
            params={
                "latitude": lat,
                "longitude": lng,
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max"
                ),
                "temperature_unit": "fahrenheit",
                "timezone": "auto",
                "forecast_days": 1,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        daily = data["daily"]
        icon = _CODE_TO_ICON.get(int(daily["weather_code"][0]), "cloudy")
        high = round(daily["temperature_2m_max"][0])
        low = round(daily["temperature_2m_min"][0])
        precip_prob = (daily.get("precipitation_probability_max") or [0])[0] or 0
        precip_icon = ("snow" if high <= 34 else "rain") if precip_prob >= 40 else None
        return Weather(
            label=label,
            high=high,
            low=low,
            icon=icon,
            condition=_CONDITION[icon],
            precip_icon=precip_icon,
        )
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        logger.warning("weather unavailable: %s", e)
        return None
