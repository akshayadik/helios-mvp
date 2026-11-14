"""S4.3 compose deployment: pinning, secrets and exposure checks (design C-c,
C-e, C-f), the model digest check (C-d) and the code changes it needed."""

from __future__ import annotations

import importlib
import re
import subprocess
from pathlib import Path
from typing import Any, NoReturn

import pytest
import yaml

from bin import check_model
from bin.helios_api import config_for
from helios.pipelines.l_pipe import lpipe_config
from helios.pipelines.l_pipe.ollama_client import OllamaConnectionError
from helios.telemetry import pool_lock
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "deploy"
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
DEFAULT = re.compile(r"\$\{[A-Z_]+:-([^}]*)\}")


def _compose() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((DEPLOY / "compose.yaml").read_text())
    return data


def _services() -> dict[str, dict[str, Any]]:
    services: dict[str, dict[str, Any]] = _compose()["services"]
    return services


def _env_files(service: dict[str, Any]) -> list[str]:
    return [
        e["path"] if isinstance(e, dict) else e for e in service.get("env_file", [])
    ]


def test_every_pulled_image_is_pinned_by_digest() -> None:
    for name, service in _services().items():
        image = str(service["image"])
        assert ":latest" not in image, name
        if "build" in service:  # the HELIOS image, built from poetry.lock
            assert image.startswith("helios:"), name
        else:
            assert DIGEST.search(image), f"{name}: {image} is not pinned by digest"


def test_every_dockerfile_base_is_pinned_by_digest() -> None:
    stages: set[str] = set()
    for line in (DEPLOY / "Dockerfile").read_text().splitlines():
        if not line.startswith("FROM "):
            continue
        parts = line.split()
        if parts[1] not in stages:
            assert DIGEST.search(parts[1]), line
        if len(parts) == 4 and parts[2] == "AS":
            stages.add(parts[3])
    assert stages == {"deps"}


def test_only_the_runner_gets_the_deviation_secrets() -> None:
    for name, service in _services().items():
        for path in _env_files(service):
            if Path(path).name == ".env":
                assert name == "runner", f"{name} is given .env"
    api = _services()["api"]
    assert [Path(p).name for p in _env_files(api)] == ["api.env"]
    assert "DEVIATION" not in yaml.safe_dump(api)


def test_api_is_published_on_loopback_only_and_off_the_model_network() -> None:
    services = _services()
    api = services["api"]
    (mapping,) = api["ports"]
    match = DEFAULT.match(mapping)
    assert match, mapping
    assert match.group(1).startswith("127."), "api must default to the loopback address"
    assert api["networks"] == ["front"]
    assert api["read_only"] is True
    assert "ports" not in services["model"]
    assert services["model"]["networks"] == ["internal"]
    assert services["runner"]["networks"] == ["internal"]
    assert _compose()["networks"]["internal"]["internal"] is True
    assert services["model-init"]["networks"] == ["egress"]


def test_start_order_gates_the_runner_on_the_model_check() -> None:
    services = _services()
    need = services["runner"]["depends_on"]["model-check"]["condition"]
    assert need == "service_completed_successfully"
    assert (
        services["model-check"]["depends_on"]["model"]["condition"] == "service_healthy"
    )
    done = services["model"]["depends_on"]["model-init"]["condition"]
    assert done == "service_completed_successfully"
    assert "depends_on" not in services["api"]
    assert services["runner"]["profiles"] == ["run"]


def test_build_context_excludes_secrets_and_data() -> None:
    ignored = set((REPO / ".dockerignore").read_text().split())
    assert {".env", ".env.*", "**/api_keys.json", "data", "*.jsonl", ".git"} <= ignored
    assert "keys/*" in ignored and "!keys/deviation_log_ed25519.pub.pem" in ignored


class _Client:
    def __init__(self, digest: str | None = None, error: Exception | None = None):
        self.digest, self.error = digest, error

    def model_digest(self, timeout_s: float) -> str:
        if self.error is not None:
            raise self.error
        assert self.digest is not None
        return self.digest


def test_model_check_accepts_only_the_pinned_digest() -> None:
    pinned = "a" * 64
    assert check_model.check(_Client(pinned), pinned) == pinned  # type: ignore[arg-type]
    with pytest.raises(SystemExit, match="mismatch"):
        check_model.check(_Client("b" * 64), pinned)  # type: ignore[arg-type]
    with pytest.raises(SystemExit, match="model check failed"):
        check_model.check(_Client(error=OllamaConnectionError("down")), pinned)  # type: ignore[arg-type]
    with pytest.raises(SystemExit, match="not set"):
        check_model.check(_Client(pinned), None)  # type: ignore[arg-type]


def test_model_check_main_reads_the_configured_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pinned = lpipe_config.EXPECTED_MODEL_DIGEST
    assert pinned is not None
    monkeypatch.setattr(check_model, "OllamaClient", lambda url, name: _Client(pinned))
    assert check_model.main() == 0
    assert pinned[:12] in capsys.readouterr().out


