import pytest

import Travel_Planner_Agent as planner
import config

SUNNY = """CURRENT CONDITIONS:
Conditions: Clear sky

DAILY FORECAST:
Friday:
  Conditions: Partly cloudy
"""

RAINY = """CURRENT CONDITIONS:
Conditions: Heavy rain

DAILY FORECAST:
Friday:
  Conditions: Moderate rain
"""

ACTIVITIES = "Activity recommendations for Paris:\n\n• Louvre Museum\n• Musée d'Orsay\n• Sainte-Chapelle"


class TestPlanTrip:
    def test_sunny_weather_asks_for_outdoor_activities(self, stub_client):
        search = stub_client(answer=ACTIVITIES)
        plan = planner.plan_trip(
            "Paris", "June 21-25", 3,
            weather_client=stub_client(answer=SUNNY),
            search_client=search,
            llm_client=stub_client(answer="Day 1: Seine cruise"),
        )
        assert plan["activity_type"] == "outdoor"
        assert "outdoor activities in Paris" in search.questions[0]
        assert plan["itinerary"] == "Day 1: Seine cruise"
        assert plan["degraded"] == []

    def test_rainy_weather_asks_for_indoor_activities(self, stub_client):
        search = stub_client(answer=ACTIVITIES)
        plan = planner.plan_trip(
            "London", "June 21-25", 3,
            weather_client=stub_client(answer=RAINY),
            search_client=search,
            llm_client=stub_client(answer="Day 1: British Museum"),
        )
        assert plan["activity_type"] == "indoor"
        assert "indoor activities in London" in search.questions[0]

    def test_forecast_days_are_requested(self, stub_client):
        weather = stub_client(answer=SUNNY)
        planner.plan_trip("Rome", "May 1-3", 5, weather, stub_client(answer=ACTIVITIES))
        assert "next 5 days" in weather.questions[0]

    def test_missing_llm_builds_local_itinerary(self, stub_client):
        plan = planner.plan_trip(
            "Paris", "June 21-25", 3,
            weather_client=stub_client(answer=SUNNY),
            search_client=stub_client(answer=ACTIVITIES),
            llm_client=None,
        )
        assert "llm" in plan["degraded"]
        assert "Day 1: Louvre Museum" in plan["itinerary"]

    def test_all_agents_down_still_returns_a_plan(self, stub_client):
        plan = planner.plan_trip("Paris", "June 21-25", 3, None, None, None)
        assert set(plan["degraded"]) == {"weather", "search", "llm"}
        assert "No weather data available" in plan["forecast"]
        assert plan["itinerary"]

    def test_dead_search_agent_does_not_become_a_fake_itinerary(self, stub_client):
        """The search fallback sentence must never be numbered as 'Day 1'."""
        plan = planner.plan_trip(
            "Paris", "June 21-25", 3,
            weather_client=stub_client(answer=SUNNY),
            search_client=None,
            llm_client=None,
        )
        assert "Day 1:" not in plan["itinerary"]
        assert "No activity recommendations were available" in plan["itinerary"]

    def test_disabled_llm_is_not_reported_as_degraded(self, stub_client):
        plan = planner.plan_trip(
            "Paris", "June 21-25", 3,
            weather_client=stub_client(answer=SUNNY),
            search_client=stub_client(answer=ACTIVITIES),
            llm_client=None,
            llm_enabled=False,
        )
        assert plan["degraded"] == []
        assert "Day 1: Louvre Museum" in plan["itinerary"]


class TestSuggestionLines:
    def test_bullets_win_over_headings(self):
        assert planner.suggestion_lines(ACTIVITIES) == [
            "Louvre Museum", "Musée d'Orsay", "Sainte-Chapelle"
        ]

    def test_headings_are_dropped_when_there_are_no_bullets(self):
        text = "Activity recommendations for Paris:\nLouvre\nOrsay"
        assert planner.suggestion_lines(text) == ["Louvre", "Orsay"]

    def test_dash_and_star_bullets(self):
        assert planner.suggestion_lines("- Louvre\n* Orsay") == ["Louvre", "Orsay"]

    @pytest.mark.parametrize("value", ["", "   \n\n", None, 42, "Heading:"])
    def test_nothing_usable(self, value):
        assert planner.suggestion_lines(value) == []


