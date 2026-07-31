import os
import subprocess

import pytest

import run_all


class FakeProcess:
    """Popen stand-in that records the shutdown calls it received."""

    def __init__(self, alive=True, terminate_works=True, killable=True):
        self._alive = alive
        self._terminate_works = terminate_works
        self._killable = killable
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated = True
        if self._terminate_works:
            self._alive = False

    def kill(self):
        self.killed = True
        if self._killable:
            self._alive = False

    def wait(self, timeout=None):
        if self._alive:
            raise subprocess.TimeoutExpired("agent", timeout)
        return 0


class TestParseArgs:
    def test_unknown_flags_pass_through_to_the_planner(self):
        known, planner_args = run_all.parse_args(
            ["--skip-llm", "-d", "Tokyo", "-n", "3"]
        )
        assert known.skip_llm is True
        assert planner_args == ["-d", "Tokyo", "-n", "3"]

    def test_defaults(self):
        known, planner_args = run_all.parse_args([])
        assert (known.skip_llm, known.agents_only) == (False, False)
        assert known.startup_timeout > 0
        assert planner_args == []

    @pytest.mark.parametrize("value", ["0", "-1", "soon"])
    def test_invalid_startup_timeout_is_rejected(self, value):
        with pytest.raises(SystemExit):
            run_all.parse_args(["--startup-timeout", value])


class TestWantedAgents:
    def test_all_agents_by_default(self):
        assert [a[0] for a in run_all.wanted_agents(False)] == ["weather", "search", "llm"]

    def test_llm_is_dropped(self):
        assert [a[0] for a in run_all.wanted_agents(True)] == ["weather", "search"]


class TestStartAgent:
    def test_missing_script_raises_a_clear_error(self):
        with pytest.raises(FileNotFoundError) as excinfo:
            run_all.start_agent("NoSuchAgent.py")
        assert "NoSuchAgent.py" in str(excinfo.value)

    def test_spawns_with_the_current_interpreter(self, monkeypatch):
        captured = {}

        def fake_popen(cmd, cwd=None):
            captured["cmd"] = cmd
            captured["cwd"] = cwd
            return FakeProcess()

        monkeypatch.setattr(run_all.subprocess, "Popen", fake_popen)
        run_all.start_agent("WeatherAgent.py")
        assert captured["cmd"][0] == run_all.sys.executable
        assert os.path.isabs(captured["cmd"][1])
        assert captured["cwd"] == run_all.PROJECT_DIR


class TestStopProcesses:
    def test_terminates_running_agents(self):
        process = FakeProcess()
        run_all.stop_processes([("weather", process)])
        assert process.terminated is True
        assert process.killed is False

    def test_already_exited_agents_are_left_alone(self):
        process = FakeProcess(alive=False)
        run_all.stop_processes([("weather", process)])
        assert process.terminated is False

    def test_stubborn_agent_is_killed(self):
        process = FakeProcess(terminate_works=False)
        run_all.stop_processes([("weather", process)], timeout=0)
        assert (process.terminated, process.killed) == (True, True)

    def test_unkillable_agent_does_not_raise(self):
        process = FakeProcess(terminate_works=False, killable=False)
        run_all.stop_processes([("weather", process)], timeout=0)
        assert process.killed is True


class TestMain:
    @pytest.fixture
    def spawned(self, monkeypatch):
        started = []

        def fake_start(script):
            started.append(script)
            return FakeProcess()

        monkeypatch.setattr(run_all, "start_agent", fake_start)
        monkeypatch.setattr(run_all, "wait_for_agent", lambda url, timeout=0: True)
        return started

    def test_skip_llm_does_not_start_the_llm_agent(self, spawned, monkeypatch):
        monkeypatch.setattr(run_all.Travel_Planner_Agent, "main", lambda argv: 0)
        assert run_all.main(["--skip-llm"]) == 0
        assert "local_llm.py" not in spawned

    def test_planner_no_llm_also_skips_starting_the_llm_agent(self, spawned, monkeypatch):
        """Starting Ollama for a planner run that ignores it wastes a model load."""
        monkeypatch.setattr(run_all.Travel_Planner_Agent, "main", lambda argv: 0)
        assert run_all.main(["--no-llm"]) == 0
        assert "local_llm.py" not in spawned

    def test_skip_llm_forwards_no_llm_to_the_planner(self, spawned, monkeypatch):
        seen = {}

        def fake_main(argv):
            seen["argv"] = list(argv)
            return 0

        monkeypatch.setattr(run_all.Travel_Planner_Agent, "main", fake_main)
        run_all.main(["--skip-llm", "-d", "Tokyo"])
        assert "--no-llm" in seen["argv"]
        assert ["-d", "Tokyo"] == seen["argv"][:2]

    def test_no_llm_is_not_duplicated(self, spawned, monkeypatch):
        seen = {}

        def fake_main(argv):
            seen["argv"] = list(argv)
            return 0

        monkeypatch.setattr(run_all.Travel_Planner_Agent, "main", fake_main)
        run_all.main(["--skip-llm", "--no-llm"])
        assert seen["argv"].count("--no-llm") == 1

    def test_planner_exit_code_is_propagated(self, spawned, monkeypatch):
        monkeypatch.setattr(run_all.Travel_Planner_Agent, "main", lambda argv: 1)
        assert run_all.main([]) == 1

    def test_missing_agent_script_returns_two(self, monkeypatch):
        def boom(script):
            raise FileNotFoundError("agent script is missing: " + script)

        monkeypatch.setattr(run_all, "start_agent", boom)
        assert run_all.main([]) == 2

    def test_agents_are_stopped_even_when_the_planner_raises(self, monkeypatch):
        processes = []

        def fake_start(script):
            process = FakeProcess()
            processes.append(process)
            return process

        monkeypatch.setattr(run_all, "start_agent", fake_start)
        monkeypatch.setattr(run_all, "wait_for_agent", lambda url, timeout=0: True)
        monkeypatch.setattr(run_all.Travel_Planner_Agent, "main",
                            lambda argv: (_ for _ in ()).throw(KeyboardInterrupt()))
        assert run_all.main([]) == 130
        assert processes and all(p.terminated for p in processes)

    def test_agents_only_reports_a_crashed_agent(self, monkeypatch):
        dead = FakeProcess(alive=False)
        monkeypatch.setattr(run_all, "start_agent", lambda script: dead)
        monkeypatch.setattr(run_all, "wait_for_agent", lambda url, timeout=0: True)
        monkeypatch.setattr(run_all.time, "sleep", lambda seconds: None)
        assert run_all.main(["--agents-only"]) == 1
