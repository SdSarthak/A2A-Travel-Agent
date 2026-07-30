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
    return subprocess.Popen(
        [sys.executable, os.path.join(PROJECT_DIR, script)],
        cwd=PROJECT_DIR,
    )


def stop_processes(processes):
    """Terminate every spawned agent, killing anything that will not exit."""
    for name, process in processes:
        if process.poll() is not None:
            continue
        logger.info("stopping %s agent", name)
        process.terminate()
    for _, process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Start all A2A travel agents and run the planner.",
        allow_abbrev=False,
    )
    parser.add_argument("--agents-only", action="store_true",
                        help="start the agents and keep them running")
    parser.add_argument("--skip-llm", action="store_true",
                        help="do not start the Ollama-backed LLM agent")
    parser.add_argument("--startup-timeout", type=float, default=45.0,
                        help="seconds to wait for each agent (default: %(default)s)")
    known, planner_args = parser.parse_known_args(argv)
    return known, planner_args


def main(argv=None):
    args, planner_args = parse_args(argv)

    wanted = [a for a in AGENTS if not (args.skip_llm and a[0] == "llm")]
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
            return 0

        if args.skip_llm and "--no-llm" not in planner_args:
            planner_args.append("--no-llm")

        return Travel_Planner_Agent.main(planner_args)

    except KeyboardInterrupt:
        logger.info("interrupted")
        return 130
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    sys.exit(main())
