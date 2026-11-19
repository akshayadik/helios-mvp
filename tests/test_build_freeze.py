"""S5.6 build freeze: the record and the check that blocks a diverging build
(design s5_6_build_freeze_design.md F-a, F-b)."""

from __future__ import annotations

import builtins
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from bin import build_freeze
from helios.evaluation.scoring import Corpus
from helios.pipelines.l_pipe.lpipe_config import EXPECTED_MODEL_DIGEST
from helios.telemetry import pool_lock
from helios.vcl import freeze
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.variants import CONFIRMATORY_VARIANTS, EXPLORATORY_VARIANTS

REPO = Path(__file__).resolve().parent.parent
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]


@pytest.fixture(autouse=True)
def _fresh_cache() -> Any:
    freeze.clear_cache()
    yield
    freeze.clear_cache()


def _repo(path: Path) -> Path:
    """A small repository with one file in each kind of frozen path."""
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    for name, text in {
        "helios/core.py": "A = 1\n",
        "bin/tool.py": "B = 2\n",
        "data/frozen/params.json": "{}\n",
        "poetry.lock": "lock\n",
        "docs/notes.md": "not frozen\n",
    }.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text)
    subprocess.run([*GIT, "add", "-A"], cwd=path, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "build"], cwd=path, check=True)
    return path


def _freeze(repo: Path) -> None:
    """Write the record, commit it and tag the commit, as step 3 and 4 do."""
    record = repo / freeze.RECORD_PATH
    record.write_text(json.dumps({"frozen_paths": freeze.frozen_paths_section(repo)}))
    subprocess.run([*GIT, "add", "-A"], cwd=repo, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "freeze"], cwd=repo, check=True)
    subprocess.run(["git", "tag", freeze.BUILD_FREEZE_TAG], cwd=repo, check=True)
    freeze.clear_cache()


def test_frozen_paths_cover_code_parameters_and_lock_but_not_docs(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path / "r")
    files = freeze.path_digests(repo)
    assert set(files) == {
        "helios/core.py",
        "bin/tool.py",
        "data/frozen/params.json",
        "poetry.lock",
    }
    section = freeze.frozen_paths_section(repo)
    assert section["count"] == len(files)
    assert section["digest"] == freeze.tree_digest(files)


def test_the_record_itself_is_not_a_frozen_path(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "r")
    _freeze(repo)
    assert freeze.RECORD_PATH not in freeze.path_digests(repo)


def test_an_untouched_frozen_build_unlocks_the_pool(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "r")
    _freeze(repo)
    assert freeze.freeze_problems(repo) == []
    assert pool_lock.build_frozen(repo)
    pool_lock.require_unlocked("case-1", repo)


def test_the_tag_alone_does_not_unlock(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "r")
    subprocess.run(["git", "tag", freeze.BUILD_FREEZE_TAG], cwd=repo, check=True)
    assert freeze.freeze_problems(repo) == [f"{freeze.RECORD_PATH} is missing"]
    assert not pool_lock.build_frozen(repo)


def test_no_tag_is_locked(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "r")
    assert freeze.freeze_problems(repo) == ["git tag 'build-freeze' does not exist"]


def test_a_changed_frozen_file_blocks_a_pool_run_and_is_named(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "r")
    _freeze(repo)
    (repo / "helios/core.py").write_text("A = 2\n")
    freeze.clear_cache()
    assert freeze.freeze_problems(repo) == ["changed: helios/core.py"]
    with pytest.raises(pool_lock.PoolLockedError, match="changed: helios/core.py"):
        pool_lock.require_unlocked("case-1", repo)


def test_added_missing_and_untracked_files_block(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "r")
    _freeze(repo)
    (repo / "bin/tool.py").unlink()
    (repo / "helios/new.py").write_text("C = 3\n")
    (repo / "helios/stray.py").write_text("D = 4\n")
    subprocess.run([*GIT, "add", "helios/new.py", "bin/tool.py"], cwd=repo, check=True)
    freeze.clear_cache()
    assert freeze.freeze_problems(repo) == [
        "missing: bin/tool.py",
        "added: helios/new.py",
        "untracked: helios/stray.py",
    ]


def test_a_change_outside_the_frozen_paths_does_not_block(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "r")
    _freeze(repo)
    (repo / "docs/notes.md").write_text("Stage B notes\n")
    freeze.clear_cache()
    assert freeze.freeze_problems(repo) == []


def test_a_regenerated_record_does_not_pass_for_the_tagged_one(tmp_path: Path) -> None:
    """Changing code and rewriting the record still differs from the tag."""
    repo = _repo(tmp_path / "r")
    _freeze(repo)
    (repo / "helios/core.py").write_text("A = 2\n")
    record = repo / freeze.RECORD_PATH
    record.write_text(json.dumps({"frozen_paths": freeze.frozen_paths_section(repo)}))
    freeze.clear_cache()
    assert freeze.freeze_problems(repo) == [
        f"{freeze.RECORD_PATH} differs from the record at tag 'build-freeze'"
    ]


def test_without_a_repository_the_pool_stays_locked(tmp_path: Path) -> None:
    problems = freeze.freeze_problems(tmp_path)
    assert problems
    assert not pool_lock.build_frozen(tmp_path)


