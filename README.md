# A2A Travel Agent

A multi-agent travel planner built on the [python-a2a](https://python-a2a.readthedocs.io/)
framework. Three specialised agents (weather, search, LLM) run as independent
A2A servers and an orchestrator queries them over the agent-to-agent protocol to
produce a weather-aware, day-by-day itinerary.

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Weather Agent  │    │   Search Agent   │    │    LLM Agent    │
│   Port: 8001    │    │    Port: 8002    │    │   Port: 5001    │
│                 │    │                  │    │                 │
│ • Open-Meteo    │    │ • Brave Search   │    │ • Ollama        │
│ • Geocoding     │    │ • Nominatim      │    │ • LLaMA 3.2     │
│ • Current/daily │    │ • Curated DB     │    │ • Synthesis     │
│   /hourly       │    │   fallback       │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                   ┌─────────────────────────┐
                   │  Travel Planner Agent   │
                   │   (orchestrator, CLI)   │
                   │                         │
                   │ • Agent network         │
                   │ • Weather classifier    │
                   │ • Graceful degradation  │
                   │ • Markdown plan output  │
                   └─────────────────────────┘
```

## Features

- **Multi-agent coordination** over the A2A protocol using `AgentNetwork` and `A2AClient`.
- **Weather-aware planning**: forecasts are parsed and classified (`good` / `fair` /
  `poor`), and a wet current condition or a majority of wet forecast days switches
  the plan from outdoor to indoor activities.
- **Live web results**: the search agent calls the Brave Search API when
  `BRAVE_API_KEY` is set and falls back to a curated database of ten cities
  (Paris, London, Tokyo, New York, Rome, Barcelona, Amsterdam, Sydney, Dubai,
  Singapore) otherwise.
- **Geocoding and location search** through Open-Meteo geocoding and
  OpenStreetMap Nominatim.
- **AI synthesis** through a local Ollama model exposed as an A2A server.
- **Graceful degradation**: if the LLM agent is down the planner builds a
  deterministic day-by-day itinerary locally; if the weather or search agent is
  down the plan is still produced and the missing agents are reported.
- **Fully configurable**: ports, URLs, units, model, timeouts and trip defaults
  all come from environment variables (see `.env.example`).
- **One-command launcher** (`run_all.py`) and a **pytest suite** (78 tests) that
  runs entirely offline.

## Prerequisites

- Python 3.8+
- [Ollama](https://ollama.ai/) with a local model (default `llama3.2:latest`) —
  optional, the planner works without it via `--no-llm`
- Internet connection for the weather and location APIs

## Installation

```bash
git clone https://github.com/SdSarthak/a2a-travel-agent.git
cd a2a-travel-agent

python -m venv env
env\Scripts\activate         # Windows
# source env/bin/activate    # Linux/macOS

pip install -r requirements.txt
ollama pull llama3.2:latest    # optional, for AI synthesis
```

Copy the example environment file and edit it if you want to change ports,
units, the model, or add a Brave Search key:

```bash
cp .env.example .env
```

Every variable is optional; the defaults in `config.py` are used when a variable
is unset. No API key is required to run the system.

## Running

### One command

```bash
python run_all.py --destination Tokyo --dates "July 1-7" --days 5
python run_all.py --skip-llm                # no Ollama installed
python run_all.py --agents-only             # keep the agents up for manual use
```

`run_all.py` starts each agent as a subprocess, waits until it answers its
health endpoint, runs the planner and then shuts the agents down again.

### Manually, one terminal per agent

```bash
python WeatherAgent.py        # port 8001
python BraveSearchAgent.py    # port 8002
python local_llm.py           # port 5001
python Travel_Planner_Agent.py --destination Paris --dates "June 21-25"
```

### Planner options

| Flag | Description | Default |
| --- | --- | --- |
| `-d`, `--destination` | Destination city | `Paris` (`DEFAULT_DESTINATION`) |
| `-t`, `--dates` | Travel dates (free text) | `June 21-25` (`DEFAULT_TRAVEL_DATES`) |
| `-n`, `--days` | Forecast days to request (1-16) | `7` |
| `--weather-url` / `--search-url` / `--llm-url` | Agent endpoints | from config |
| `--wait` | Seconds to wait for agents to come up | `15` |
| `--no-llm` | Skip the LLM agent, build the itinerary locally | off |
| `-o`, `--output` | Write the markdown plan to a file | off |

## How it works

1. **Discovery** — the planner waits for each agent's `/a2a/health` endpoint and
   registers the weather and search agents in an `AgentNetwork`.
2. **Forecast** — the weather agent geocodes the destination through Open-Meteo,
   fetches current, daily and (on request) hourly data and returns a text report.
3. **Classification** — `travel_utils.is_outdoor_friendly()` reads every
   `Conditions:` line of that report and decides between outdoor and indoor
   recommendations, returning the reason it chose.
4. **Recommendations** — the search agent answers with live Brave Search results
   or curated suggestions for the destination.
5. **Synthesis** — the forecast and recommendations are folded into a prompt for
   the local LLM; the answer is rendered as a markdown plan.

Example:

```
$ python run_all.py -d Paris -t "June 21-25" -n 3

weather agent : http://localhost:8001
search agent  : http://localhost:8002
llm agent     : http://localhost:5001
ollama model  : llama3.2:latest @ http://localhost:11434
brave search  : disabled (using curated recommendations)

# Travel plan: Paris (June 21-25)

## Weather
Weather forecast for Paris, France
==================================================

CURRENT CONDITIONS:
Temperature: 72.1F
Humidity: 65%
Wind Speed: 8.0 mph
Conditions: Mainly clear
...

Recommendation type: outdoor - current conditions are 'Mainly clear'.

## Suggested activities
- Seine River cruise and walk along the riverbank
- Picnic in Luxembourg Gardens or Tuileries Garden
...

## Itinerary
Day 1: Seine River cruise & Eiffel Tower
...
```

## Project layout

| File | Purpose |
| --- | --- |
| `config.py` | All configuration, loaded from the environment / `.env` |
| `travel_utils.py` | Shared helpers: task parsing, location extraction, weather classification, agent health |
| `WeatherAgent.py` | Open-Meteo weather agent (port 8001) |
| `BraveSearchAgent.py` | Brave Search + Nominatim search agent (port 8002) |
| `local_llm.py` | Ollama model exposed as an A2A server (port 5001) |
| `Travel_Planner_Agent.py` | Orchestrator and CLI |
| `run_all.py` | Starts every agent, runs the planner, cleans up |
| `tests/` | Offline pytest suite |

## Testing

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The suite stubs every HTTP call and every agent client, so it needs no network,
no API key and no running agent.

Ad-hoc checks against a running system:

```python
from python_a2a import A2AClient

print(A2AClient("http://localhost:8001").ask("Get weather for London for 3 days"))
print(A2AClient("http://localhost:8002").ask("Recommend outdoor activities in Paris"))
print(A2AClient("http://localhost:5001").ask("Suggest a travel itinerary for Tokyo"))
```

## Configuration reference

See `.env.example` for the full list. The most useful ones:

| Variable | Purpose |
| --- | --- |
| `BRAVE_API_KEY` | Enables live web results in the search agent |
| `OLLAMA_MODEL` / `OLLAMA_BASE_URL` | Which local model to serve and where |
| `WEATHER_AGENT_PORT` / `SEARCH_AGENT_PORT` / `LLM_AGENT_PORT` | Ports to bind |
| `WEATHER_AGENT_URL` / `SEARCH_AGENT_URL` / `LLM_AGENT_URL` | Point the planner at remote agents |
| `TEMPERATURE_UNIT` / `WIND_SPEED_UNIT` / `PRECIPITATION_UNIT` | Output units |
| `DEFAULT_DESTINATION` / `DEFAULT_TRAVEL_DATES` / `DEFAULT_FORECAST_DAYS` | Trip defaults |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, ... |

## Troubleshooting

**Port already in use**

```bash
netstat -ano | findstr :8001   # Windows
taskkill /PID <PID> /F
```

Or change the port: `WEATHER_AGENT_PORT=8011 python WeatherAgent.py`.

**Ollama connection issues** — `local_llm.py` checks Ollama on startup and tells
you whether it is unreachable or the model is missing:

```bash
ollama serve
ollama list
ollama pull llama3.2:latest
```

You can also run the planner without any LLM: `python run_all.py --skip-llm`.

**Agent connection timeouts** — the planner waits `--wait` seconds for each
agent and reports which ones it could not reach; the plan is still generated
from whatever answered.

**Brave Search returns nothing** — the agent silently falls back to the curated
database and logs a notice. Keys are never logged or echoed.

## Limitations

- Curated recommendations cover ten cities; everything else gets generic
  suggestions unless a Brave Search key is configured.
- Travel dates are free text and are passed to the LLM as-is.
- No persistence: plans are printed (or written with `--output`), not stored.
- English only.

## Roadmap

- [ ] Flight and hotel agents
- [ ] Budget estimation
- [ ] Multi-language output
- [ ] Persisted user preferences and plan history
- [ ] Streaming responses from the LLM agent

## License

MIT — see [LICENSE](LICENSE).
