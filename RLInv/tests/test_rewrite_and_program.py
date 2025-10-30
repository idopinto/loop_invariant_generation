import sys
import os
from pathlib import Path
import pytest

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.utils.program import Program, AssertionPointAttributes
from src.utils.rewriter import Rewriter


def _dataset_c_path(rel: str) -> Path:
    return PROJECT_ROOT / "dataset" / "evaluation" / "easy" / "c" / rel


@pytest.mark.parametrize(
    "c_filename,expected_points",
    [
        ("benchmark24_conjunctive_1.c", {7, 10}),
    ],
)
def test_program_structure_basic(c_filename, expected_points):
    c_program = _dataset_c_path(c_filename)
    if not c_program.exists():
        pytest.skip(f"Missing dataset file: {c_program}")
    r = Rewriter(c_program)
    program = Program(r.lines_to_verify, r.replacement)
    assert program.assertion_points.keys() == expected_points
    assert AssertionPointAttributes.BeginningOfLoop in program.assertion_points[min(expected_points)]
    assert AssertionPointAttributes.BeforeAssertion in program.assertion_points[max(expected_points)]