def test_the_pool_label_files_are_never_frozen_paths() -> None:
    names = " ".join([*freeze.FROZEN_DIRS, *freeze.FROZEN_FILES])
    assert "ground_truth" not in names
    assert "checksums" not in names
    assert not any(n.startswith("data/rcaeval/") for n in freeze.FROZEN_DIRS)


def test_the_record_is_deterministic_and_never_opens_a_label_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []
    real_open = builtins.open
    real_read_bytes = Path.read_bytes
    real_read_text = Path.read_text

    def spy_open(file: Any, *a: Any, **k: Any) -> Any:
        opened.append(str(file))
        return real_open(file, *a, **k)

    def spy_bytes(self: Path) -> bytes:
        opened.append(str(self))
        return real_read_bytes(self)

    def spy_text(self: Path, *a: Any, **k: Any) -> str:
        opened.append(str(self))
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(Path, "read_bytes", spy_bytes)
    monkeypatch.setattr(Path, "read_text", spy_text)
    first = build_freeze.render(build_freeze.build_record(REPO))
    second = build_freeze.render(build_freeze.build_record(REPO))
    assert first == second
    assert not [p for p in opened if "ground_truth" in p or "checksums" in p]


def test_the_record_names_every_part_of_the_design() -> None:
    record = build_freeze.build_record(REPO)
    assert set(record) >= {
        "parameters",
        "price_book",
        "model",
        "images",
        "variants",
        "versions",
        "pool",
        "stage_b_moves",
        "frozen_paths",
    }
    frozen = [
        p
        for p in (REPO / "data/frozen").glob("*.json")
        if p.name != "build_freeze.json"
    ]
    assert len(record["parameters"]) == len(frozen)
    assert len(record["variants"]) == len(
        {**CONFIRMATORY_VARIANTS, **EXPLORATORY_VARIANTS}
    )
    assert record["model"]["digest"] == EXPECTED_MODEL_DIGEST
    assert record["pool"]["cases"] == 240
    assert all(m["entries"] for m in record["stage_b_moves"])
    assert any("ollama" in pin for pins in record["images"].values() for pin in pins)


def test_cli_verify_fails_without_a_record_and_check_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path / "r")
    assert build_freeze.main(["--check", "--root", str(repo)]) == 1
    assert "NOT the frozen build" in capsys.readouterr().out


# ── pool campaigns carry the frozen digest (F-b) ───────────────────────────


def _campaign_repo(tmp_path: Path, digest: str) -> Path:
    root = tmp_path / "root"
    (root / "data/frozen").mkdir(parents=True)
    (root / freeze.RECORD_PATH).write_text(
        json.dumps({"frozen_paths": {"digest": digest}})
    )
    return root


def test_a_pool_campaign_is_refused_with_the_reasons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bin import helios_campaign as hc

    monkeypatch.setattr(hc, "build_frozen", lambda: False)
    monkeypatch.setattr(hc, "lock_reasons", lambda: ["changed: helios/core.py"])
    with pytest.raises(pool_lock.PoolLockedError, match="changed: helios/core.py"):
        hc._check_pool(Corpus.POOL)
    hc._check_pool("rcaeval_build")  # build corpora are not affected


def test_a_pool_plan_records_the_frozen_digest_and_a_run_checks_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse

    from bin import helios_campaign as hc

    root = _campaign_repo(tmp_path, "d1")
    monkeypatch.setattr(hc, "REPO_ROOT", root)
    monkeypatch.setattr(hc, "build_frozen", lambda: True)

    class _Schedule:
        digest = "s" * 12
        refused: tuple[str, ...] = ()
        rerun_cases: tuple[str, ...] = ()
        eh5_cases: tuple[str, ...] = ()
        specs: tuple[Any, ...] = ()

        def counts(self) -> dict[str, int]:
            return {}

    monkeypatch.setattr(hc, "schedule_for", lambda config, key: _Schedule())
    monkeypatch.setattr(hc, "exclusion_ledger", lambda d, c, k: None)
    monkeypatch.setattr(hc, "executors", lambda *a, **k: {})
    monkeypatch.setattr(hc, "baseline_executors", lambda *a, **k: {})

    class _Campaign:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        def run(self, phases: list[str], limit: Any = None) -> int:
            return 0

    monkeypatch.setattr(hc, "Campaign", _Campaign)
    directory = tmp_path / "campaign"
    plan = argparse.Namespace(
        dir=directory,
        manifest=Path("m.json"),
        gt_corpus=Corpus.POOL,
        captures=Path("c"),
    )
    assert hc.cmd_plan(plan, b"k") == 0
    config = json.loads((directory / hc.CONFIG).read_text())
    assert config["build_freeze_digest"] == "d1"

    run = argparse.Namespace(dir=directory, phase=[], cache_only=True, limit=None)
    assert hc.cmd_run(run, b"k") == 0
    (root / freeze.RECORD_PATH).write_text(
        json.dumps({"frozen_paths": {"digest": "d2"}})
    )
    assert hc.cmd_run(run, b"k") == 2
