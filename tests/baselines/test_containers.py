"""S4.8 container checks (B-d fidelity), run locally with the pinned images.

Skipped unless HELIOS_DOCKER_TESTS=1 and the default image is present. The
PDiagnose port must reproduce RCAEval's own script (paths pointed at a
synthetic case, nothing else changed) on a case inside the script's working
domain: one "_" per metric name, every log container and span service also a
metric service, every anomalous span operation also seen before the anomaly.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from helios.baselines.container import ADAPTER_DIR, IMAGES, DockerRunner, Limits
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.skipif(
    os.environ.get("HELIOS_DOCKER_TESTS") != "1",
    reason="container checks run locally with HELIOS_DOCKER_TESTS=1",
)

INJECT = 300
US = 1_000_000

_COMPARE = r"""
import io, json, contextlib, ast, sys
import pandas as pd
sys.path.insert(0, "/adapters")
from pdiagnose_adapter import pdiagnose
src = open("/opt/RCAEval/RCAEval/e2e/pdiagnose.py").read()
src = src.replace("./data/mm-ob/checkoutservice_cpu/1/", "/in/")
ns = {"__name__": "pdiagnose_script"}
exec(compile(src, "pdiagnose.py", "exec"), ns)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ns["main"]()
script = [k for k, _ in ast.literal_eval(buf.getvalue().strip().splitlines()[-1])]
data = {
    "metric": pd.read_csv("/in/simple_metrics.csv"),
    "logs": pd.read_csv("/in/logs.csv"),
    "traces": pd.read_csv("/in/traces.csv"),
}
port = pdiagnose(data, int(open("/in/inject_time.txt").read()))["ranks"]
print(json.dumps({"script": script, "port": port}))
"""


def _case(d: Path) -> None:
    times = list(range(600))
    pd.DataFrame(
        {
            "time": times,
            "aservice_cpu": [1 + (t % 3) for t in times],
            "bservice_cpu": [2 + (t % 2) + (9 if 300 <= t < 340 else 0) for t in times],
            "frontend_cpu": [
                5 + (t % 4) + (20 if 300 <= t < 310 else 0) for t in times
            ],
        }
    ).to_csv(d / "simple_metrics.csv", index=False)
    pd.DataFrame({"time": times[:5]}).to_csv(d / "logts.csv", index=False)
    pd.DataFrame(
        {
            "container_name": ["aservice"] * 3 + ["bservice"] * 2 + ["frontend"],
            "message": ["error a", "fail b", "ok", "error x", "ok", "fine"],
        }
    ).to_csv(d / "logs.csv", index=False)
    rows = []
    for i in range(40):
        for svc, op, base in (("aservice", "Get", 1000), ("frontend", "Home", 3000)):
            t = 10 + i * 14
            slow = t >= INJECT and svc == "aservice" and i % 2 == 0
            rows.append(
                {
                    "serviceName": svc,
                    "methodName": op,
                    "operationName": op,
                    "startTime": t * US,
                    "duration": base * (40 if slow else 1) + (i % 5) * 10,
                }
            )
    pd.DataFrame(rows).to_csv(d / "traces.csv", index=False)
    (d / "inject_time.txt").write_text(f"{INJECT}\n")


def test_pdiagnose_port_matches_the_script(tmp_path: Path) -> None:
    tag, _ = IMAGES["default"]
    if subprocess.run(
        ["docker", "image", "inspect", tag], capture_output=True, check=False
    ).returncode:
        pytest.skip(f"{tag} not built")
    d = tmp_path / "in"
    d.mkdir()
    _case(d)
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{d}:/in:ro",
            "-v",
            f"{ADAPTER_DIR}:/adapters:ro",
            tag,
            "python",
            "-c",
            _COMPARE,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["script"] == out["port"]
    assert len(out["port"]) == 3


def test_docker_runner_checks_the_pinned_digest() -> None:
    runner = DockerRunner()
    assert runner.check_image("default") == IMAGES["default"][1]
    assert Limits().timeout_s == 1800
