"""Central configuration for the A2A Travel Agent system.

Every tunable value lives here and can be overridden through environment
variables (or a local ``.env`` file). Nothing in this module ever prints or
logs the value of an API key.
"""

import os

from dotenv import load_dotenv

# Load .env from the project directory without overriding real environment vars
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


def _get_int(name, default):
    """Read an integer environment variable, falling back to a default."""
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return int(default)


def _get_float(name, default):
    """Read a float environment variable, falling back to a default."""
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


# --- Network -----------------------------------------------------------------
AGENT_HOST = os.getenv("AGENT_HOST", "0.0.0.0")
CLIENT_HOST = os.getenv("CLIENT_HOST", "localhost")

WEATHER_AGENT_PORT = _get_int("WEATHER_AGENT_PORT", 8001)
SEARCH_AGENT_PORT = _get_int("SEARCH_AGENT_PORT", 8002)
LLM_AGENT_PORT = _get_int("LLM_AGENT_PORT", 5001)

WEATHER_AGENT_URL = os.getenv(
    "WEATHER_AGENT_URL", f"http://{CLIENT_HOST}:{WEATHER_AGENT_PORT}"
)
SEARCH_AGENT_URL = os.getenv(
    "SEARCH_AGENT_URL", f"http://{CLIENT_HOST}:{SEARCH_AGENT_PORT}"
)
LLM_AGENT_URL = os.getenv("LLM_AGENT_URL", f"http://{CLIENT_HOST}:{LLM_AGENT_PORT}")

# --- HTTP --------------------------------------------------------------------
REQUEST_TIMEOUT = _get_float("REQUEST_TIMEOUT", 10)
GEOCODING_TIMEOUT = _get_float("GEOCODING_TIMEOUT", 5)
USER_AGENT = os.getenv("USER_AGENT", "a2a-travel-agent/2.1 (+https://github.com/SdSarthak)")

# --- External APIs -----------------------------------------------------------
OPEN_METEO_GEOCODING_URL = os.getenv(
    "OPEN_METEO_GEOCODING_URL", "https://geocoding-api.open-meteo.com/v1/search"
)
OPEN_METEO_FORECAST_URL = os.getenv(
    "OPEN_METEO_FORECAST_URL", "https://api.open-meteo.com/v1/forecast"
)
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "").strip()
BRAVE_SEARCH_URL = os.getenv(
    "BRAVE_SEARCH_URL", "https://api.search.brave.com/res/v1/web/search"
)
BRAVE_RESULT_COUNT = _get_int("BRAVE_RESULT_COUNT", 6)

# --- Units -------------------------------------------------------------------
TEMPERATURE_UNIT = os.getenv("TEMPERATURE_UNIT", "fahrenheit")
WIND_SPEED_UNIT = os.getenv("WIND_SPEED_UNIT", "mph")
PRECIPITATION_UNIT = os.getenv("PRECIPITATION_UNIT", "inch")

# --- LLM ---------------------------------------------------------------------
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# --- Trip defaults -----------------------------------------------------------
DEFAULT_DESTINATION = os.getenv("DEFAULT_DESTINATION", "Paris")
DEFAULT_TRAVEL_DATES = os.getenv("DEFAULT_TRAVEL_DATES", "June 21-25")
DEFAULT_FORECAST_DAYS = _get_int("DEFAULT_FORECAST_DAYS", 7)
MAX_FORECAST_DAYS = 16

# --- Logging -----------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def has_brave_api_key():
    """True when a Brave Search API key is configured."""
    return bool(BRAVE_API_KEY)


def temperature_symbol():
    """Short symbol matching the configured temperature unit."""
    return "°C" if TEMPERATURE_UNIT.lower().startswith("c") else "°F"


def summary():
    """Human-readable configuration summary, safe to print (no secrets)."""
    return (
        f"weather agent : {WEATHER_AGENT_URL}\n"
        f"search agent  : {SEARCH_AGENT_URL}\n"
        f"llm agent     : {LLM_AGENT_URL}\n"
        f"ollama model  : {OLLAMA_MODEL} @ {OLLAMA_BASE_URL}\n"
        f"brave search  : {'enabled' if has_brave_api_key() else 'disabled (using curated recommendations)'}"
    )
