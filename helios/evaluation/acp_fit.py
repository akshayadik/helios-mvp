"""ACP fit on build data (S3.2 design P-a, P-d; entry 82).

The only labels are injected fault types, mapped to remediation families by
``FAULT_CLASS`` (fixed in the pre-run entry, before any fit). The model is a
multinomial logistic regression on standardised features, L2 with lambda on
every weight but the bias. Folds need no random seed: cases are ordered by
corpus, class and the SHA-256 of their opaque incident ID and dealt
round-robin, so the split is a pure function of frozen inputs.

Build data only; this module is the only ACP code that reads labels, and the
runtime package ``helios.acp`` never imports it.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy.optimize import minimize

from helios.acp.features import ACP_FEATURE_NAMES
from helios.acp.params import ACP_CLASSES, ACPParams
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "FAULT_CLASS",
    "ACPCase",
    "cross_fit",
    "fit_params",
    "folds",
    "scores",
]

HELIOS_ENABLE_ACP_FIT: bool = True

# Design P-a: remediation family of each build fault type (entry 82).
FAULT_CLASS: dict[str, str] = {
    "cpu": "resource",
    "mem": "resource",
    "disk": "resource",
    "adHighCpu": "resource",
    "adManualGc": "resource",
    "emailMemoryLeak": "resource",
    "delay": "network",
    "loss": "network",
    "socket": "network",
    "adFailure": "config",
    "cartFailure": "config",
    "paymentFailure": "config",
    "paymentUnreachable": "config",
    "productCatalogFailure": "config",
    "recommendationCacheFailure": "config",
    "f1": "code",
    "f2": "code",
    "f3": "code",
    "f4": "code",
    "f5": "code",
}
_DIGITS = 6
_EPS = 1e-12
_MAXITER = 5000
_GTOL = 1e-8


@dataclass(frozen=True)
class ACPCase:
    """One build case: its ACP features (from the run's CoE entry) and class."""

    incident_id: str
    corpus: str
    x: tuple[float, ...]
    label: str


def folds(cases: Sequence[ACPCase], k: int) -> list[int]:
    """Fold index of each case: stratified by corpus and class, seed-free."""
    order = sorted(
        range(len(cases)),
        key=lambda i: (
            cases[i].corpus,
            cases[i].label,
            hashlib.sha256(cases[i].incident_id.encode("utf-8")).hexdigest(),
        ),
    )
    out = [0] * len(cases)
    for rank, i in enumerate(order):
        out[i] = rank % k
    return out


def _standardisation(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    mean[0] = 0  # bias column stays as is
    scale[0] = 1
    scale[scale <= _EPS] = 1  # a constant column is left centred
    return mean, scale


def fit_params(cases: Sequence[ACPCase], lam: float) -> ACPParams:
    """Multinomial logistic regression on ``cases`` (deterministic L-BFGS)."""
    if not cases:
        raise ValueError("no cases to fit")
    x = np.array([c.x for c in cases], dtype=float)
    y = np.array([ACP_CLASSES.index(c.label) for c in cases])
    mean, scale = _standardisation(x)
    z = (x - mean) / scale
    k, d = len(ACP_CLASSES), x.shape[1]
    onehot = np.eye(k)[y]
    penal = np.ones(d)
    penal[0] = 0

    def loss(flat: np.ndarray) -> tuple[float, np.ndarray]:
        w = flat.reshape(k, d)
        logits = z @ w.T
        logits -= logits.max(axis=1, keepdims=True)
        p = np.exp(logits)
        p /= p.sum(axis=1, keepdims=True)
        nll = -float(np.sum(onehot * np.log(p + _EPS)))
        reg = lam / 2 * float(np.sum((w * penal) ** 2))
        grad = (p - onehot).T @ z + lam * w * penal
        return nll + reg, grad.ravel()

    res = minimize(
        loss,
        np.zeros(k * d),
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": _MAXITER, "gtol": _GTOL},
    )
    if not res.success:
        raise RuntimeError(f"ACP fit did not converge: {res.message}")
    w = res.x.reshape(k, d)
    return ACPParams(
        feature_names=ACP_FEATURE_NAMES,
        classes=ACP_CLASSES,
        mean=tuple(round(float(v), _DIGITS) for v in mean),
        scale=tuple(round(float(v), _DIGITS) for v in scale),
        weights=tuple(tuple(round(float(v), _DIGITS) for v in row) for row in w),
        lam=lam,
        n_cases=len(cases),
    )


def cross_fit(cases: Sequence[ACPCase], lam: float, k: int) -> list[dict[str, float]]:
    """Held-out class probabilities for every case (k-fold cross-fitting)."""
    fold = folds(cases, k)
    out: list[dict[str, float]] = [{} for _ in cases]
    for f in range(k):
        train = [c for c, g in zip(cases, fold, strict=True) if g != f]
        params = fit_params(train, lam)
        for i, (c, g) in enumerate(zip(cases, fold, strict=True)):
            if g == f:
                out[i] = params.probabilities(c.x)
    return out


def _predicted(probs: dict[str, float]) -> str:
    return max(ACP_CLASSES, key=lambda c: (probs[c], -ACP_CLASSES.index(c)))


def scores(
    cases: Sequence[ACPCase], probs: Sequence[dict[str, float]]
) -> dict[str, Any]:
    """Accuracy, macro-F1, log loss and the confusion (rows = true class)."""
    n = len(cases)
    confusion = {t: dict.fromkeys(ACP_CLASSES, 0) for t in ACP_CLASSES}
    log_loss: float = 0
    for c, p in zip(cases, probs, strict=True):
        confusion[c.label][_predicted(p)] += 1
        log_loss -= math.log(max(p[c.label], _EPS))
    correct = sum(confusion[t][t] for t in ACP_CLASSES)
    f1s: list[float] = []
    for cls in ACP_CLASSES:
        tp = confusion[cls][cls]
        fp = sum(confusion[t][cls] for t in ACP_CLASSES if t != cls)
        fn = sum(confusion[cls][q] for q in ACP_CLASSES if q != cls)
        if tp + fn == 0:
            continue  # a class absent from these cases has no F1
        denom = 2 * tp + fp + fn
        f1s.append(2 * tp / denom if denom else 0)
    return {
        "cases": n,
        "accuracy": round(correct / n, _DIGITS) if n else None,
        "macro_f1": round(sum(f1s) / len(f1s), _DIGITS) if f1s else None,
        "log_loss": round(log_loss / n, _DIGITS) if n else None,
        "confusion": confusion,
    }
