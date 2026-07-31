import importlib

import pytest

import config


class TestNumericEnvHelpers:
    @pytest.mark.parametrize("raw,expected", [
        ("8080", 8080), ("  9000 ", 9000), ("-1", -1),
    ])
    def test_valid_integers(self, monkeypatch, raw, expected):
        monkeypatch.setenv("A2A_TEST_INT", raw)
        assert config._get_int("A2A_TEST_INT", 1) == expected

    @pytest.mark.parametrize("raw", ["", "eight", "8.5", "0x10"])
    def test_invalid_integers_fall_back(self, monkeypatch, raw):
        monkeypatch.setenv("A2A_TEST_INT", raw)
        assert config._get_int("A2A_TEST_INT", 7) == 7

    def test_unset_integer_uses_the_default(self, monkeypatch):
        monkeypatch.delenv("A2A_TEST_INT", raising=False)
        assert config._get_int("A2A_TEST_INT", 7) == 7

    @pytest.mark.parametrize("raw,expected", [("2.5", 2.5), ("10", 10.0)])
    def test_valid_floats(self, monkeypatch, raw, expected):
        monkeypatch.setenv("A2A_TEST_FLOAT", raw)
        assert config._get_float("A2A_TEST_FLOAT", 1) == expected

    @pytest.mark.parametrize("raw", ["", "soon", "1,5"])
    def test_invalid_floats_fall_back(self, monkeypatch, raw):
        monkeypatch.setenv("A2A_TEST_FLOAT", raw)
        assert config._get_float("A2A_TEST_FLOAT", 3.5) == 3.5


class TestUnits:
    @pytest.mark.parametrize("unit,expected", [
        ("celsius", "°C"), ("Celsius", "°C"), ("C", "°C"),
        ("fahrenheit", "°F"), ("", "°F"),
    ])
    def test_temperature_symbol(self, monkeypatch, unit, expected):
        monkeypatch.setattr(config, "TEMPERATURE_UNIT", unit)
        assert config.temperature_symbol() == expected


class TestSecrets:
    def test_no_key_means_disabled(self, monkeypatch):
        monkeypatch.setattr(config, "BRAVE_API_KEY", "")
        assert config.has_brave_api_key() is False
        assert "disabled" in config.summary()

    def test_summary_never_prints_the_key(self, monkeypatch):
        secret = "brave-super-secret-token"
        monkeypatch.setattr(config, "BRAVE_API_KEY", secret)
        summary = config.summary()
        assert config.has_brave_api_key() is True
        assert secret not in summary
        assert "enabled" in summary

    def test_key_is_stripped_of_stray_whitespace(self, monkeypatch):
        """A key pasted into .env with a trailing newline must still work."""
        monkeypatch.setenv("BRAVE_API_KEY", "  token-with-spaces  ")
        reloaded = importlib.reload(config)
        try:
            assert reloaded.BRAVE_API_KEY == "token-with-spaces"
        finally:
            monkeypatch.delenv("BRAVE_API_KEY", raising=False)
            importlib.reload(config)


class TestForecastBounds:
    def test_default_days_are_inside_the_supported_range(self):
        assert 1 <= config.DEFAULT_FORECAST_DAYS <= config.MAX_FORECAST_DAYS

    def test_open_meteo_maximum(self):
        assert config.MAX_FORECAST_DAYS == 16
