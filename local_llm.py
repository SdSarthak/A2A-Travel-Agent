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
    """List the model tags Ollama currently has installed, or None if unreachable."""
    url = (base_url or config.OLLAMA_BASE_URL).rstrip("/") + "/api/tags"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None

    if not isinstance(payload, dict):
        return []
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    return [
        model.get("name", "")
        for model in models
        if isinstance(model, dict) and model.get("name")
    ]


def normalise_model_tag(name):
    """Ollama stores untagged models as ``name:latest``; compare like for like."""
    text = (name or "").strip()
    if not text:
        return ""
    return text if ":" in text else f"{text}:latest"


def check_ollama():
    """Warn early when Ollama is unreachable or the model is missing."""
    models = available_models()
    if models is None:
        logger.error(
            "cannot reach Ollama at %s - start it with 'ollama serve'",
            config.OLLAMA_BASE_URL,
        )
        return False

    wanted = normalise_model_tag(config.OLLAMA_MODEL)
    installed = {normalise_model_tag(name) for name in models}
    if wanted not in installed:
        logger.warning(
            "model '%s' is not installed - run 'ollama pull %s' (installed: %s)",
            config.OLLAMA_MODEL,
            config.OLLAMA_MODEL,
            ", ".join(sorted(models)) or "none",
        )
        return False
    return True


def main():
    check_ollama()

    try:
        llm_server = build_llm_server()
    except Exception as exc:  # noqa: BLE001 - surface a usable message, not a traceback
        logger.error(
            "could not build the LLM server for model '%s' at %s: %s: %s",
            config.OLLAMA_MODEL, config.OLLAMA_BASE_URL, type(exc).__name__, exc,
        )
        return 1

    llm_thread = threading.Thread(
        target=lambda: run_server(
            llm_server, host=config.AGENT_HOST, port=config.LLM_AGENT_PORT
        ),
        daemon=True,
        name="llm-server",
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
        return 130

    # The serving thread only exits on its own if run_server failed.
    logger.error("llm server stopped unexpectedly")
    return 1


if __name__ == "__main__":
    sys.exit(main())
