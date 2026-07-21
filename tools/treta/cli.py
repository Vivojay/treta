from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # fixed local commands run with shell=False  # nosec B404
import sys
import time
from pathlib import Path
from typing import NoReturn

from treta.application.control_plane import run_demo_scenario
from treta.domain.models import MissionState, to_primitive
from treta.simulation.scenarios import load_scenario

ROOT = Path(__file__).resolve().parents[2]
DEMO_SCENARIO = ROOT / "simulators" / "scenarios" / "rapid-battery-drain.yaml"


def _run(arguments: list[str], *, check: bool = True) -> int:
    print(f"+ {' '.join(arguments)}", flush=True)
    # Arguments are assembled only from fixed repository commands and argparse choices.
    completed = subprocess.run(arguments, cwd=ROOT, check=False)  # noqa: S603  # nosec B603
    if check and completed.returncode != 0:
        raise subprocess.CalledProcessError(completed.returncode, arguments)
    return completed.returncode


def _pnpm(*arguments: str) -> list[str]:
    configured_node = os.environ.get("TRETA_NODE")
    configured_cli = os.environ.get("TRETA_PNPM_CLI")
    if configured_node or configured_cli:
        if not configured_node or not configured_cli:
            raise RuntimeError("TRETA_NODE and TRETA_PNPM_CLI must be set together")
        node = Path(configured_node)
        cli = Path(configured_cli)
        if not node.is_file() or not cli.is_file():
            raise RuntimeError("TRETA_NODE and TRETA_PNPM_CLI must name existing files")
        os.environ["PATH"] = str(node.parent) + os.pathsep + os.environ.get("PATH", "")
        return [str(node), str(cli), *arguments]
    configured = os.environ.get("TRETA_PNPM")
    if configured:
        configured_executable = Path(configured)
        if not configured_executable.is_file():
            raise RuntimeError("TRETA_PNPM must name an existing pnpm executable")
        return [str(configured_executable), *arguments]
    executable = shutil.which("pnpm") or shutil.which("pnpm.cmd")
    if executable:
        return [executable, *arguments]
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx:
        return [npx, "--yes", "pnpm@10.14.0", *arguments]
    raise RuntimeError("pnpm 10.14.0 or npx is required")


def _uv(*arguments: str) -> list[str]:
    executable = shutil.which("uv") or shutil.which("uv.exe")
    if not executable:
        raise RuntimeError("uv is required; install the pinned version documented in README.md")
    return [executable, *arguments]


def command_doctor(_: argparse.Namespace) -> int:
    checks = {
        "python": sys.version.split()[0],
        "uv": shutil.which("uv") or "missing",
        "node": shutil.which("node") or "missing",
        "pnpm_or_npx": shutil.which("pnpm") or shutil.which("npx") or "missing",
        "docker": shutil.which("docker") or "missing (optional for direct local slice)",
    }
    print(json.dumps(checks, indent=2))
    return 0 if checks["uv"] != "missing" and checks["node"] != "missing" else 1


def command_bootstrap(_: argparse.Namespace) -> int:
    os.environ.setdefault("UV_CACHE_DIR", str(ROOT / ".treta" / "uv-cache"))
    _run(_uv("sync", "--all-groups", "--locked"))
    _run(_pnpm("install", "--frozen-lockfile"))
    return 0


def command_format(arguments: argparse.Namespace) -> int:
    if arguments.check:
        _run([sys.executable, "-m", "ruff", "format", "--check", "src", "tools", "tests"])
        _run(_pnpm("format:check"))
    else:
        _run([sys.executable, "-m", "ruff", "format", "src", "tools", "tests"])
        _run([sys.executable, "-m", "ruff", "check", "--fix", "src", "tools", "tests"])
        _run(_pnpm("format"))
    return 0


def command_lint(_: argparse.Namespace) -> int:
    _run([sys.executable, "-m", "ruff", "check", "src", "tools", "tests"])
    _run(_pnpm("lint"))
    return 0


def command_typecheck(_: argparse.Namespace) -> int:
    _run([sys.executable, "-m", "mypy", "src", "tools"])
    _run(_pnpm("typecheck"))
    return 0


def command_test(arguments: argparse.Namespace) -> int:
    if arguments.tier == "unit":
        _run([sys.executable, "-m", "pytest", "tests/unit"])
    else:
        _run([sys.executable, "-m", "pytest"])
        _run(_pnpm("test"))
        command_simulate(argparse.Namespace(scenario="demo", json=False))
    return 0


