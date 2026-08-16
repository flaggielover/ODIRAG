from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "verify-production-integrity.py"
SPEC = importlib.util.spec_from_file_location("verify_production_integrity", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _ids() -> list[str]:
    return [f"chunk-{index:04d}" for index in range(MODULE.EXPECTED_CHUNKS)]


def test_exact_id_sets_pass() -> None:
    values = _ids()
    digest = MODULE._validate_id_sets(values, values.copy(), values.copy())
    assert len(digest) == 64


@pytest.mark.parametrize("failure", ["duplicate", "set_mismatch", "point_mismatch"])
def test_id_integrity_failures(failure: str) -> None:
    postgres = _ids()
    payload = postgres.copy()
    points = postgres.copy()
    if failure == "duplicate":
        payload[-1] = payload[0]
        points[-1] = points[0]
    elif failure == "set_mismatch":
        payload[-1] = "different-chunk"
        points[-1] = "different-chunk"
    else:
        points[-1] = "different-point"
    with pytest.raises(MODULE.VerificationError):
        MODULE._validate_id_sets(postgres, payload, points)


def test_vector_shape_rejects_named_vectors() -> None:
    with pytest.raises(MODULE.VerificationError):
        MODULE._vector_shape(
            {"config": {"params": {"vectors": {"default": {"size": 1536}}}}}
        )
