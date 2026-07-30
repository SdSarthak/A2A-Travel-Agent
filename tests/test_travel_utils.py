import requests

import travel_utils


class TestExtractMessageText:
    def test_python_a2a_format(self, make_task):
        assert travel_utils.extract_message_text(make_task("weather in Paris")) == "weather in Paris"

    def test_google_a2a_format(self, make_task):
        task = make_task("weather in Tokyo", google_format=True)
        assert travel_utils.extract_message_text(task) == "weather in Tokyo"

    def test_missing_message(self, make_task):
        task = make_task("ignored")
        task.message = None
        assert travel_utils.extract_message_text(task) == ""


class TestExtractLocation:
    def test_in_preposition(self):
        assert travel_utils.extract_location("What's the weather in Paris?") == "Paris"

    def test_for_preposition_with_trailing_clause(self):
        query = "Get weather for New York for the next 7 days"
        assert travel_utils.extract_location(query) == "New York"

    def test_activity_query(self):
        query = "Recommend outdoor activities in Kuala Lumpur"
        assert travel_utils.extract_location(query) == "Kuala Lumpur"

    def test_indoor_does_not_match_in(self):
        assert travel_utils.extract_location("Recommend indoor activities in London") == "London"

    def test_bare_location(self):
        assert travel_utils.extract_location("weather Tokyo") == "Tokyo"

    def test_default_when_empty(self):
        assert travel_utils.extract_location("", default="the location") == "the location"


class TestParseForecastDays:
    def test_reads_days(self):
        assert travel_utils.parse_forecast_days("weather in Rome for 3 days") == 3

    def test_clamps_to_maximum(self):
        assert travel_utils.parse_forecast_days("weather in Rome for 40 days") == 16

    def test_default_when_absent(self):
        assert travel_utils.parse_forecast_days("weather in Rome", default=5) == 5


class TestConditionClassification:
    def test_poor(self):
        assert travel_utils.classify_condition("Heavy rain") == "poor"
        assert travel_utils.classify_condition("Thunderstorm with heavy hail") == "poor"

    def test_good(self):
        assert travel_utils.classify_condition("Clear sky") == "good"

    def test_fair(self):
        assert travel_utils.classify_condition("Overcast") == "fair"

    def test_unknown(self):
        assert travel_utils.classify_condition("") == "unknown"


SUNNY_REPORT = """Weather forecast for Paris, France

CURRENT CONDITIONS:
Temperature: 72°F
Conditions: Mainly clear

DAILY FORECAST:
Friday, June 21:
  Conditions: Partly cloudy
Saturday, June 22:
  Conditions: Clear sky
"""

RAINY_REPORT = """Weather forecast for London, United Kingdom

CURRENT CONDITIONS:
Temperature: 55°F
Conditions: Heavy rain

DAILY FORECAST:
Friday, June 21:
  Conditions: Moderate rain
"""

MIXED_REPORT = """CURRENT CONDITIONS:
Conditions: Partly cloudy

DAILY FORECAST:
Day one:
  Conditions: Moderate rain
Day two:
  Conditions: Slight rain showers
Day three:
  Conditions: Clear sky
"""


class TestIsOutdoorFriendly:
    def test_sunny_forecast_is_outdoor(self):
        outdoor, reason = travel_utils.is_outdoor_friendly(SUNNY_REPORT)
        assert outdoor is True
        assert "Mainly clear" in reason

    def test_current_rain_forces_indoor(self):
        outdoor, reason = travel_utils.is_outdoor_friendly(RAINY_REPORT)
        assert outdoor is False
        assert "Heavy rain" in reason

    def test_majority_wet_days_forces_indoor(self):
        outdoor, reason = travel_utils.is_outdoor_friendly(MIXED_REPORT)
        assert outdoor is False
        assert "2 of 3" in reason

    def test_unstructured_text_falls_back_to_keywords(self):
        outdoor, _ = travel_utils.is_outdoor_friendly("Expect snow all week")
        assert outdoor is False

    def test_empty_text_defaults_to_outdoor(self):
        outdoor, _ = travel_utils.is_outdoor_friendly("")
        assert outdoor is True


class TestAskAgent:
    def test_returns_answer(self, stub_client):
        client = stub_client(answer="sunny")
        answer, ok = travel_utils.ask_agent(client, "weather?")
        assert (answer, ok) == ("sunny", True)
        assert client.questions == ["weather?"]

    def test_none_client_uses_fallback(self):
        assert travel_utils.ask_agent(None, "weather?", fallback="n/a") == ("n/a", False)

    def test_exception_uses_fallback(self, stub_client):
        client = stub_client(error=requests.ConnectionError("down"))
        assert travel_utils.ask_agent(client, "weather?", fallback="n/a") == ("n/a", False)

    def test_error_response_uses_fallback(self, stub_client):
        client = stub_client(answer="Error: agent exploded")
        assert travel_utils.ask_agent(client, "weather?", fallback="n/a") == ("n/a", False)

    def test_blank_response_uses_fallback(self, stub_client):
        assert travel_utils.ask_agent(stub_client(answer="   "), "q", fallback="n/a") == ("n/a", False)


class TestAgentHealth:
    def test_is_agent_up_true(self, monkeypatch, stub_response):
        monkeypatch.setattr(
            travel_utils.requests, "get", lambda *a, **kw: stub_response(status_code=200)
        )
        assert travel_utils.is_agent_up("http://localhost:9999") is True

    def test_is_agent_up_false(self, monkeypatch):
        def boom(*args, **kwargs):
            raise requests.ConnectionError("refused")

        monkeypatch.setattr(travel_utils.requests, "get", boom)
        assert travel_utils.is_agent_up("http://localhost:9999") is False

    def test_wait_for_agent_gives_up(self, monkeypatch):
        monkeypatch.setattr(travel_utils, "is_agent_up", lambda url, **kw: False)
        monkeypatch.setattr(travel_utils.time, "sleep", lambda seconds: None)
        assert travel_utils.wait_for_agent("http://localhost:9999", timeout=0.01) is False


def test_text_artifact_shape():
    assert travel_utils.text_artifact("hello") == [
        {"parts": [{"type": "text", "text": "hello"}]}
    ]