def command_security(arguments: argparse.Namespace) -> int:
    _run([sys.executable, "-m", "tools.treta.secret_scan"])
    _run([sys.executable, "-m", "bandit", "-c", "pyproject.toml", "-r", "src", "tools"])
    if not arguments.fast:
        _run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--strict",
                "--cache-dir",
                str(ROOT / ".treta" / "pip-audit-cache"),
            ]
        )
        _run(_pnpm("audit", "--audit-level", "low"))
    return 0


def command_build(_: argparse.Namespace) -> int:
    _run([sys.executable, "-m", "compileall", "-q", "src", "tools"])
    _run(_pnpm("build"))
    return 0


def command_simulate(arguments: argparse.Namespace) -> int:
    if arguments.scenario != "demo":
        raise ValueError("only the versioned demo scenario is currently available")
    scenario = load_scenario(DEMO_SCENARIO)
    service, replay = run_demo_scenario(scenario)
    missions = service.repository.list_missions("tenant-synthetic")
    incidents = service.repository.list_incidents("tenant-synthetic")
    safety_events = [
        event for event in service.events(limit=500) if event.event_type == "safety.rule_triggered"
    ]
    summary = {
        "scenario": scenario.name,
        "drones": len(service.repository.list_drones("tenant-synthetic")),
        "selected_drone_id": missions[0].assigned_drone_id,
        "final_mission_state": missions[0].state.value,
        "incident_count": len(incidents),
        "safety_rule_trigger_count": len(safety_events),
        "event_count": len(service.events(limit=500)),
        "replay": to_primitive(replay),
    }
    if missions[0].state is not MissionState.ABORTED:
        raise RuntimeError("demo mission did not reach the expected ABORTED state")
    if not incidents or not safety_events or not replay.deterministic:
        raise RuntimeError("demo safety, incident, or replay acceptance criteria failed")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def command_ci(_: argparse.Namespace) -> int:
    command_format(argparse.Namespace(check=True))
    command_lint(argparse.Namespace())
    command_typecheck(argparse.Namespace())
    command_test(argparse.Namespace(tier="push"))
    command_security(argparse.Namespace(fast=True))
    command_build(argparse.Namespace())
    return 0


def _terminate(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def command_dev(arguments: argparse.Namespace) -> int:
    if arguments.profile == "full":
        docker = shutil.which("docker")
        if not docker:
            raise RuntimeError("Docker is required for the full local profile")
        return _run(
            [
                docker,
                "compose",
                "--profile",
                "core",
                "--profile",
                "messaging",
                "--profile",
                "observability",
                "up",
                "--build",
            ]
        )
    pnpm_command = _pnpm("--dir", "apps/web", "dev", "--host", "127.0.0.1")
    environment = os.environ.copy()
    environment.setdefault("PUBLIC_TRETA_API_ORIGIN", "http://127.0.0.1:8000")
    processes = [
        subprocess.Popen(  # noqa: S603  # nosec B603
            [sys.executable, "-m", "uvicorn", "treta.api.app:app", "--reload", "--port", "8000"],
            cwd=ROOT,
            env=environment,
        ),
        subprocess.Popen(  # noqa: S603  # nosec B603
            pnpm_command, cwd=ROOT, env=environment
        ),
    ]
    print("Treta local UI: http://127.0.0.1:5173", flush=True)
    try:
        while True:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    return return_code
            time.sleep(0.2)
    except KeyboardInterrupt:
        _terminate(processes)
        return 0
    finally:
        _terminate(processes)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m tools.treta")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor").set_defaults(handler=command_doctor)
    commands.add_parser("bootstrap").set_defaults(handler=command_bootstrap)
    format_parser = commands.add_parser("format")
    format_parser.add_argument("--check", action="store_true")
    format_parser.set_defaults(handler=command_format)
    commands.add_parser("lint").set_defaults(handler=command_lint)
    commands.add_parser("typecheck").set_defaults(handler=command_typecheck)
    test_parser = commands.add_parser("test")
    test_parser.add_argument("tier", choices=("unit", "push", "full"))
    test_parser.set_defaults(handler=command_test)
    security_parser = commands.add_parser("security")
    security_parser.add_argument("--fast", action="store_true")
    security_parser.set_defaults(handler=command_security)
    commands.add_parser("build").set_defaults(handler=command_build)
    simulate_parser = commands.add_parser("simulate")
    simulate_parser.add_argument("scenario", nargs="?", default="demo")
    simulate_parser.add_argument("--json", action="store_true")
    simulate_parser.set_defaults(handler=command_simulate)
    commands.add_parser("ci").set_defaults(handler=command_ci)
    dev_parser = commands.add_parser("dev")
    dev_parser.add_argument("profile", choices=("core", "full"), default="core", nargs="?")
    dev_parser.set_defaults(handler=command_dev)
    return root


def _fail(message: str) -> NoReturn:
    print(f"treta: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        return int(arguments.handler(arguments))
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        _fail(str(error))
