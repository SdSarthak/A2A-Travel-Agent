import pytest
import requests
from python_a2a import TaskState

import WeatherAgent as weather_module

GEO_PAYLOAD = {
    "results": [
        {"latitude": 48.85, "longitude": 2.35, "name": "Paris", "country": "France"}
    ]
}

FORECAST_PAYLOAD = {
    "current": {
        "temperature_2m": 72.1,
        "relative_humidity_2m": 65,
        "wind_speed_10m": 8.0,
        "wind_direction_10m": 270,
        "weather_code": 1,
    },
    "daily": {
        "time": ["2025-06-21", "2025-06-22"],
        "temperature_2m_max": [75.0, 78.0],
        "temperature_2m_min": [58.0, 60.0],
        "precipitation_sum": [0.0, 0.1],
        "wind_speed_10m_max": [12.0, 10.0],
        "weather_code": [2, 61],
    },
    "hourly": {
        "time": ["2025-06-21T08:00", "2025-06-21T09:00"],
        "temperature_2m": [60.0, 62.0],
        "precipitation": [0.0, 0.0],
        "weather_code": [0, 2],
    },
}


@pytest.fixture
def agent():
    return weather_module.WeatherAgent()


@pytest.fixture
def fake_api(monkeypatch, stub_response):
    """Route geocoding and forecast calls to canned payloads."""
    calls = []

    def fake_get(url, params=None, **kwargs):
        calls.append((url, params or {}))
        if "geocoding" in url:
            return stub_response(GEO_PAYLOAD)
        return stub_response(FORECAST_PAYLOAD)

    monkeypatch.setattr(weather_module.requests, "get", fake_get)
    return calls


class TestWeatherDescriptions:
    def test_known_code(self, agent):
        assert agent._get_weather_description(0) == "Clear sky"
        assert agent._get_weather_description(95) == "Thunderstorm"

    def test_unknown_code(self, agent):
        assert agent._get_weather_description(1234) == "Weather code: 1234"

    def test_missing_code(self, agent):
        assert agent._get_weather_description(None) == "Unknown"
        assert agent._get_weather_description("N/A") == "Unknown"


class TestFormatting:
    def test_value_at_handles_short_series(self, agent):
        assert agent._value_at({"temperature_2m_max": [1.0]}, "temperature_2m_max", 5) == "N/A"
        assert agent._value_at({}, "missing", 0) == "N/A"

    def test_format_date_falls_back(self, agent):
        assert agent._format_date("not-a-date", "%A") == "not-a-date"

    def test_report_contains_all_sections(self, agent):
        report = agent._format_weather_response(
            FORECAST_PAYLOAD, "Paris", "France", True, True, True
        )
        assert "Weather forecast for Paris, France" in report
        assert "CURRENT CONDITIONS:" in report
        assert "Conditions: Mainly clear" in report
        assert "DAILY FORECAST:" in report
        assert "Conditions: Slight rain" in report
        assert "HOURLY FORECAST" in report

    def test_hourly_omitted_when_not_requested(self, agent):
        report = agent._format_weather_response(
            FORECAST_PAYLOAD, "Paris", "France", True, True, False
        )
        assert "HOURLY FORECAST" not in report


class TestGetWeather:
    def test_happy_path(self, agent, fake_api):
        report = agent.get_weather("Paris", forecast_days=2)
        assert "Weather forecast for Paris, France" in report
        forecast_call = fake_api[-1]
        assert forecast_call[1]["forecast_days"] == 2
        assert forecast_call[1]["temperature_unit"]

    def test_forecast_days_clamped(self, agent, fake_api):
        agent.get_weather("Paris", forecast_days=99)
        assert fake_api[-1][1]["forecast_days"] == 16

    def test_unknown_location(self, agent, monkeypatch, stub_response):
        monkeypatch.setattr(
            weather_module.requests, "get", lambda *a, **kw: stub_response({"results": []})
        )
        assert "Could not find coordinates" in agent.get_weather("Atlantis")

    def test_network_error_is_reported(self, agent, monkeypatch):
        def boom(*args, **kwargs):
            raise requests.ConnectionError("offline")

        monkeypatch.setattr(weather_module.requests, "get", boom)
        assert "Error looking up location" in agent.get_weather("Paris")


class TestHandleTask:
    def test_weather_query_completes(self, agent, fake_api, make_task):
        task = agent.handle_task(make_task("What's the weather in Paris?"))
        assert task.status.state == TaskState.COMPLETED
        assert "Weather forecast for Paris" in task.artifacts[0]["parts"][0]["text"]

    def test_google_format_query_completes(self, agent, fake_api, make_task):
        task = agent.handle_task(make_task("weather in Paris", google_format=True))
        assert task.status.state == TaskState.COMPLETED

    def test_non_weather_query_asks_for_input(self, agent, make_task):
        task = agent.handle_task(make_task("tell me a joke"))
        assert task.status.state == TaskState.INPUT_REQUIRED

    def test_missing_location_asks_for_input(self, agent, make_task):
        task = agent.handle_task(make_task("weather"))
        assert task.status.state == TaskState.INPUT_REQUIRED
