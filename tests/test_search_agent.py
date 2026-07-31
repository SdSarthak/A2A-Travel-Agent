import pytest
import requests
from python_a2a import TaskState

import BraveSearchAgent as search_module
import config

BRAVE_PAYLOAD = {
    "web": {
        "results": [
            {
                "title": "10 <strong>outdoor</strong> things to do in Rome",
                "description": "Walk the <strong>Appian Way</strong> and more.",
                "url": "https://example.com/rome",
            },
            {"title": "", "description": "no title, skipped", "url": "https://example.com/x"},
        ]
    }
}

NOMINATIM_PAYLOAD = [
    {
        "display_name": "Paris, Ile-de-France, France",
        "lat": "48.85",
        "lon": "2.35",
        "type": "city",
        "importance": 0.9123,
    }
]


@pytest.fixture
def agent():
    return search_module.LocationSearchAgent()


@pytest.fixture
def no_brave_key(monkeypatch):
    monkeypatch.setattr(config, "BRAVE_API_KEY", "")


@pytest.fixture
def brave_key(monkeypatch):
    monkeypatch.setattr(config, "BRAVE_API_KEY", "PLACEHOLDER-TEST-KEY")


class TestCategoryDetection:
    @pytest.mark.parametrize("query,expected", [
        ("Recommend outdoor activities in Paris", "outdoor"),
        ("Recommend indoor activities in Paris", "indoor"),
        ("Best restaurants in Paris", "restaurant"),
        ("Which museum in Paris", "museum"),
        ("Things to do in Paris", "general"),
    ])
    def test_category_for(self, agent, query, expected):
        assert agent._category_for(query.lower()) == expected


class TestLocationKey:
    def test_alias_is_normalised(self, agent):
        assert agent._location_key("New York City") == "new york"

    def test_leading_article_removed(self, agent):
        assert agent._location_key("The Hague") == "hague"

    def test_plain_city_is_untouched(self, agent):
        assert agent._location_key("Tokyo") == "tokyo"


class TestCuratedRecommendations:
    def test_known_city(self, agent, no_brave_key):
        result = agent.search("Recommend outdoor activities in Tokyo")
        assert "Activity recommendations for Tokyo" in result
        assert "Senso-ji Temple" in result

    def test_alias_city(self, agent, no_brave_key):
        result = agent.search("Recommend indoor activities in New York City")
        assert "Metropolitan Museum of Art" in result

    def test_unknown_city_falls_back(self, agent, no_brave_key):
        result = agent.search("Recommend outdoor activities in Springfield")
        assert "Explore local parks and outdoor markets" in result

    def test_restaurant_query(self, agent, no_brave_key):
        assert "Food markets" in agent.search("Best restaurants in Lisbon")


class TestBraveSearch:
    def test_disabled_without_key(self, agent, no_brave_key):
        assert agent.brave_search("anything") == []

    def test_parses_results(self, agent, brave_key, monkeypatch, stub_response):
        captured = {}

        def fake_get(url, params=None, headers=None, **kwargs):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            return stub_response(BRAVE_PAYLOAD)

        monkeypatch.setattr(search_module.requests, "get", fake_get)
        results = agent.brave_search("outdoor things in Rome", count=3)

        assert captured["url"] == config.BRAVE_SEARCH_URL
        assert captured["params"]["count"] == 3
        assert captured["headers"]["X-Subscription-Token"] == "PLACEHOLDER-TEST-KEY"
        assert len(results) == 1
        assert results[0]["title"] == "10 outdoor things to do in Rome"
        assert results[0]["description"] == "Walk the Appian Way and more."

    def test_network_error_returns_empty(self, agent, brave_key, monkeypatch):
        def boom(*args, **kwargs):
            raise requests.Timeout("slow")

        monkeypatch.setattr(search_module.requests, "get", boom)
        assert agent.brave_search("anything") == []

    def test_recommendations_use_live_results(self, agent, brave_key, monkeypatch, stub_response):
        monkeypatch.setattr(
            search_module.requests, "get", lambda *a, **kw: stub_response(BRAVE_PAYLOAD)
        )
        result = agent.search("Recommend outdoor activities in Rome")
        assert "live Brave Search results" in result
        assert "https://example.com/rome" in result

    def test_recommendations_fall_back_when_brave_empty(self, agent, brave_key, monkeypatch,
                                                        stub_response):
        monkeypatch.setattr(
            search_module.requests, "get", lambda *a, **kw: stub_response({"web": {"results": []}})
        )
        result = agent.search("Recommend outdoor activities in Rome")
        assert "Colosseum and Roman Forum walking route" in result