class TestLocalItinerary:
    def test_numbers_days_from_bullets(self):
        text = planner.local_itinerary("Paris", "June 21-25", ACTIVITIES, True)
        assert "Outdoor-friendly plan for Paris" in text
        assert "Day 2: Musée d'Orsay" in text

    def test_handles_plain_lines(self):
        text = planner.local_itinerary("Paris", "June", "Louvre\nOrsay", False)
        assert "Weather-proof (mostly indoor) plan" in text
        assert "Day 1: Louvre" in text

    def test_caps_at_max_plan_days(self):
        bullets = "\n".join(f"• Stop {i}" for i in range(20))
        text = planner.local_itinerary("Paris", "June", bullets, True)
        assert f"Day {planner.MAX_PLAN_DAYS}:" in text
        assert f"Day {planner.MAX_PLAN_DAYS + 1}:" not in text

    def test_unavailable_activities_produce_an_honest_message(self):
        text = planner.local_itinerary(
            "Paris", "June", "• Louvre", True, activities_available=False
        )
        assert "Day 1:" not in text
        assert "No activity recommendations were available" in text


class TestRendering:
    def test_render_plan_sections(self, stub_client):
        plan = planner.plan_trip(
            "Paris", "June 21-25", 3,
            weather_client=stub_client(answer=SUNNY),
            search_client=stub_client(answer=ACTIVITIES),
            llm_client=stub_client(answer="Day 1: Seine cruise"),
        )
        markdown = planner.render_plan(plan)
        assert markdown.startswith("# Travel plan: Paris (June 21-25)")
        assert "## Weather" in markdown
        assert "## Suggested activities" in markdown
        assert "## Itinerary" in markdown

    def test_build_prompt_includes_context(self):
        prompt = planner.build_prompt("Tokyo", "July 1-7", "sunny", "temples")
        assert "Tokyo" in prompt and "July 1-7" in prompt
        assert "sunny" in prompt and "temples" in prompt


class TestCli:
    def test_defaults(self):
        args = planner.parse_args([])
        assert args.destination
        assert args.days >= 1

    def test_overrides(self):
        args = planner.parse_args(["-d", "Tokyo", "-t", "July 1-7", "-n", "3", "--no-llm"])
        assert (args.destination, args.dates, args.days, args.no_llm) == (
            "Tokyo", "July 1-7", 3, True
        )

    @pytest.mark.parametrize("argv", [
        ["-n", "0"],
        ["-n", "-3"],
        ["-n", str(config.MAX_FORECAST_DAYS + 1)],
        ["-n", "seven"],
        ["-d", "   "],
        ["-t", ""],
    ])
    def test_invalid_arguments_are_rejected(self, argv):
        with pytest.raises(SystemExit):
            planner.parse_args(argv)

    def test_destination_is_stripped(self):
        assert planner.parse_args(["-d", "  Tokyo  "]).destination == "Tokyo"


class TestMainExitCodes:
    def _patch_plan(self, monkeypatch, degraded):
        plan = {
            "destination": "Paris", "travel_dates": "June", "forecast": "sunny",
            "outdoor_friendly": True, "reason": "clear", "activity_type": "outdoor",
            "activities": "• Louvre", "prompt": "p", "itinerary": "Day 1: Louvre",
            "degraded": degraded,
        }
        monkeypatch.setattr(planner, "connect_agents",
                            lambda args: (_StubNetwork(), {"weather": None, "search": None,
                                                           "llm": None}))
        monkeypatch.setattr(planner, "plan_trip", lambda **kwargs: plan)
        return plan

    def test_healthy_run_returns_zero(self, monkeypatch, capsys):
        self._patch_plan(monkeypatch, [])
        assert planner.main([]) == planner.EXIT_OK

    def test_all_agents_down_returns_one(self, monkeypatch, capsys):
        self._patch_plan(monkeypatch, ["weather", "search", "llm"])
        assert planner.main([]) == planner.EXIT_ALL_AGENTS_DOWN

    def test_no_llm_only_needs_two_failures_to_fail(self, monkeypatch, capsys):
        self._patch_plan(monkeypatch, ["weather", "search"])
        assert planner.main(["--no-llm"]) == planner.EXIT_ALL_AGENTS_DOWN

    def test_no_llm_with_healthy_agents_returns_zero(self, monkeypatch, capsys):
        self._patch_plan(monkeypatch, [])
        assert planner.main(["--no-llm"]) == planner.EXIT_OK

    def test_unwritable_output_path_is_reported(self, monkeypatch, tmp_path, capsys):
        self._patch_plan(monkeypatch, [])
        target = tmp_path / "missing-dir" / "plan.md"
        assert planner.main(["-o", str(target)]) == planner.EXIT_OUTPUT_FAILED

    def test_output_is_written_as_utf8(self, monkeypatch, tmp_path, capsys):
        plan = self._patch_plan(monkeypatch, [])
        plan["itinerary"] = "Day 1: Musée d'Orsay 東京"
        target = tmp_path / "plan.md"
        assert planner.main(["-o", str(target)]) == planner.EXIT_OK
        assert "Musée d'Orsay 東京" in target.read_text(encoding="utf-8")


class _StubNetwork:
    def list_agents(self):
        return [{"name": "weather", "description": "stub"}]
