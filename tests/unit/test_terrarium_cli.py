"""Unit tests for terrarium CLI mode selection and headless output."""

import argparse
import sys
import types
from types import SimpleNamespace

import pytest


class _DummyVault:
    def __init__(self, *args, **kwargs):
        pass

    def enable_auto_pack(self):
        pass

    def enable_cache(self, *args, **kwargs):
        pass

    def flush_cache(self):
        pass

    def insert(self, *args, **kwargs):
        pass

    def keys(self, *args, **kwargs):
        return []

    def __setitem__(self, key, value):
        pass

    def __getitem__(self, key):
        raise KeyError(key)


sys.modules.setdefault(
    "html2text",
    types.SimpleNamespace(HTML2Text=object, html2text=lambda text: text),
)
sys.modules.setdefault(
    "kohakuvault",
    types.SimpleNamespace(KVault=_DummyVault, TextVault=_DummyVault),
)

from kohakuterrarium.terrarium import cli as terrarium_cli


def _make_config(*, with_root: bool = True):
    root = None
    if with_root:
        root = SimpleNamespace(config_data={"base_config": "creatures/root"})

    return SimpleNamespace(
        name="demo_terrarium",
        creatures=[
            SimpleNamespace(
                name="alpha",
                listen_channels=["tasks"],
                send_channels=["results"],
            )
        ],
        channels=[
            SimpleNamespace(
                name="tasks",
                channel_type="queue",
                description="Task queue",
            )
        ],
        root=root,
    )


def _make_args(path: str, *, mode: str) -> argparse.Namespace:
    return argparse.Namespace(
        terrarium_command="run",
        terrarium_path=path,
        log_level="INFO",
        seed=None,
        seed_channel="seed",
        observe=["tasks"],
        no_observe=False,
        session=None,
        no_session=True,
        llm="gpt-5.4",
        mode=mode,
    )


def test_run_parser_accepts_mode_flag():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    terrarium_cli.add_terrarium_subparser(subparsers)

    args = parser.parse_args(["terrarium", "run", "terrarium.yaml", "--mode", "cli"])

    assert args.mode == "cli"


@pytest.mark.asyncio
async def test_cli_output_prints_with_speaker_prefix(capsys):
    output = terrarium_cli.CLIOutput("alpha")

    await output.write("ready")
    output.reset()
    await output.write_stream("stream")
    await output.write_stream("ed")
    await output.flush()

    assert capsys.readouterr().out == "[alpha] ready\n[alpha] streamed\n"


def test_run_root_cli_mode_dispatches_to_cli_runner(monkeypatch, tmp_path):
    config = _make_config(with_root=True)
    config_path = tmp_path / "terrarium.yaml"
    config_path.write_text("terrarium: {}\n", encoding="utf-8")
    args = _make_args(str(config_path), mode="cli")

    calls: dict[str, object] = {}

    class DummyRuntime:
        def __init__(self, config_obj, llm_override=None):
            self.config = config_obj
            self.llm_override = llm_override
            self._pending_session_store = None

    async def fake_cli_runner(runtime, *, observe, no_observe):
        calls["runner"] = "cli"
        calls["runtime"] = runtime
        calls["observe"] = observe
        calls["no_observe"] = no_observe

    async def fake_tui_runner(runtime):
        calls["runner"] = "tui"
        calls["runtime"] = runtime

    monkeypatch.setattr(terrarium_cli, "load_terrarium_config", lambda _: config)
    monkeypatch.setattr(terrarium_cli, "TerrariumRuntime", DummyRuntime)
    monkeypatch.setattr(terrarium_cli, "run_terrarium_with_cli", fake_cli_runner)
    monkeypatch.setattr(terrarium_cli, "run_terrarium_with_tui", fake_tui_runner)

    rc = terrarium_cli._run_terrarium_cli(args)

    assert rc == 0
    assert calls["runner"] == "cli"
    assert calls["observe"] == ["tasks"]
    assert calls["no_observe"] is False
    assert calls["runtime"].llm_override == "gpt-5.4"


def test_run_root_tui_mode_dispatches_to_tui_runner(monkeypatch, tmp_path):
    config = _make_config(with_root=True)
    config_path = tmp_path / "terrarium.yaml"
    config_path.write_text("terrarium: {}\n", encoding="utf-8")
    args = _make_args(str(config_path), mode="tui")

    calls: dict[str, object] = {}

    class DummyRuntime:
        def __init__(self, config_obj, llm_override=None):
            self.config = config_obj
            self.llm_override = llm_override
            self._pending_session_store = None

    async def fake_cli_runner(runtime, *, observe, no_observe):
        calls["runner"] = "cli"
        calls["runtime"] = runtime

    async def fake_tui_runner(runtime):
        calls["runner"] = "tui"
        calls["runtime"] = runtime

    monkeypatch.setattr(terrarium_cli, "load_terrarium_config", lambda _: config)
    monkeypatch.setattr(terrarium_cli, "TerrariumRuntime", DummyRuntime)
    monkeypatch.setattr(terrarium_cli, "run_terrarium_with_cli", fake_cli_runner)
    monkeypatch.setattr(terrarium_cli, "run_terrarium_with_tui", fake_tui_runner)

    rc = terrarium_cli._run_terrarium_cli(args)

    assert rc == 0
    assert calls["runner"] == "tui"
    assert calls["runtime"].llm_override == "gpt-5.4"
