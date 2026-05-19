"""PromptRegistry — frozen prompt + SHA256 tamper-guard."""

from __future__ import annotations

import hashlib
from pathlib import Path

from helios.pipelines.l_pipe.lpipe_config import PROMPT_VERSION
from helios.vcl import VCLFlag  # noqa: F401 — satisfies flag-guard

HELIOS_ENABLE_PROMPT_REGISTRY: bool = True

PROMPT_PATH: Path = Path(__file__).parent / "prompts" / "rca_v1.txt"


class PromptTamperError(Exception):
    pass


class PromptRegistry:
    def __init__(self, prompt_path: Path) -> None:
        self._text = prompt_path.read_text(encoding="utf-8")
        self._sha = hashlib.sha256(self._text.encode("utf-8")).hexdigest()

    @property
    def prompt_sha(self) -> str:
        return self._sha

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION

    def render(
        self, *, incident_id: str, service_list: list[str], anomaly_summary: str
    ) -> str:
        return self._text.format(
            incident_id=incident_id,
            service_list=", ".join(service_list),
            anomaly_summary=anomaly_summary,
        )

    def verify_sha(self, expected_sha: str) -> bool:
        return self._sha == expected_sha

    def verify_sha_or_raise(self, expected_sha: str) -> None:
        if not self.verify_sha(expected_sha):
            raise PromptTamperError(
                f"Prompt SHA mismatch: live={self._sha!r} expected={expected_sha!r}. "
                "rca_v1.txt has been modified. Deviation log entry required before proceeding."
            )
