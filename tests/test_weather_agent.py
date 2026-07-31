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

    @pytest.mark.parametrize("location", ["", "   ", None, 42])
    def test_invalid_location_is_rejected_without_a_request(self, agent, monkeypatch, location):
        def boom(*args, **kwargs):
            raise AssertionError("no HTTP call should be made")

        monkeypatch.setattr(weather_module.requests, "get", boom)
        assert agent.get_weather(location) == "Please specify a location for the weather forecast."

    def test_oversized_location_is_truncated(self, agent, fake_api):
        agent.get_weather("x" * 5000)
        geo_call = fake_api[0]
        assert len(geo_call[1]["name"]) == weather_module.MAX_LOCATION_LENGTH

    @pytest.mark.parametrize("value,expected", [
        ("3", 3), (None, weather_module.config.DEFAULT_FORECAST_DAYS),
        ("not a number", weather_module.config.DEFAULT_FORECAST_DAYS),
        (0, 1), (-5, 1), (999, 16), (2.9, 2),
    ])
    def test_forecast_days_are_coerced(self, agent, fake_api, value, expected):
        agent.get_weather("Paris", forecast_days=value)
        assert fake_api[-1][1]["forecast_days"] == expected


class TestMalformedPayloads:
    @pytest.mark.parametrize("payload", [
        {}, {"results": []}, {"results": "nope"}, {"results": [None]},
        {"results": [{"name": "Paris"}]},          # coordinates missing
        {"results": [{"latitude": "x", "longitude": "y"}]},  # coordinates unusable
        [],                                        # not an object at all
    ])
    def test_unusable_geocoding_payloads_return_none(self, agent, monkeypatch, stub_response,
                                                     payload):
        monkeypatch.setattr(
            weather_module.requests, "get", lambda *a, **kw: stub_response(payload)
        )
        assert agent.geocode("Paris") is None

    def test_non_json_geocoding_response(self, agent, monkeypatch, stub_response):
        monkeypatch.setattr(
            weather_module.requests,
            "get",
            lambda *a, **kw: stub_response(ValueError("not json")),
        )
        assert agent.geocode("Paris") is None

    def test_forecast_sections_of_the_wrong_type_do_not_crash(self, agent):
        report = agent._format_weather_response(
            {"current": [1, 2], "daily": "nope", "hourly": None},
            "Paris", "France", True, True, True,
        )
        assert "Weather forecast for Paris, France" in report
        assert "CURRENT CONDITIONS:" not in report

    def test_non_dict_forecast_payload(self, agent):
        report = agent._format_weather_response(["junk"], "Paris", "France", True, True, True)
        assert "No forecast data was returned" in report

    def test_daily_series_shorter_than_time_axis(self, agent):
        data = {"daily": {"time": ["2025-06-21", "2025-06-22"], "temperature_2m_max": [70.0]}}
        report = agent._format_weather_response(data, "Paris", "", True, True, False)
        assert report.count("High: N/A") == 1

    def test_value_at_rejects_negative_index_and_bad_series(self, agent):
        assert agent._value_at({"a": [1, 2]}, "a", -1) == "N/A"
        assert agent._value_at({"a": "string"}, "a", 0) == "N/A"
        assert agent._value_at(None, "a", 0) == "N/A"


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

    def test_noise_word_location_asks_for_input(self, agent, monkeypatch, make_task):
        """'weather in the next 7 days' leaves 'the' behind - do not geocode it."""
        def boom(*args, **kwargs):
            raise AssertionError("no HTTP call should be made")

        monkeypatch.setattr(weather_module.requests, "get", boom)
        task = agent.handle_task(make_task("What's the weather in the next 7 days?"))
        assert task.status.state == TaskState.INPUT_REQUIRED

    def test_unexpected_error_fails_the_task_instead_of_raising(self, agent, monkeypatch,
                                                               make_task):
        def boom(**kwargs):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(agent, "get_weather", boom)
        task = agent.handle_task(make_task("weather in Paris"))
        assert task.status.state == TaskState.FAILED
        assert "RuntimeError" in task.status.message["content"]["text"]
