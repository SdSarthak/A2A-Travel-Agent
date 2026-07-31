"""Shared helpers used by the travel agents and the orchestrator.

Everything here is pure Python plus ``requests`` so it can be unit tested
without starting any agent server.
"""

import logging
import re
import time

import requests

import config

# --- Logging -----------------------------------------------------------------

def configure_logging(name=None):
    """Configure root logging once and return a named logger."""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    return logging.getLogger(name or __name__)


# --- A2A task helpers --------------------------------------------------------

def extract_message_text(task):
    """Pull the user text out of an A2A task.

    Handles the python_a2a message format (``content.text``), the Google A2A
    format (``parts`` array) and raw ``Message`` objects.
    """
    message = getattr(task, "message", None) or {}

    # Message object rather than a dict
    if not isinstance(message, dict):
        content = getattr(message, "content", None)
        return (getattr(content, "text", "") or "").strip()

    content = message.get("content")
    if isinstance(content, dict):
        text = content.get("text") or content.get("message") or ""
        if text:
            return text.strip()
    elif isinstance(content, str):
        return content.strip()

    for part in message.get("parts", []) or []:
        if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
            return part["text"].strip()

    return ""


def text_artifact(text):
    """Build the artifact list an A2A task expects for a plain text reply."""
    return [{"parts": [{"type": "text", "text": text}]}]


# --- Query parsing -----------------------------------------------------------

_PREPOSITION_PATTERNS = [
    re.compile(r"\bin\s+(?P<location>.+)$", re.IGNORECASE),
    re.compile(r"\bfor\s+(?P<location>.+)$", re.IGNORECASE),
    re.compile(r"\bat\s+(?P<location>.+)$", re.IGNORECASE),
    re.compile(r"\bnear\s+(?P<location>.+)$", re.IGNORECASE),
    re.compile(r"\baround\s+(?P<location>.+)$", re.IGNORECASE),
]

# Clause that follows a location and is not part of it, e.g.
# "New York for the next 7 days" or "Paris with kids".
_TRAILING_CLAUSE = re.compile(
    r"\s+(?:for|with|over|during|this|next|tomorrow|today|please)\b.*$", re.IGNORECASE
)

_QUERY_NOISE = re.compile(
    r"\b(?:what'?s|what|whats|is|the|get|give|me|show|tell|about|please|"
    r"weather|forecast|temperature|conditions|recommend|recommendations|suggest|"
    r"activities|attractions|things\s+to\s+do|places\s+to\s+visit|outdoor|indoor|"
    r"restaurants|museums|hotels|search|find|hourly|daily|days?|top|best)\b",
    re.IGNORECASE,
)

_DAYS_PATTERN = re.compile(r"(\d+)\s*[- ]?\s*days?", re.IGNORECASE)


