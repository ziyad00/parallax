"""Python AST verifier.

Compares the bodies of the units in a cluster via a normalised AST
fingerprint. Strips identifier names, replaces literals with type
tags, then computes pairwise sequence-matcher similarity over the
resulting node-type stream.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Sequence

from difflib import SequenceMatcher

from .core import PairSimilarity, Recommendation, Verifier, VerifyResult, _recommendation_for


class PythonAstVerifier(Verifier):
    name = "python-ast"

    def supports(self, languages: set[str]) -> bool:
        return not languages or "python" in languages

    def verify(
        self, unit_locations: Sequence[str], *, root: Path
    ) -> VerifyResult:
        fingerprints: list[tuple[str, str]] = []
        for loc in unit_locations:
            file, _, lineno_s = loc.rpartition(":")
            try:
                lineno = int(lineno_s)
            except ValueError:
                continue
            fp = _fingerprint_function(root / file, lineno)
            if fp is None:
                continue
            fingerprints.append((loc, fp))

        pairs: list[PairSimilarity] = []
        for i in range(len(fingerprints)):
            for j in range(i + 1, len(fingerprints)):
                a_loc, a = fingerprints[i]
                b_loc, b = fingerprints[j]
                ratio = SequenceMatcher(None, a, b).ratio()
                pairs.append(PairSimilarity(a_loc, b_loc, ratio))

        mean = sum(p.score for p in pairs) / len(pairs) if pairs else 0.0
        return VerifyResult(
            verifier=self.name,
            pairs=pairs,
            mean_similarity=mean,
            recommendation=_recommendation_for(mean),
        )


def _fingerprint_function(path: Path, lineno: int) -> str | None:
    if not path.exists():
        return None
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None
    target: ast.AST | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if getattr(node, "lineno", -1) == lineno:
                target = node
                break
    if target is None:
        return None
    return _ast_fingerprint(target)


def _ast_fingerprint(node: ast.AST) -> str:
    """Stream of node types + literal type tags, ignoring identifiers."""
    tokens: list[str] = []
    for child in ast.walk(node):
        tokens.append(type(child).__name__)
        if isinstance(child, ast.Constant):
            tokens.append(type(child.value).__name__)
    return "|".join(tokens)
