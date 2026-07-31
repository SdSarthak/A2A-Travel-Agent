import pytest
import requests

import config
import local_llm

TAGS_PAYLOAD = {"models": [{"name": "llama3.2:latest"}, {"name": "qwen2.5:7b"}]}


@pytest.fixture
def tags(monkeypatch, stub_response):
    """Serve a canned /api/tags payload and record the URL that was hit."""
    def _install(payload):
        captured = {}

        def fake_get(url, timeout=None):
            captured["url"] = url
            captured["timeout"] = timeout
            return stub_response(payload)

        monkeypatch.setattr(local_llm.requests, "get", fake_get)
        return captured

    return _install


class TestAvailableModels:
    def test_lists_installed_tags(self, tags):
        captured = tags(TAGS_PAYLOAD)
        assert local_llm.available_models() == ["llama3.2:latest", "qwen2.5:7b"]
        assert captured["url"].endswith("/api/tags")

    def test_trailing_slash_in_base_url_is_normalised(self, tags):
        captured = tags(TAGS_PAYLOAD)
        local_llm.available_models(base_url="http://localhost:11434/")
        assert captured["url"] == "http://localhost:11434/api/tags"

    def test_unreachable_ollama_returns_none(self, monkeypatch):
        def boom(*args, **kwargs):
            raise requests.ConnectionError("refused")

        monkeypatch.setattr(local_llm.requests, "get", boom)
        assert local_llm.available_models() is None

    def test_non_json_response_returns_none(self, monkeypatch, stub_response):
        monkeypatch.setattr(
            local_llm.requests, "get",
            lambda *a, **kw: stub_response(ValueError("not json")),
        )
        assert local_llm.available_models() is None

    @pytest.mark.parametrize("payload", [
        [], "text", {}, {"models": None}, {"models": "nope"},
        {"models": [None, {"name": ""}, "junk"]},
    ])
    def test_malformed_payloads_yield_an_empty_list_not_a_crash(self, tags, payload):
        tags(payload)
        assert local_llm.available_models() == []


class TestNormaliseModelTag:
    @pytest.mark.parametrize("value,expected", [
        ("llama3.2", "llama3.2:latest"),
        ("llama3.2:latest", "llama3.2:latest"),
        ("qwen2.5:7b", "qwen2.5:7b"),
        ("  llama3.2  ", "llama3.2:latest"),
        ("", ""),
        (None, ""),
    ])
    def test_tags_are_normalised(self, value, expected):
        assert local_llm.normalise_model_tag(value) == expected


class TestCheckOllama:
    def test_installed_model_passes(self, tags, monkeypatch):
        tags(TAGS_PAYLOAD)
        monkeypatch.setattr(config, "OLLAMA_MODEL", "llama3.2:latest")
        assert local_llm.check_ollama() is True

    def test_untagged_model_name_matches_the_latest_tag(self, tags, monkeypatch):
        """'llama3.2' and 'llama3.2:latest' are the same model to Ollama."""
        tags(TAGS_PAYLOAD)
        monkeypatch.setattr(config, "OLLAMA_MODEL", "llama3.2")
        assert local_llm.check_ollama() is True

    def test_missing_model_is_reported(self, tags, monkeypatch, caplog):
        tags(TAGS_PAYLOAD)
        monkeypatch.setattr(config, "OLLAMA_MODEL", "mistral")
        with caplog.at_level("WARNING"):
            assert local_llm.check_ollama() is False
        assert "ollama pull mistral" in caplog.text

    def test_unreachable_ollama_is_reported(self, monkeypatch, caplog):
        monkeypatch.setattr(local_llm, "available_models", lambda: None)
        with caplog.at_level("ERROR"):
            assert local_llm.check_ollama() is False
        assert "cannot reach Ollama" in caplog.text


class TestMain:
    def test_build_failure_returns_non_zero_instead_of_raising(self, monkeypatch, caplog):
        monkeypatch.setattr(local_llm, "check_ollama", lambda: False)
        monkeypatch.setattr(
            local_llm, "build_llm_server",
            lambda: (_ for _ in ()).throw(RuntimeError("no ollama")),
        )
        with caplog.at_level("ERROR"):
            assert local_llm.main() == 1
        assert "could not build the LLM server" in caplog.text

    def test_server_thread_dying_returns_non_zero(self, monkeypatch, caplog):
        monkeypatch.setattr(local_llm, "check_ollama", lambda: True)
        monkeypatch.setattr(local_llm, "build_llm_server", lambda: object())
        monkeypatch.setattr(
            local_llm, "run_server",
            lambda server, host=None, port=None: None,  # returns immediately
        )
        with caplog.at_level("ERROR"):
            assert local_llm.main() == 1
        assert "stopped unexpectedly" in caplog.text
