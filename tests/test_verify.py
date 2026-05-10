from pathlib import Path

from parallax.verify import PythonAstVerifier, Recommendation, verify_cluster


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "verify_app"


def test_near_identical_functions_recommend_merge():
    cluster = {
        "units": [
            {"location": "a.py:1", "language": "python"},
            {"location": "b.py:1", "language": "python"},
        ]
    }
    results = verify_cluster(cluster, root=FIXTURE_ROOT)
    assert results
    r = results[0]
    assert r.mean_similarity > 0.85
    assert r.recommendation == Recommendation.MERGE


def test_unrelated_functions_recommend_unrelated():
    cluster = {
        "units": [
            {"location": "a.py:1", "language": "python"},
            {"location": "c.py:1", "language": "python"},
        ]
    }
    results = verify_cluster(cluster, root=FIXTURE_ROOT)
    r = results[0]
    assert r.mean_similarity < 0.55
    assert r.recommendation in {Recommendation.UNRELATED, Recommendation.SHARED_HELPER}


def test_supports_filters_non_python_languages():
    v = PythonAstVerifier()
    assert v.supports(set()) is True
    assert v.supports({"python"}) is True
    assert v.supports({"go"}) is False
