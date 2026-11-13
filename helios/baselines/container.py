"""Run one baseline method in its pinned image, offline (S4.8 B-e, B-f).

``docker run --rm --network none --cpus N --memory M`` with the exported case
mounted read-only at /in, an empty /out, and the adapters
(``baselines/rcaeval/adapters``) read-only at /adapters. The wrapper inside
(``run_method.py``) writes /out/result.json.

Outcome classes (S4.10 O-c, design B-f):
- the image is missing or not the pinned digest: ``BaselineConfigError``
  (stops the campaign);
- Docker itself fails (daemon down, exit 125-127) or the container is killed
  for memory (exit 137): ``ConnectionError`` / ``MemoryError``, infrastructure
  errors the campaign retries;
- the method raises: a result with ``error`` (an exclusion, baseline_error);
- the run passes its hard time limit: ``BaselineTimeoutError`` (an exclusion,
  baseline_timeout).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

__all__ = [
    "ADAPTER_DIR",
    "IMAGES",
    "LIMIT_S",
    "BaselineConfigError",
    "BaselineTimeoutError",
    "ContainerRunner",
    "DockerRunner",
    "Limits",
    "adapter_digest",
]

ADAPTER_DIR = Path(__file__).resolve().parents[2] / "baselines" / "rcaeval" / "adapters"
# Pinned images (baselines/rcaeval/README.md; built 2026-10-24, S0.11).
IMAGES: dict[str, tuple[str, str]] = {
    "default": (
        "helios-baselines-default:2fca61b",
        "sha256:bd05e0dcf6d6bb51bf79815ad5e0ca65676f4630800a2be3d7a824366207663b",
    ),
    "rcd": (
        "helios-baselines-rcd:2fca61b",
        "sha256:54c3079b5b48502fd08ddb7261e3b1510f6d287f093a5d3d53fb51ba3c37b3e2",
    ),
}
LIMIT_S = 1800  # Ch3's incident window; also the TTCD censoring point
_DOCKER_FAILURES = frozenset({125, 126, 127})
_OOM_KILLED = 137
_KILL_GRACE_S = 30


class BaselineConfigError(RuntimeError):
    """The baseline environment is not the pinned one: stop the campaign."""


class BaselineTimeoutError(RuntimeError):
    """The method ran past the hard time limit."""


@dataclass(frozen=True)
class Limits:
    cpus: int = 8
    memory: str = "12g"
    timeout_s: int = LIMIT_S


def adapter_digest(directory: Path = ADAPTER_DIR) -> str:
    """SHA-256 over the adapter files (names and bytes), in name order."""
    h = hashlib.sha256()
    for path in sorted(directory.glob("*.py")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


class ContainerRunner(Protocol):
    def check_image(self, env: str) -> str: ...

    def run(
        self, env: str, in_dir: Path, out_dir: Path, name: str, limits: Limits
    ) -> dict[str, Any]: ...


class DockerRunner:
    """The real runner: the Docker CLI, no network, fixed limits."""

    def __init__(self, docker: str = "docker") -> None:
        self._docker = docker

    def check_image(self, env: str) -> str:
        tag, pinned = IMAGES[env]
        proc = subprocess.run(
            [self._docker, "image", "inspect", "--format", "{{.Id}}", tag],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise BaselineConfigError(f"baseline image {tag} is not available")
        found = proc.stdout.strip()
        if found != pinned:
            raise BaselineConfigError(
                f"baseline image {tag} is {found[:19]}, pinned {pinned[:19]}"
            )
        return found

    def run(
        self, env: str, in_dir: Path, out_dir: Path, name: str, limits: Limits
    ) -> dict[str, Any]:
        tag, _ = IMAGES[env]
        cmd = [
            self._docker,
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            "none",
            "--cpus",
            str(limits.cpus),
            "--memory",
            limits.memory,
            "-v",
            f"{in_dir}:/in:ro",
            "-v",
            f"{out_dir}:/out",
            "-v",
            f"{ADAPTER_DIR}:/adapters:ro",
            "-e",
            "PYTHONPATH=/adapters",
            "-w",
            "/opt/RCAEval",
            tag,
            "python",
            "/adapters/run_method.py",
            "/in",
            "/out",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=limits.timeout_s + _KILL_GRACE_S,
            )
        except subprocess.TimeoutExpired as exc:
            subprocess.run(
                [self._docker, "kill", name], capture_output=True, check=False
            )
            raise BaselineTimeoutError(
                f"no result within {limits.timeout_s} s"
            ) from exc
        if proc.returncode == _OOM_KILLED:
            raise MemoryError(f"baseline container killed (memory {limits.memory})")
        if proc.returncode in _DOCKER_FAILURES:
            raise ConnectionError(f"docker failed: {proc.stderr.strip()[:300]}")
        result_path = out_dir / "result.json"
        if proc.returncode != 0 or not result_path.is_file():
            raise ConnectionError(
                f"baseline container exited {proc.returncode} without a result: "
                f"{proc.stderr.strip()[-300:]}"
            )
        result: dict[str, Any] = json.loads(result_path.read_text())
        if float(result.get("wall_ms", 0)) > limits.timeout_s * 1000:
            raise BaselineTimeoutError(f"ran past {limits.timeout_s} s")
        return result