class TestLocationSearch:
    def test_formats_results(self, agent, monkeypatch, stub_response):
        monkeypatch.setattr(
            search_module.requests, "get", lambda *a, **kw: stub_response(NOMINATIM_PAYLOAD)
        )
        result = agent.search("Paris")
        assert "Location search results for 'Paris'" in result
        assert "Coordinates: 48.85, 2.35" in result
        assert "Importance: 0.912" in result

    def test_no_results(self, agent, monkeypatch, stub_response):
        monkeypatch.setattr(search_module.requests, "get", lambda *a, **kw: stub_response([]))
        assert "No location results found" in agent.search("Atlantis")

    def test_network_error(self, agent, monkeypatch):
        def boom(*args, **kwargs):
            raise requests.ConnectionError("offline")

        monkeypatch.setattr(search_module.requests, "get", boom)
        assert agent.search("Paris").startswith("Location search failed")

    def test_error_object_instead_of_array(self, agent, monkeypatch, stub_response):
        """Nominatim reports some failures as {"error": ...}, not a list."""
        monkeypatch.setattr(
            search_module.requests,
            "get",
            lambda *a, **kw: stub_response({"error": "Unable to geocode"}),
        )
        result = agent.search("Paris")
        assert result == "Location search failed: Unable to geocode."

    def test_scalar_payload_is_rejected(self, agent, monkeypatch, stub_response):
        monkeypatch.setattr(
            search_module.requests, "get", lambda *a, **kw: stub_response("nonsense")
        )
        assert "returned invalid data" in agent.search("Paris")

    def test_non_numeric_importance_does_not_crash(self, agent, monkeypatch, stub_response):
        payload = [dict(NOMINATIM_PAYLOAD[0], importance="high")]
        monkeypatch.setattr(
            search_module.requests, "get", lambda *a, **kw: stub_response(payload)
        )
        assert "Importance: 0.000" in agent.search("Paris")

    def test_non_dict_entries_are_skipped(self, agent, monkeypatch, stub_response):
        monkeypatch.setattr(
            search_module.requests, "get", lambda *a, **kw: stub_response(["junk", None])
        )
        assert "No location results found" in agent.search("Paris")

    def test_invalid_json_is_reported(self, agent, monkeypatch, stub_response):
        monkeypatch.setattr(
            search_module.requests,
            "get",
            lambda *a, **kw: stub_response(ValueError("not json")),
        )
        assert "returned invalid data" in agent.search("Paris")


class TestQueryValidation:
    def test_non_string_query(self, agent):
        assert agent.search(1234) == "Please provide a search query or location to find."
        assert agent.search(None) == "Please provide a search query or location to find."

    def test_oversized_query_is_truncated(self, agent, monkeypatch, stub_response):
        captured = {}

        def fake_get(url, params=None, **kwargs):
            captured["params"] = params or {}
            return stub_response([])

        monkeypatch.setattr(search_module.requests, "get", fake_get)
        agent.search("x" * 5000)
        assert len(captured["params"]["q"]) == search_module.MAX_QUERY_LENGTH


class TestBravePayloadParsing:
    @pytest.mark.parametrize("payload", [None, [], "text", {"web": "not a dict"}, {}])
    def test_malformed_payloads_yield_no_results(self, agent, payload):
        assert agent._parse_brave_results(payload) == []

    def test_non_dict_entries_are_skipped(self, agent):
        payload = {"web": {"results": ["junk", {"title": "Real", "url": "u"}]}}
        assert [r["title"] for r in agent._parse_brave_results(payload)] == ["Real"]


class TestHandleTask:
    def test_completes_for_text(self, agent, no_brave_key, make_task):
        task = agent.handle_task(make_task("Recommend outdoor activities in Paris"))
        assert task.status.state == TaskState.COMPLETED
        assert "Seine River cruise" in task.artifacts[0]["parts"][0]["text"]

    def test_input_required_for_blank(self, agent, make_task):
        task = agent.handle_task(make_task("   "))
        assert task.status.state == TaskState.INPUT_REQUIRED

    def test_unexpected_error_fails_the_task_instead_of_raising(self, agent, monkeypatch,
                                                               make_task):
        def boom(query):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(agent, "search", boom)
        task = agent.handle_task(make_task("things to do in Paris"))
        assert task.status.state == TaskState.FAILED
        assert "RuntimeError" in task.status.message["content"]["text"]
