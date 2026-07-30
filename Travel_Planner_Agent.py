"""Travel planner: the orchestrator that coordinates the specialised agents."""

import argparse
import sys

from python_a2a import A2AClient, AgentNetwork

import config
from travel_utils import (
    ask_agent,
    configure_logging,
    is_outdoor_friendly,
    wait_for_agent,
)

logger = configure_logging("travel-planner")


def parse_args(argv=None):
    """Command line interface for the travel planner."""
    parser = argparse.ArgumentParser(
        description="Plan a trip using the weather, search and LLM A2A agents."
    )
    parser.add_argument("-d", "--destination", default=config.DEFAULT_DESTINATION,
                        help="destination city (default: %(default)s)")
    parser.add_argument("-t", "--dates", default=config.DEFAULT_TRAVEL_DATES,
                        help="travel dates, free text (default: %(default)s)")
    parser.add_argument("-n", "--days", type=int, default=config.DEFAULT_FORECAST_DAYS,
                        help="forecast days to request (default: %(default)s)")
    parser.add_argument("--weather-url", default=config.WEATHER_AGENT_URL)
    parser.add_argument("--search-url", default=config.SEARCH_AGENT_URL)
    parser.add_argument("--llm-url", default=config.LLM_AGENT_URL)
    parser.add_argument("--wait", type=float, default=15.0,
                        help="seconds to wait for agents to come up (default: %(default)s)")
    parser.add_argument("--no-llm", action="store_true",
                        help="skip the LLM agent and build the itinerary locally")
    parser.add_argument("-o", "--output", help="write the plan to this markdown file")
    return parser.parse_args(argv)


def connect_agents(args):
    """Build the agent network and return ``(network, clients)``."""
    network = AgentNetwork(name="Travel Assistant Network")

    for name, url in (("weather", args.weather_url), ("search", args.search_url)):
        if not wait_for_agent(url, timeout=args.wait):
            logger.warning("agent '%s' is not responding at %s", name, url)
        network.add(name, url)

    llm_client = None
    if not args.no_llm:
        if wait_for_agent(args.llm_url, timeout=args.wait):
            llm_client = A2AClient(args.llm_url)
        else:
            logger.warning("llm agent is not responding at %s", args.llm_url)

    return network, {
        "weather": network.get_agent("weather"),
        "search": network.get_agent("search"),
        "llm": llm_client,
    }


def build_prompt(destination, travel_dates, forecast, activities):
    """Prompt used to turn raw agent output into a readable itinerary."""
    return (
        "You are a travel assistant. Based on the weather forecast result "
        f"{forecast} and the recommendations [{activities}], suggest me a few "
        f"must-see attractions in {destination} on date {travel_dates}. "
        "Group them into a day-by-day plan and keep weather in mind."
    )


def local_itinerary(destination, travel_dates, activities, outdoor_friendly):
    """Deterministic day-by-day plan used when the LLM agent is unavailable."""
    suggestions = [
        line.lstrip("• ").strip()
        for line in activities.splitlines()
        if line.strip().startswith("•")
    ]
    if not suggestions:
        suggestions = [line.strip() for line in activities.splitlines() if line.strip()]

    style = "outdoor-friendly" if outdoor_friendly else "weather-proof (mostly indoor)"
    lines = [f"{style.capitalize()} plan for {destination} ({travel_dates}):"]
    for day, suggestion in enumerate(suggestions[:7], start=1):
        lines.append(f"Day {day}: {suggestion}")
    if not suggestions:
        lines.append("No recommendations were available from the search agent.")
    return "\n".join(lines)


def plan_trip(destination, travel_dates, forecast_days, weather_client, search_client,
              llm_client=None):
    """Run the full planning flow and return a structured plan."""
    degraded = []

    forecast, ok = ask_agent(
        weather_client,
        f"What's the weather in {destination} for the next {forecast_days} days?",
        fallback=f"No weather data available for {destination}.",
    )
    if not ok:
        degraded.append("weather")

    outdoor_friendly, reason = is_outdoor_friendly(forecast)
    kind = "outdoor" if outdoor_friendly else "indoor"

    activities, ok = ask_agent(
        search_client,
        f"Recommend {kind} activities in {destination}",
        fallback=f"No activity recommendations available for {destination}.",
    )
    if not ok:
        degraded.append("search")

    prompt = build_prompt(destination, travel_dates, forecast, activities)
    itinerary, ok = ask_agent(llm_client, prompt, fallback="")
    if not ok:
        degraded.append("llm")
        itinerary = local_itinerary(destination, travel_dates, activities, outdoor_friendly)

    return {
        "destination": destination,
        "travel_dates": travel_dates,
        "forecast": forecast,
        "outdoor_friendly": outdoor_friendly,
        "reason": reason,
        "activity_type": kind,
        "activities": activities,
        "prompt": prompt,
        "itinerary": itinerary,
        "degraded": degraded,
    }


def render_plan(plan):
    """Render a plan as markdown."""
    return "\n".join([
        f"# Travel plan: {plan['destination']} ({plan['travel_dates']})",
        "",
        "## Weather",
        "```",
        plan["forecast"].strip(),
        "```",
        f"Recommendation type: **{plan['activity_type']}** - {plan['reason']}.",
        "",
        "## Suggested activities",
        plan["activities"].strip(),
        "",
        "## Itinerary",
        plan["itinerary"].strip(),
        "",
    ])


def main(argv=None):
    args = parse_args(argv)
    print(config.summary())

    network, clients = connect_agents(args)

    print("\nAvailable Agents:")
    for agent_info in network.list_agents():
        print(f"- {agent_info['name']}: {agent_info.get('description', 'no description')}")

    plan = plan_trip(
        destination=args.destination,
        travel_dates=args.dates,
        forecast_days=args.days,
        weather_client=clients["weather"],
        search_client=clients["search"],
        llm_client=clients["llm"],
    )

    markdown = render_plan(plan)
    print("\n" + markdown)

    if plan["degraded"]:
        logger.warning("plan built without: %s", ", ".join(plan["degraded"]))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(markdown)
        print(f"Plan written to {args.output}")

    # Non-zero exit only when every agent failed.
    return 1 if len(plan["degraded"]) >= 3 else 0


if __name__ == "__main__":
    sys.exit(main())
