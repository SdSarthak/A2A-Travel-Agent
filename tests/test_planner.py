import Travel_Planner_Agent as planner

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


class TestLocalItinerary:
    def test_numbers_days_from_bullets(self):
        text = planner.local_itinerary("Paris", "June 21-25", ACTIVITIES, True)
        assert "Outdoor-friendly plan for Paris" in text
        assert "Day 2: Musée d'Orsay" in text

    def test_handles_plain_lines(self):
        text = planner.local_itinerary("Paris", "June", "Louvre\nOrsay", False)
        assert "Weather-proof (mostly indoor) plan" in text
        assert "Day 1: Louvre" in text


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
