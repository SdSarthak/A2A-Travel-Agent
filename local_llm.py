"""LLM agent: exposes a local Ollama model as an A2A server."""

import sys
import threading

import requests
from langchain_ollama.llms import OllamaLLM
from python_a2a import run_server
from python_a2a.langchain import to_a2a_server

import config
from travel_utils import configure_logging

logger = configure_logging("llm-agent")


def build_llm():
    """Create the LangChain LLM described by the configuration."""
    return OllamaLLM(model=config.OLLAMA_MODEL, base_url=config.OLLAMA_BASE_URL)


def build_llm_server(llm=None):
    """Convert the LangChain LLM into an A2A server."""
    return to_a2a_server(llm or build_llm())


def available_models(base_url=None, timeout=5):
    """List the model tags Ollama currently has installed."""
    url = (base_url or config.OLLAMA_BASE_URL).rstrip("/") + "/api/tags"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None
    return [model.get("name", "") for model in payload.get("models", [])]


def check_ollama():
    """Warn early when Ollama is unreachable or the model is missing."""
    models = available_models()
    if models is None:
        logger.error(
            "cannot reach Ollama at %s - start it with 'ollama serve'",
            config.OLLAMA_BASE_URL,
        )
        return False
    if config.OLLAMA_MODEL not in models:
        logger.warning(
            "model '%s' is not installed - run 'ollama pull %s' (installed: %s)",
            config.OLLAMA_MODEL,
            config.OLLAMA_MODEL,
            ", ".join(models) or "none",
        )
        return False
    return True


def main():
    check_ollama()

    llm_server = build_llm_server()
    llm_thread = threading.Thread(
        target=lambda: run_server(
            llm_server, host=config.AGENT_HOST, port=config.LLM_AGENT_PORT
        ),
        daemon=True,
    )
    llm_thread.start()

    # Wait here until Ctrl+C
    try:
        logger.info(
            "llm agent serving %s on port %s. Press Ctrl+C to stop.",
            config.OLLAMA_MODEL,
            config.LLM_AGENT_PORT,
        )
        while llm_thread.is_alive():
            llm_thread.join(1)
    except KeyboardInterrupt:
        logger.info("stopping llm agent")
        sys.exit(0)


if __name__ == "__main__":
    main()
