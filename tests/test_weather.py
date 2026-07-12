"""Weather adapter against mocked Open-Meteo — no network in tests."""

import httpx

from still.almanac import weather as weather_mod
from still.render.icons import WEATHER_ICONS, weather_icon

OK_RESPONSE = {
    "daily": {
        "weather_code": [2],
        "temperature_2m_max": [82.1],
        "temperature_2m_min": [63.6],
        "precipitation_probability_max": [20],
    },
}


def client_returning(response: httpx.Response) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: response))


def test_fetch_parses_and_rounds() -> None:
    w = weather_mod.fetch(
        40.7128, -74.006, "New York", client_returning(httpx.Response(200, json=OK_RESPONSE))
    )
    assert w is not None
    assert (w.high, w.low) == (82, 64)
    assert w.icon == "partly"
    assert w.condition == "Partly cloudy"
    assert w.label == "New York"
    assert w.precip_icon is None  # 20% precip prob is below 40% threshold


def test_fetch_returns_none_on_http_error() -> None:
    w = weather_mod.fetch(40.7128, -74.006, "New York", client_returning(httpx.Response(503)))
    assert w is None


def test_fetch_returns_none_on_malformed_body() -> None:
    w = weather_mod.fetch(
        40.7128, -74.006, "New York", client_returning(httpx.Response(200, json={"oops": 1}))
    )
    assert w is None


def test_wmo_code_buckets() -> None:
    assert weather_mod._CODE_TO_ICON[0] == "clear"
    assert weather_mod._CODE_TO_ICON[61] == "rain"
    assert weather_mod._CODE_TO_ICON[75] == "snow"
    assert weather_mod._CODE_TO_ICON[95] == "storm"


def test_unknown_code_falls_back_to_cloudy() -> None:
    resp = {
        "daily": {
            "weather_code": [7],  # 7 is not a real WMO code
            "temperature_2m_max": [55],
            "temperature_2m_min": [45],
            "precipitation_probability_max": [0],
        },
    }
    w = weather_mod.fetch(0, 0, "X", client_returning(httpx.Response(200, json=resp)))
    assert w is not None and w.icon == "cloudy"


def test_every_icon_key_has_svg() -> None:
    for key in set(weather_mod._CODE_TO_ICON.values()) | {"cloudy"}:
        assert "<svg" in WEATHER_ICONS[key]
    assert weather_icon("nonexistent") == WEATHER_ICONS["cloudy"]


def test_precip_icon_shown_when_precipitation_expected() -> None:
    # High precip probability, cold → snow
    resp_snow = {
        "daily": {
            "weather_code": [3],
            "temperature_2m_max": [30],
            "temperature_2m_min": [20],
            "precipitation_probability_max": [60],
        },
    }
    w = weather_mod.fetch(0, 0, "X", client_returning(httpx.Response(200, json=resp_snow)))
    assert w is not None and w.precip_icon == "snow"

    # High precip probability, mild → rain
    resp_rain = {
        "daily": {
            "weather_code": [3],
            "temperature_2m_max": [50],
            "temperature_2m_min": [40],
            "precipitation_probability_max": [60],
        },
    }
    w = weather_mod.fetch(0, 0, "X", client_returning(httpx.Response(200, json=resp_rain)))
    assert w is not None and w.precip_icon == "rain"


def test_precip_icon_absent_when_dry() -> None:
    resp = {
        "daily": {
            "weather_code": [0],
            "temperature_2m_max": [75],
            "temperature_2m_min": [55],
            "precipitation_probability_max": [10],
        },
    }
    w = weather_mod.fetch(0, 0, "X", client_returning(httpx.Response(200, json=resp)))
    assert w is not None and w.precip_icon is None