def extract_location(text, default=""):
    """Extract a location from a free-form query.

    >>> extract_location("What's the weather in Paris?")
    'Paris'
    >>> extract_location("Get weather for New York for the next 7 days")
    'New York'
    """
    if not text or not isinstance(text, str):
        return default

    cleaned = text.strip().rstrip("?.!,")

    for pattern in _PREPOSITION_PATTERNS:
        match = pattern.search(cleaned)
        if not match:
            continue
        location = _TRAILING_CLAUSE.sub("", match.group("location"))
        location = location.strip(" ,.?!\"'")
        if location:
            return location

    # No preposition: strip the query verbs and keep whatever is left.
    remainder = _QUERY_NOISE.sub(" ", cleaned)
    remainder = re.sub(r"[\d]+", " ", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip(" ,.?!\"'")
    return remainder or default


def parse_forecast_days(text, default=None):
    """Read a day count out of a query, clamped to the Open-Meteo maximum."""
    if default is None:
        default = config.DEFAULT_FORECAST_DAYS
    match = _DAYS_PATTERN.search(text if isinstance(text, str) else "")
    if not match:
        return default
    return max(1, min(int(match.group(1)), config.MAX_FORECAST_DAYS))


# --- Weather interpretation --------------------------------------------------

POOR_CONDITIONS = (
    "rain",
    "drizzle",
    "snow",
    "thunder",
    "hail",
    "freezing",
    "sleet",
    "shower",
    "blizzard",
)
FAIR_CONDITIONS = ("fog", "overcast", "cloudy")
GOOD_CONDITIONS = ("clear", "sunny", "fair", "partly cloudy", "mainly clear")


def classify_condition(condition):
    """Classify a weather description as ``poor``, ``fair`` or ``good``."""
    text = (condition or "").lower()
    if any(marker in text for marker in POOR_CONDITIONS):
        return "poor"
    if any(marker in text for marker in GOOD_CONDITIONS):
        return "good"
    if any(marker in text for marker in FAIR_CONDITIONS):
        return "fair"
    return "unknown"


def _condition_lines(forecast_text):
    """Return every ``Conditions: ...`` value found in a forecast report."""
    values = []
    for line in (forecast_text or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("conditions:"):
            values.append(stripped.split(":", 1)[1].strip())
    return values


def is_outdoor_friendly(forecast_text):
    """Decide whether a forecast favours outdoor plans.

    Returns ``(outdoor_friendly, reason)``. Current conditions win; when they
    are unusable the daily forecast lines are used, and a majority of poor days
    pushes the plan indoors.
    """
    conditions = _condition_lines(forecast_text)

    if not conditions:
        text = (forecast_text or "").lower()
        if any(marker in text for marker in POOR_CONDITIONS):
            return False, "forecast mentions wet or stormy weather"
        if any(marker in text for marker in GOOD_CONDITIONS):
            return True, "forecast mentions clear or sunny weather"
        return True, "no adverse weather detected"

    current = classify_condition(conditions[0])
    if current == "poor":
        return False, f"current conditions are '{conditions[0]}'"

    daily = conditions[1:] or conditions
    poor_days = sum(1 for value in daily if classify_condition(value) == "poor")
    if daily and poor_days * 2 >= len(daily):
        return False, f"{poor_days} of {len(daily)} forecast days look wet"

    return True, f"current conditions are '{conditions[0]}'"


# --- Agent health ------------------------------------------------------------

_HEALTH_PATHS = ("/a2a/health", "/agent.json", "")


def is_agent_up(url, timeout=2.0):
    """True when an A2A agent answers on its health or index endpoint.

    ``timeout`` is the budget for the whole probe and is shared across the
    endpoints that get tried, so probing a dead port costs about ``timeout``
    seconds rather than ``timeout`` times the number of endpoints.
    """
    base = url.rstrip("/")
    per_path = max(0.25, float(timeout) / len(_HEALTH_PATHS))
    for path in _HEALTH_PATHS:
        try:
            response = requests.get(base + path, timeout=per_path)
            if response.status_code < 500:
                return True
        except requests.RequestException:
            continue
    return False


def wait_for_agent(url, timeout=30.0, interval=1.0):
    """Block until an agent is reachable or the timeout expires.

    Always probes at least once, and never sleeps or probes past the deadline.
    Uses a monotonic clock so a system clock adjustment cannot extend the wait.
    """
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        remaining = deadline - time.monotonic()
        if is_agent_up(url, timeout=min(2.0, remaining) if remaining > 0 else 0.5):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(interval, remaining))


# Agents answer with plain text, so a failure has to be recognised by its
# wording. These are the prefixes the agents in this repo use when they could
# not do the work; treating them as successes silently poisons the plan.
AGENT_FAILURE_PREFIXES = (
    "error:",
    "error looking up",
    "error fetching",
    "failed to",
    "could not ",
    "location search failed",
    "please provide",
    "please specify",
    "please ask",
)


def ask_agent(client, question, fallback=""):
    """Ask an A2A client a question, returning ``(text, ok)``.

    Network problems and agent-side errors degrade to ``fallback`` instead of
    raising, so a single unavailable agent cannot abort a travel plan.
    """
    if client is None:
        return fallback, False
    try:
        answer = client.ask(question)
    except Exception as exc:  # noqa: BLE001 - any client failure is degradable
        logging.getLogger(__name__).warning("agent call failed: %s", exc)
        return fallback, False

    if not answer or not str(answer).strip():
        return fallback, False

    answer = str(answer).strip()
    if answer.lower().startswith(AGENT_FAILURE_PREFIXES):
        logging.getLogger(__name__).warning(
            "agent could not answer: %s", answer.splitlines()[0][:120]
        )
        return fallback, False
    return answer, True
