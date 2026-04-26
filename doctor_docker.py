#!/usr/bin/env python3
"""
doctor-docker
A safe, dependency-free Docker project diagnostic CLI.

Works on: Windows, macOS, Linux
Requires: Python 3.8+
Optional: Docker CLI / Docker Compose plugin

Usage:
  python doctor_docker.py
  python doctor_docker.py /path/to/project
  python doctor_docker.py --logs 120
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ----------------------------- UI helpers -----------------------------

class Style:
    def __init__(self) -> None:
        self.enabled = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    def c(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def bold(self, text: str) -> str:
        return self.c(text, "1")

    def red(self, text: str) -> str:
        return self.c(text, "31")

    def yellow(self, text: str) -> str:
        return self.c(text, "33")

    def green(self, text: str) -> str:
        return self.c(text, "32")

    def blue(self, text: str) -> str:
        return self.c(text, "34")


S = Style()


@dataclass
class Finding:
    level: str  # OK, INFO, WARN, ERROR
    title: str
    problem: Optional[str] = None
    fix: Optional[str] = None
    details: Optional[List[str]] = None

    @property
    def score_penalty(self) -> int:
        return {"ERROR": 18, "WARN": 8, "INFO": 0, "OK": 0}.get(self.level, 0)


def icon(level: str) -> str:
    return {
        "OK": "✅",
        "INFO": "ℹ️ ",
        "WARN": "⚠️ ",
        "ERROR": "❌",
    }.get(level, "•")


def color_level(level: str, text: str) -> str:
    if level == "ERROR":
        return S.red(text)
    if level == "WARN":
        return S.yellow(text)
    if level == "OK":
        return S.green(text)
    return S.blue(text)


# ----------------------------- System helpers -----------------------------

def run_cmd(
    cmd: Sequence[str],
    cwd: Optional[Path] = None,
    timeout: int = 12,
) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            list(cmd),
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            shell=False,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except Exception as e:
        return 1, "", f"Could not run command {' '.join(cmd)}: {e}"


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def safe_read(path: Path, max_bytes: int = 2_000_000) -> str:
    try:
        data = path.read_bytes()[:max_bytes]
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def normalize_newlines(text: str) -> List[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


# ----------------------------- Docker checks -----------------------------

def check_docker_installed() -> Finding:
    if command_exists("docker"):
        code, out, err = run_cmd(["docker", "--version"], timeout=8)
        version = out or err or "Docker CLI found."
        return Finding("OK", "Docker CLI is installed", details=[version])

    return Finding(
        "ERROR",
        "Docker CLI is not installed or not in PATH",
        problem="The `docker` command could not be found.",
        fix="Install Docker Desktop on Windows/macOS, or Docker Engine on Linux. Then restart your terminal.",
    )


def check_docker_daemon() -> Finding:
    if not command_exists("docker"):
        return Finding("INFO", "Skipped daemon check", problem="Docker CLI is missing.")

    code, out, err = run_cmd(["docker", "info", "--format", "{{json .ServerVersion}}"], timeout=10)
    if code == 0:
        version = out.strip('"') if out else "unknown"
        return Finding("OK", "Docker daemon is running", details=[f"Server version: {version}"])

    combined = f"{out}\n{err}".strip()
    system = platform.system().lower()
    if "permission denied" in combined.lower() or "got permission denied" in combined.lower():
        fix = "On Linux, add your user to the docker group: `sudo usermod -aG docker $USER`, then log out/in. Or run with sudo."
    elif system == "windows" or system == "darwin":
        fix = "Start Docker Desktop and wait until it says Docker is running."
    else:
        fix = "Start Docker with `sudo systemctl start docker`. If needed, enable it with `sudo systemctl enable docker`."

    return Finding(
        "ERROR",
        "Docker daemon is not reachable",
        problem=combined or "`docker info` failed.",
        fix=fix,
    )


def check_compose_available() -> Finding:
    if not command_exists("docker"):
        return Finding("INFO", "Skipped Docker Compose check", problem="Docker CLI is missing.")

    code, out, err = run_cmd(["docker", "compose", "version"], timeout=10)
    if code == 0:
        return Finding("OK", "Docker Compose plugin is available", details=[out or "docker compose works"])

    legacy = command_exists("docker-compose")
    if legacy:
        code2, out2, err2 = run_cmd(["docker-compose", "--version"], timeout=10)
        if code2 == 0:
            return Finding(
                "WARN",
                "Legacy docker-compose is installed, but `docker compose` plugin is missing",
                problem="Modern projects usually expect `docker compose` instead of `docker-compose`.",
                fix="Install the Docker Compose plugin or update Docker Desktop.",
                details=[out2 or err2],
            )

    return Finding(
        "WARN",
        "Docker Compose is not available",
        problem=err or "`docker compose version` failed.",
        fix="Install/update Docker Desktop, or install the Docker Compose plugin for Docker Engine.",
    )


# ----------------------------- Project checks -----------------------------

COMPOSE_NAMES = [
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
]


def find_compose_files(project: Path) -> List[Path]:
    return [project / name for name in COMPOSE_NAMES if (project / name).is_file()]


def check_compose_file_exists(project: Path) -> Finding:
    files = find_compose_files(project)
    if files:
        return Finding("OK", "Compose file found", details=[str(p.name) for p in files])

    dockerfile = project / "Dockerfile"
    if dockerfile.is_file():
        return Finding(
            "INFO",
            "No Compose file found, but Dockerfile exists",
            problem="This project may be using plain `docker build` / `docker run` instead of Compose.",
            fix="If the project has multiple services, add a compose.yaml file.",
        )

    return Finding(
        "WARN",
        "No Dockerfile or Compose file found",
        problem="This folder does not look like a Docker project.",
        fix="Run doctor-docker inside your project root, or add a Dockerfile/compose.yaml.",
    )


def basic_yaml_lint(path: Path) -> List[Finding]:
    text = safe_read(path)
    lines = normalize_newlines(text)
    findings: List[Finding] = []

    tab_lines = [i + 1 for i, line in enumerate(lines) if "\t" in line]
    if tab_lines:
        findings.append(Finding(
            "ERROR",
            f"{path.name}: YAML contains tab characters",
            problem=f"Tabs found on line(s): {', '.join(map(str, tab_lines[:12]))}{'...' if len(tab_lines) > 12 else ''}",
            fix="YAML indentation must use spaces, usually 2 spaces.",
        ))

    odd_indent = []
    for i, line in enumerate(lines, start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        spaces = len(line) - len(line.lstrip(" "))
        if spaces % 2 != 0:
            odd_indent.append(i)

    if odd_indent:
        findings.append(Finding(
            "WARN",
            f"{path.name}: suspicious YAML indentation",
            problem=f"Odd number of leading spaces on line(s): {', '.join(map(str, odd_indent[:12]))}{'...' if len(odd_indent) > 12 else ''}",
            fix="Use consistent 2-space indentation in compose files.",
        ))

    if re.search(r"^version\s*:", text, flags=re.MULTILINE):
        findings.append(Finding(
            "INFO",
            f"{path.name}: `version:` key is usually unnecessary now",
            problem="Modern Docker Compose ignores/does not require the top-level version key.",
            fix="You can remove `version:` if Compose warns about it.",
        ))

    if not re.search(r"^services\s*:", text, flags=re.MULTILINE):
        findings.append(Finding(
            "WARN",
            f"{path.name}: no top-level `services:` key detected",
            problem="Most Compose projects need a `services:` section.",
            fix="Check that your compose file has `services:` at the root level.",
        ))

    return findings


def check_compose_config(project: Path) -> List[Finding]:
    files = find_compose_files(project)
    findings: List[Finding] = []

    for f in files:
        findings.extend(basic_yaml_lint(f))

    if not files or not command_exists("docker"):
        return findings

    code, out, err = run_cmd(["docker", "compose", "config"], cwd=project, timeout=20)
    if code == 0:
        findings.append(Finding("OK", "Compose config is valid", details=["`docker compose config` completed successfully."]))
    else:
        findings.append(Finding(
            "ERROR",
            "Compose config is invalid",
            problem=(err or out or "`docker compose config` failed.")[:2000],
            fix="Run `docker compose config` and fix the first YAML/Compose error it prints.",
        ))

    return findings


def collect_compose_text(project: Path) -> str:
    parts = []
    for p in find_compose_files(project):
        parts.append(f"\n# --- {p.name} ---\n")
        parts.append(safe_read(p))
    return "\n".join(parts)


def parse_env_files(project: Path, compose_text: str) -> List[str]:
    env_files: List[str] = []
    lines = normalize_newlines(compose_text)

    for idx, line in enumerate(lines):
        stripped = line.strip()

        m = re.match(r"env_file\s*:\s*['\"]?([^'\"#\[\]]+)['\"]?", stripped)
        if m:
            value = m.group(1).strip()
            if value:
                env_files.append(value)

        if stripped == "env_file:":
            for nxt in lines[idx + 1: idx + 8]:
                s = nxt.strip()
                if not s:
                    continue
                if not s.startswith("-"):
                    break
                env_files.append(s[1:].strip().strip("\"'"))

    return sorted(set(env_files))


def parse_env_keys(text: str) -> set:
    keys = set()

    for line in normalize_newlines(text):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue

        key = s.split("=", 1)[0].strip()
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            keys.add(key)

    return keys


def compare_env_keys(env: Path, example: Path) -> List[str]:
    env_keys = parse_env_keys(safe_read(env))
    ex_keys = parse_env_keys(safe_read(example))
    return sorted(ex_keys - env_keys)


def check_env_files(project: Path) -> List[Finding]:
    compose_text = collect_compose_text(project)
    findings: List[Finding] = []
    env_files = parse_env_files(project, compose_text)

    if env_files:
        missing = [f for f in env_files if not (project / f).exists()]
        if missing:
            findings.append(Finding(
                "ERROR",
                "Compose references missing env_file(s)",
                problem="Missing: " + ", ".join(missing),
                fix="Create the missing file(s). If you have `.env.example`, copy it to `.env` and fill the values.",
            ))
        else:
            findings.append(Finding("OK", "All env_file references exist", details=env_files))

    env = project / ".env"
    env_example = project / ".env.example"

    if env_example.exists() and not env.exists():
        findings.append(Finding(
            "WARN",
            ".env.example exists but .env is missing",
            problem="The app may require environment variables that are not set.",
            fix="Copy `.env.example` to `.env` and fill real values: `cp .env.example .env`",
        ))
    elif env.exists() and env_example.exists():
        missing_keys = compare_env_keys(env, env_example)
        if missing_keys:
            findings.append(Finding(
                "WARN",
                ".env is missing keys from .env.example",
                problem="Missing keys: " + ", ".join(missing_keys[:20]) + ("..." if len(missing_keys) > 20 else ""),
                fix="Add the missing variables to `.env`.",
            ))
        else:
            findings.append(Finding("OK", ".env contains all keys from .env.example"))

    return findings


def parse_ports_from_compose(compose_text: str) -> List[int]:
    ports = set()

    patterns = [
        r"['\"]?(?:127\.0\.0\.1:|0\.0\.0\.0:|localhost:)?(\d{2,5})\s*:\s*\d{1,5}(?:/(?:tcp|udp))?['\"]?",
        r"published\s*:\s*['\"]?(\d{2,5})['\"]?",
    ]

    for pat in patterns:
        for m in re.finditer(pat, compose_text, flags=re.IGNORECASE):
            try:
                port = int(m.group(1))
                if 1 <= port <= 65535:
                    ports.add(port)
            except ValueError:
                pass

    return sorted(ports)


def is_port_available(port: int) -> bool:
    for host in ("127.0.0.1", "0.0.0.0"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
        finally:
            sock.close()

    return True


def port_owner_hint(port: int) -> Optional[str]:
    system = platform.system().lower()

    if system in {"linux", "darwin"}:
        if command_exists("lsof"):
            code, out, _ = run_cmd(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], timeout=6)
            if code == 0 and out:
                return out.splitlines()[0] + (" | " + out.splitlines()[1] if len(out.splitlines()) > 1 else "")

        if command_exists("ss"):
            code, out, _ = run_cmd(["ss", "-ltnp", f"sport = :{port}"], timeout=6)
            if code == 0 and out:
                return " ".join(out.splitlines()[:2])

    elif system == "windows":
        code, out, _ = run_cmd(["netstat", "-ano"], timeout=8)
        if code == 0 and out:
            for line in out.splitlines():
                if f":{port} " in line and "LISTEN" in line.upper():
                    return line.strip()

    return None


def check_ports(project: Path) -> List[Finding]:
    compose_text = collect_compose_text(project)
    ports = parse_ports_from_compose(compose_text)
    findings: List[Finding] = []

    if not ports:
        return findings

    busy = []
    for p in ports:
        if not is_port_available(p):
            hint = port_owner_hint(p)
            busy.append((p, hint))

    if busy:
        details = [f"Port {p}: {hint or 'already in use'}" for p, hint in busy]
        findings.append(Finding(
            "ERROR",
            "One or more Compose host ports are already in use",
            problem="; ".join([f"{p}" for p, _ in busy]),
            fix="Stop the process using the port, or change the left side of the port mapping in compose.yaml. Example: `3001:3000`.",
            details=details,
        ))
    else:
        findings.append(Finding("OK", "Compose host ports look available", details=[", ".join(map(str, ports))]))

    return findings


# ----------------------------- Container/log checks -----------------------------

LOG_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"address already in use|port is already allocated|bind.*failed", re.I),
        "Port conflict detected in logs",
        "Change the host port mapping or stop the process/container using that port.",
    ),
    (
        re.compile(r"permission denied|operation not permitted", re.I),
        "Permission problem detected in logs",
        "Check file permissions, Docker socket access, mounted volumes, or Linux user/group permissions.",
    ),
    (
        re.compile(r"no such file or directory|cannot find module|module not found|failed to read|ENOENT", re.I),
        "Missing file/module detected in logs",
        "Check COPY paths, working directory, installed dependencies, and volume mounts.",
    ),
    (
        re.compile(r"connection refused|ECONNREFUSED", re.I),
        "Service connection refused",
        "A dependency service may not be ready. Add healthchecks, depends_on conditions, or correct host/port.",
    ),
    (
        re.compile(r"authentication failed|access denied|invalid password|password authentication failed", re.I),
        "Authentication error detected",
        "Check database/user/password environment variables and secrets.",
    ),
    (
        re.compile(r"database.*does not exist|unknown database", re.I),
        "Database name problem detected",
        "Create the database or update the DB name in your environment variables.",
    ),
    (
        re.compile(r"exec format error|no matching manifest for.*platform|unsupported platform", re.I),
        "CPU/platform mismatch detected",
        "Use the correct image architecture or set `platform: linux/amd64` / `linux/arm64` intentionally.",
    ),
    (
        re.compile(r"out of memory|oom|killed process", re.I),
        "Out-of-memory problem detected",
        "Increase Docker memory limits, reduce app memory usage, or check runaway processes.",
    ),
    (
        re.compile(r"yaml:|did not find expected key|mapping values are not allowed", re.I),
        "YAML syntax problem detected",
        "Fix compose.yaml indentation, colons, quotes, and tabs.",
    ),
    (
        re.compile(r"npm ERR!|pnpm ERR!|yarn error", re.I),
        "Node package install/runtime error detected",
        "Check lockfile, package manager, Node version, and dependency install step.",
    ),
    (
        re.compile(r"pip.*error|ModuleNotFoundError|ImportError", re.I),
        "Python dependency error detected",
        "Check requirements.txt/pyproject.toml and install dependencies inside the image.",
    ),
]


def docker_compose_ps(project: Path) -> List[Dict[str, str]]:
    if not command_exists("docker"):
        return []

    code, out, _ = run_cmd(["docker", "compose", "ps", "-a", "--format", "json"], cwd=project, timeout=14)
    if code != 0 or not out:
        return []

    containers: List[Dict[str, str]] = []

    try:
        data = json.loads(out)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                containers.append(obj)
        except json.JSONDecodeError:
            continue

    return containers


def get_container_name(obj: Dict[str, str]) -> str:
    for key in ("Name", "Names", "Service", "ID"):
        val = obj.get(key)
        if val:
            return str(val)

    return "unknown"


def get_container_state(obj: Dict[str, str]) -> str:
    for key in ("State", "Status"):
        val = obj.get(key)
        if val:
            return str(val)

    return "unknown"


def analyze_logs(logs: str) -> List[Finding]:
    findings: List[Finding] = []

    for pattern, title, fix in LOG_PATTERNS:
        matches = []

        for line in logs.splitlines():
            if pattern.search(line):
                cleaned = line.strip()
                if cleaned and cleaned not in matches:
                    matches.append(cleaned[:350])

            if len(matches) >= 3:
                break

        if matches:
            findings.append(Finding(
                "ERROR",
                title,
                problem="Found matching error line(s) in recent container logs.",
                fix=fix,
                details=matches,
            ))

    return findings


def inspect_compose_containers(project: Path, log_lines: int) -> List[Finding]:
    findings: List[Finding] = []
    containers = docker_compose_ps(project)

    if not containers:
        return findings

    bad = []

    for c in containers:
        name = get_container_name(c)
        state = get_container_state(c)
        normalized = state.lower()

        if any(word in normalized for word in ["exited", "dead", "restarting", "created"]):
            bad.append((name, state))

    if bad:
        findings.append(Finding(
            "ERROR",
            "Some Compose containers are not running cleanly",
            problem="; ".join([f"{name}: {state}" for name, state in bad]),
            fix="Run `docker compose logs --tail=100` and check the first real error above the crash.",
        ))
    else:
        findings.append(Finding(
            "OK",
            "Compose containers look healthy/running",
            details=[f"{get_container_name(c)}: {get_container_state(c)}" for c in containers],
        ))

    code, out, err = run_cmd(["docker", "compose", "logs", f"--tail={log_lines}"], cwd=project, timeout=25)
    logs = out or err

    if code == 0 and logs.strip():
        findings.extend(analyze_logs(logs))
    elif code != 0:
        findings.append(Finding(
            "WARN",
            "Could not read Compose logs",
            problem=(err or out or "docker compose logs failed")[:1500],
            fix="Start the project first with `docker compose up`, or check whether this folder belongs to a Compose project.",
        ))

    return findings


# ----------------------------- Dockerfile checks -----------------------------

def find_dockerfiles(project: Path) -> List[Path]:
    files = [project / "Dockerfile"] if (project / "Dockerfile").is_file() else []
    files.extend(sorted(project.glob("Dockerfile.*")))
    return files


def check_dockerfiles(project: Path) -> List[Finding]:
    findings: List[Finding] = []

    for df in find_dockerfiles(project):
        text = safe_read(df)
        lower = text.lower()

        if not text.strip():
            findings.append(Finding(
                "ERROR",
                f"{df.name} is empty",
                fix="Add Docker build instructions or remove the empty file.",
            ))
            continue

        if "from " not in lower:
            findings.append(Finding(
                "ERROR",
                f"{df.name}: missing FROM instruction",
                problem="A Dockerfile must start from a base image.",
                fix="Add something like `FROM python:3.12-slim` or `FROM node:22-alpine`.",
            ))

        if re.search(r"^FROM\s+[^\n:]+\s*$", text, flags=re.IGNORECASE | re.MULTILINE):
            findings.append(Finding(
                "WARN",
                f"{df.name}: base image tag may be implicit/latest",
                problem="Using implicit `latest` can break builds unexpectedly.",
                fix="Pin a version tag, for example `python:3.12-slim` instead of `python`.",
            ))

        if "apt-get update" in lower and "rm -rf /var/lib/apt/lists" not in lower:
            findings.append(Finding(
                "INFO",
                f"{df.name}: apt cache cleanup not detected",
                problem="Images can become larger than needed.",
                fix="After apt install, add `rm -rf /var/lib/apt/lists/*` in the same RUN layer.",
            ))

        if "node_modules" in lower and not (project / ".dockerignore").exists():
            findings.append(Finding(
                "WARN",
                f"{df.name}: .dockerignore is missing",
                problem="Docker build context may include node_modules, git files, caches, or secrets.",
                fix="Create `.dockerignore` and exclude node_modules, .git, dist/build, .env, caches.",
            ))

    if find_dockerfiles(project):
        findings.append(Finding(
            "OK",
            "Dockerfile scan completed",
            details=[p.name for p in find_dockerfiles(project)],
        ))

    return findings


def check_dockerignore(project: Path) -> List[Finding]:
    if not find_dockerfiles(project) and not find_compose_files(project):
        return []

    path = project / ".dockerignore"

    if not path.exists():
        return [Finding(
            "WARN",
            ".dockerignore is missing",
            problem="Docker may send unnecessary or sensitive files into the build context.",
            fix="Create `.dockerignore` with at least: .git, node_modules, __pycache__, .env, dist, build.",
        )]

    text = safe_read(path)
    recommended = [".git", "node_modules", ".env", "__pycache__"]
    missing = [x for x in recommended if x not in text]

    if missing:
        return [Finding(
            "INFO",
            ".dockerignore exists but may be incomplete",
            problem="Consider adding: " + ", ".join(missing),
            fix="Add common heavy/sensitive files to `.dockerignore`.",
        )]

    return [Finding("OK", ".dockerignore exists")]


# ----------------------------- Main -----------------------------

def calculate_score(findings: Iterable[Finding]) -> int:
    score = 100

    for f in findings:
        score -= f.score_penalty

    return max(0, min(100, score))


def print_finding(index: int, f: Finding) -> None:
    title = f"{index}. {icon(f.level)} {f.title}"
    print(color_level(f.level, title))

    if f.problem:
        print(f"   Problem: {f.problem}")

    if f.fix:
        print(f"   Fix: {f.fix}")

    if f.details:
        for d in f.details[:8]:
            print(f"   - {d}")

    print()


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doctor-docker",
        description="Diagnose common Docker / Docker Compose project problems.",
    )

    parser.add_argument(
        "project",
        nargs="?",
        default=".",
        help="Project directory. Default: current directory.",
    )

    parser.add_argument(
        "--logs",
        type=int,
        default=80,
        help="Number of recent Compose log lines to analyze. Default: 80.",
    )

    parser.add_argument(
        "--no-logs",
        action="store_true",
        help="Skip reading Docker Compose logs.",
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = make_parser().parse_args(argv)
    project = Path(args.project).expanduser().resolve()

    print(S.bold("🩺 doctor-docker"))
    print(f"Project: {project}")
    print(f"System: {platform.system()} {platform.release()} | Python {platform.python_version()}")
    print()

    findings: List[Finding] = []

    if not project.exists() or not project.is_dir():
        findings.append(Finding(
            "ERROR",
            "Project path is not a directory",
            problem=str(project),
            fix="Pass a valid project folder: `python doctor_docker.py /path/to/project`.",
        ))
    else:
        findings.extend([
            check_docker_installed(),
            check_docker_daemon(),
            check_compose_available(),
            check_compose_file_exists(project),
        ])

        findings.extend(check_compose_config(project))
        findings.extend(check_env_files(project))
        findings.extend(check_ports(project))
        findings.extend(check_dockerignore(project))
        findings.extend(check_dockerfiles(project))

        if not args.no_logs:
            findings.extend(inspect_compose_containers(project, max(10, args.logs)))

    score = calculate_score(findings)

    if score >= 85:
        score_text = S.green(f"{score}/100")
    elif score >= 60:
        score_text = S.yellow(f"{score}/100")
    else:
        score_text = S.red(f"{score}/100")

    print(S.bold(f"Project score: {score_text}"))
    print()

    if not findings:
        print("No checks were run.")
        return 1

    for i, finding in enumerate(findings, start=1):
        print_finding(i, finding)

    errors = sum(1 for f in findings if f.level == "ERROR")
    warnings = sum(1 for f in findings if f.level == "WARN")

    print(S.bold("Summary:"))
    print(f"Errors: {errors} | Warnings: {warnings} | Total checks/findings: {len(findings)}")

    if errors:
        print(S.red("Result: Problems found. Fix the ERROR items first."))
        return 2

    if warnings:
        print(S.yellow("Result: No fatal errors found, but improvements are recommended."))
        return 1

    print(S.green("Result: Looks good."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
