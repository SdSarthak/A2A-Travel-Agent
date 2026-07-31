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

MAX_PLAN_DAYS = 7

EXIT_OK = 0
EXIT_ALL_AGENTS_DOWN = 1
EXIT_OUTPUT_FAILED = 2


def _positive_int(value):
    """argparse type for a forecast day count inside the supported range."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer")
    if not 1 <= days <= config.MAX_FORECAST_DAYS:
        raise argparse.ArgumentTypeError(
            f"days must be between 1 and {config.MAX_FORECAST_DAYS}, got {days}"
        )
    return days


def _non_empty(value):
    """argparse type that rejects blank text arguments."""
    text = (value or "").strip()
    if not text:
        raise argparse.ArgumentTypeError("value must not be empty")
    return text


def _use_utf8_stdout():
    """Stop plans with accented place names from crashing a redirected stdout.

    On Windows a redirected stream falls back to the ANSI codepage, and
    printing a bullet or a non-Latin city name raises ``UnicodeEncodeError``.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # detached or unusual stream
            pass


def parse_args(argv=None):
    """Command line interface for the travel planner."""
    parser = argparse.ArgumentParser(
        description="Plan a trip using the weather, search and LLM A2A agents."
    )
    parser.add_argument("-d", "--destination", type=_non_empty,
                        default=config.DEFAULT_DESTINATION,
                        help="destination city (default: %(default)s)")
    parser.add_argument("-t", "--dates", type=_non_empty,
                        default=config.DEFAULT_TRAVEL_DATES,
                        help="travel dates, free text (default: %(default)s)")
    parser.add_argument("-n", "--days", type=_positive_int,
                        default=config.DEFAULT_FORECAST_DAYS,
                        help=f"forecast days to request, 1-{config.MAX_FORECAST_DAYS} "
                             "(default: %(default)s)")
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


def suggestion_lines(activities):
    """Pull individual suggestions out of a search-agent reply.

    Bulleted lines win; otherwise every non-empty line that is not a section
    heading is treated as a suggestion.
    """
    if not isinstance(activities, str):
        return []

    bullets = []
    plain = []
    for raw in activities.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith(("•", "- ", "* ")):
            candidate = stripped.lstrip("•-* ").strip()
            if candidate:
                bullets.append(candidate)
        elif not stripped.endswith(":"):
            plain.append(stripped)
    return bullets or plain


def local_itinerary(destination, travel_dates, activities, outdoor_friendly,
                    activities_available=True):
    """Deterministic day-by-day plan used when the LLM agent is unavailable."""
    suggestions = suggestion_lines(activities) if activities_available else []

    style = "outdoor-friendly" if outdoor_friendly else "weather-proof (mostly indoor)"
    lines = [f"{style.capitalize()} plan for {destination} ({travel_dates}):"]

    if not suggestions:
        # Never turn the search agent's "nothing available" fallback into a
        # day-by-day plan - that reads as a real itinerary when it is not.
        lines.append(
            "No activity recommendations were available, so no day-by-day plan "
            "could be built. Start the search agent and try again."
        )
        return "\n".join(lines)

    for day, suggestion in enumerate(suggestions[:MAX_PLAN_DAYS], start=1):
        lines.append(f"Day {day}: {suggestion}")
    return "\n".join(lines)


def plan_trip(destination, travel_dates, forecast_days, weather_client, search_client,
              llm_client=None, llm_enabled=True):
    """Run the full planning flow and return a structured plan.

    ``llm_enabled=False`` means the caller deliberately skipped the LLM agent,
    so its absence is not reported as a degraded service.
    """
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

    activities, activities_ok = ask_agent(
        search_client,
        f"Recommend {kind} activities in {destination}",
        fallback=f"No activity recommendations available for {destination}.",
    )
    if not activities_ok:
        degraded.append("search")

    prompt = build_prompt(destination, travel_dates, forecast, activities)
    if llm_enabled:
        itinerary, ok = ask_agent(llm_client, prompt, fallback="")
        if not ok:
            degraded.append("llm")
    else:
        itinerary, ok = "", False

    if not ok:
        itinerary = local_itinerary(
            destination, travel_dates, activities, outdoor_friendly,
            activities_available=activities_ok,
        )

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
    _use_utf8_stdout()
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
        llm_enabled=not args.no_llm,
    )

    markdown = render_plan(plan)
    print("\n" + markdown)

    if plan["degraded"]:
        logger.warning("plan built without: %s", ", ".join(plan["degraded"]))

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(markdown)
        except OSError as exc:
            logger.error("could not write the plan to %s: %s", args.output, exc)
            return EXIT_OUTPUT_FAILED
        print(f"Plan written to {args.output}")

    # Non-zero exit only when every agent that was asked for failed.
    expected = 3 if not args.no_llm else 2
    if len(plan["degraded"]) >= expected:
        return EXIT_ALL_AGENTS_DOWN
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
