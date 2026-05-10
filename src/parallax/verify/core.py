"""Verifier interface and orchestration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence


class Recommendation(str, Enum):
    MERGE = "merge"
    SHARED_HELPER = "shared_helper"
    UNRELATED = "unrelated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PairSimilarity:
    a_location: str
    b_location: str
    score: float  # 0..1
    notes: str = ""


@dataclass(frozen=True)
class VerifyResult:
    verifier: str
    pairs: list[PairSimilarity]
    mean_similarity: float
    recommendation: Recommendation


class Verifier(ABC):
    """Compare units in a cluster and recommend a consolidation strategy."""

    name: str

    @abstractmethod
    def supports(self, languages: set[str]) -> bool:
        """Return True if this verifier can analyse units of these languages."""

    @abstractmethod
    def verify(
        self,
        unit_locations: Sequence[str],
        *,
        root: Path,
    ) -> VerifyResult:
        """Analyse the units and return a :class:`VerifyResult`."""


def _recommendation_for(mean: float) -> Recommendation:
    if mean >= 0.85:
        return Recommendation.MERGE
    if mean >= 0.55:
        return Recommendation.SHARED_HELPER
    if mean > 0.0:
        return Recommendation.UNRELATED
    return Recommendation.UNKNOWN


def verify_cluster(
    cluster: dict,
    *,
    root: Path,
    verifiers: Iterable[Verifier] | None = None,
) -> list[VerifyResult]:
    """Run every applicable verifier against the cluster.

    ``cluster`` is the JSON-shaped dict returned by the JSON reporter
    (so this works on output piped from ``parallax scan --format json``).
    """
    if verifiers is None:
        verifiers = [cls() for cls in BUILTIN_VERIFIERS.values()]
    languages = {u.get("language", "") for u in cluster.get("units", [])}
    languages.discard("")
    locations = [u["location"] for u in cluster.get("units", [])]
    results: list[VerifyResult] = []
    for v in verifiers:
        if v.supports(languages):
            results.append(v.verify(locations, root=root))
    return results


# Populated after PythonAstVerifier is defined to avoid a forward reference.
BUILTIN_VERIFIERS: dict[str, type[Verifier]] = {}


def register_default_verifiers() -> None:
    from .python_ast import PythonAstVerifier

    BUILTIN_VERIFIERS["python-ast"] = PythonAstVerifier


register_default_verifiers()