def test_ollama_url_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        monkeypatch.setenv(lpipe_config.OLLAMA_URL_ENV, "http://model:11434")
        assert importlib.reload(lpipe_config).OLLAMA_BASE_URL == "http://model:11434"
        monkeypatch.delenv(lpipe_config.OLLAMA_URL_ENV)
        assert (
            importlib.reload(lpipe_config).OLLAMA_BASE_URL == "http://localhost:11434"
        )
    finally:
        monkeypatch.delenv(lpipe_config.OLLAMA_URL_ENV, raising=False)
        importlib.reload(lpipe_config)


def test_pool_lock_fails_closed_without_git(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def no_git(*args: object, **kwargs: object) -> NoReturn:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)
    assert pool_lock.build_frozen(tmp_path) is False
    with pytest.raises(pool_lock.PoolLockedError):
        pool_lock.require_unlocked("case", tmp_path)


def test_api_decisions_ledger_can_live_outside_the_campaign(tmp_path: Path) -> None:
    secret = b"s" * 32
    default = config_for(tmp_path / "c", tmp_path / "k.json", secret)
    assert default.decisions_path == tmp_path / "c" / "decisions" / "decisions.jsonl"
    moved = config_for(
        tmp_path / "c", tmp_path / "k.json", secret, tmp_path / "d.jsonl"
    )
    assert moved.decisions_path == tmp_path / "d.jsonl"


def test_verify_ledgers_checks_a_decisions_ledger_by_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from bin import verify_ledgers
    from helios.api.decisions import DECISIONS_SECRET_ENV, DecisionLedger

    secret = "d" * 32
    path = tmp_path / "decisions.jsonl"
    monkeypatch.delenv(DECISIONS_SECRET_ENV, raising=False)
    assert verify_ledgers.main(["--decisions", str(path)]) == 1  # no file, no secret
    DecisionLedger(key=secret.encode(), log_path=path).append(
        {"event": "view", "run_id": "r", "incident_id": "i", "key_id": "R1"}
    )
    assert verify_ledgers.main(["--decisions", str(path)]) == 1  # secret not loaded
    monkeypatch.setenv(DECISIONS_SECRET_ENV, secret)
    assert verify_ledgers.main(["--decisions", str(path)]) == 0
    monkeypatch.setenv(DECISIONS_SECRET_ENV, "e" * 32)
    assert verify_ledgers.main(["--decisions", str(path)]) == 1


def test_runner_keeps_its_own_lpipe_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _services()["runner"]
    assert runner["environment"]["HELIOS_LPIPE_CACHE"].startswith("/cache/")
    assert "runner-cache:/cache" in runner["volumes"]
    assert "../data:/app/data:ro" in runner["volumes"]
    import bin.helios_campaign as campaign

    try:
        monkeypatch.setenv(campaign.CACHE_ENV, "/cache/x.sqlite")
        assert Path("/cache/x.sqlite") == importlib.reload(campaign).CACHE_PATH
        monkeypatch.delenv(campaign.CACHE_ENV)
        assert importlib.reload(campaign).CACHE_PATH.parts[-3:] == (
            "data",
            "cache",
            "lpipe_cache.sqlite",
        )
    finally:
        monkeypatch.delenv(campaign.CACHE_ENV, raising=False)
        importlib.reload(campaign)


def test_console_is_pinned_on_loopback_with_a_strict_policy() -> None:
    console = _services()["console"]
    assert DIGEST.search(console["image"]) and "nginx-unprivileged" in console["image"]
    (mapping,) = console["ports"]
    match = DEFAULT.match(mapping)
    assert match and match.group(1).startswith("127.")
    assert console["networks"] == ["front"]
    assert console["read_only"] is True and console["cap_drop"] == ["ALL"]
    assert "../console:/usr/share/nginx/html:ro" in console["volumes"]
    assert console["depends_on"]["api"]["condition"] == "service_healthy"
    assert "env_file" not in console
    conf = (DEPLOY / "nginx.conf").read_text()
    csp = re.search(r'Content-Security-Policy "([^"]+)"', conf)
    assert csp
    policy = csp.group(1)
    assert "default-src 'self'" in policy and "frame-ancestors 'none'" in policy
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
    proxied = re.findall(r"location (=?\s?\S+) \{\s+proxy_pass", conf)
    assert proxied == ["/v1/", "= /health"]
    served = re.search(r"location ~ \^/\(([^)]+)\)\$", conf)
    assert served
    files = {f.replace("\\.", ".") for f in served.group(1).split("|")}
    assert files == {p.name for p in (REPO / "console").iterdir() if p.is_file()}


def test_console_never_builds_html_from_data() -> None:
    for path in (REPO / "console").glob("*.js"):
        text = path.read_text()
        for unsafe in (
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "eval(",
            "document.write",
        ):
            assert unsafe not in text, f"{path.name} uses {unsafe}"
    page = (REPO / "console" / "index.html").read_text()
    assert "<script>" not in page and " style=" not in page  # CSP: no inline code
    api = _services()["api"]["command"]
    assert api[api.index("--assignments") + 1] == "/secrets/assignments.json"


def test_runner_product_settings_default_to_the_evidence_values() -> None:
    """S4.4/S4.5: redaction off (confirmatory runs refuse it) and
    recommendation mode, unless the operator sets them."""
    env = _services()["runner"]["environment"]
    assert DEFAULT.findall(env["HELIOS_PII_REDACTION"]) == ["off"]
    assert DEFAULT.findall(env["HELIOS_ACTION_MODE"]) == ["recommend"]
