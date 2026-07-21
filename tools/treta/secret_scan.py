from __future__ import annotations

import re
import shutil
import subprocess  # resolved git executable runs with shell=False  # nosec B404
from pathlib import Path

SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    "generic assigned secret": re.compile(
        r"(?im)^\s*(?:password|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?[^\s'\"#]{8,}"
    ),
}

TEXT_SUFFIXES = {
    "",
    ".css",
    ".dockerignore",
    ".editorconfig",
    ".example",
    ".gitignore",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".scss",
    ".svelte",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}


def repository_files(root: Path) -> list[Path]:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required for repository-aware secret scanning")
    result = subprocess.run(  # noqa: S603  # nosec B603
        [git, "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [root / line for line in result.stdout.splitlines() if line]


def scan(root: Path) -> list[tuple[Path, str]]:
    findings: list[tuple[Path, str]] = []
    for path in repository_files(root):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.stat().st_size > 1_000_000:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for category, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append((path.relative_to(root), category))
    return findings


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    findings = scan(root)
    if findings:
        for path, category in findings:
            print(f"secret-scan: {path}: possible {category}")
        return 1
    print("secret-scan: no credential patterns found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
