"""Launcher: start every agent, run the planner, then shut everything down.

    python run_all.py --destination Tokyo --dates "July 1-7"
    python run_all.py --agents-only      # keep the agents running for manual use
"""

import argparse
import os
import subprocess
import sys
import time

import config
import Travel_Planner_Agent
from travel_utils import configure_logging, wait_for_agent

logger = configure_logging("run-all")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

AGENTS = [
    ("weather", "WeatherAgent.py", config.WEATHER_AGENT_URL),
    ("search", "BraveSearchAgent.py", config.SEARCH_AGENT_URL),
    ("llm", "local_llm.py", config.LLM_AGENT_URL),
]


def start_agent(script):
    """Spawn one agent process."""
    path = os.path.join(PROJECT_DIR, script)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"agent script is missing: {path}")
    return subprocess.Popen([sys.executable, path], cwd=PROJECT_DIR)


def stop_processes(processes, timeout=10):
    """Terminate every spawned agent, killing anything that will not exit.

    Signals all of them first, then waits, so shutdown costs one timeout in
    total rather than one per agent.
    """
    for name, process in processes:
        if process.poll() is not None:
            continue
        logger.info("stopping %s agent", name)
        try:
            process.terminate()
        except OSError as exc:  # already reaped by the OS
            logger.debug("could not terminate %s: %s", name, exc)

    deadline = time.monotonic() + timeout
    for name, process in processes:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            logger.warning("%s agent ignored terminate, killing it", name)
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.error("%s agent could not be killed", name)


def _positive_float(value):
    """argparse type for a timeout that has to be usable."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"{value!r} is not a number")
    if seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than zero")
    return seconds


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Start all A2A travel agents and run the planner.",
        allow_abbrev=False,
    )
    parser.add_argument("--agents-only", action="store_true",
                        help="start the agents and keep them running")
    parser.add_argument("--skip-llm", action="store_true",
                        help="do not start the Ollama-backed LLM agent")
    parser.add_argument("--startup-timeout", type=_positive_float, default=45.0,
                        help="seconds to wait for each agent (default: %(default)s)")
    known, planner_args = parser.parse_known_args(argv)
    return known, planner_args


def wanted_agents(skip_llm):
    """The agents to start, honouring ``--skip-llm``."""
    return [agent for agent in AGENTS if not (skip_llm and agent[0] == "llm")]


def main(argv=None):
    args, planner_args = parse_args(argv)

    # Starting an Ollama-backed server the planner has been told to ignore
    # burns a port and a model load for nothing.
    skip_llm = args.skip_llm or "--no-llm" in planner_args
    wanted = wanted_agents(skip_llm)
    processes = []

    try:
        for name, script, _url in wanted:
            logger.info("starting %s agent (%s)", name, script)
            processes.append((name, start_agent(script)))

        for name, _script, url in wanted:
            if wait_for_agent(url, timeout=args.startup_timeout):
                logger.info("%s agent ready at %s", name, url)
            else:
                logger.warning("%s agent did not become ready at %s", name, url)

        if args.agents_only:
            logger.info("agents running. Press Ctrl+C to stop.")
            while all(process.poll() is None for _, process in processes):
                time.sleep(1)
            dead = [name for name, process in processes if process.poll() is not None]
            logger.error("agent(s) exited: %s", ", ".join(dead))
            return 1

        if skip_llm and "--no-llm" not in planner_args:
            planner_args.append("--no-llm")

        return Travel_Planner_Agent.main(planner_args)

    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        logger.info("interrupted")
        return 130
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    sys.exit(main())
