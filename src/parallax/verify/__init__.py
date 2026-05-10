"""Cluster verification — deeper comparison of units in a candidate cluster.

A :class:`Verifier` reads the source of each unit in a cluster, computes
a pairwise structural similarity, and emits a recommendation.
"""

from .core import (
    BUILTIN_VERIFIERS,
    PairSimilarity,
    Recommendation,
    Verifier,
    VerifyResult,
    verify_cluster,
)
from .python_ast import PythonAstVerifier

__all__ = [
    "BUILTIN_VERIFIERS",
    "PairSimilarity",
    "PythonAstVerifier",
    "Recommendation",
    "Verifier",
    "VerifyResult",
    "verify_cluster",
]
