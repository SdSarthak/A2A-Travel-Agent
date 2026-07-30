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


class TestHandleTask:
    def test_completes_for_text(self, agent, no_brave_key, make_task):
        task = agent.handle_task(make_task("Recommend outdoor activities in Paris"))
        assert task.status.state == TaskState.COMPLETED
        assert "Seine River cruise" in task.artifacts[0]["parts"][0]["text"]

    def test_input_required_for_blank(self, agent, make_task):
        task = agent.handle_task(make_task("   "))
        assert task.status.state == TaskState.INPUT_REQUIRED
