"""Golden-file helper for the protect-existing harness.

Regenerate intentionally with EQ_UPDATE_GOLDENS=1 and explain why in the PR.
Goldens are compared as parsed JSON so checkout line endings do not matter.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def canonical(payload):
    return json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def assert_golden(test, name: str, payload) -> None:
    path = GOLDEN_DIR / f"{name}.json"
    actual = canonical(payload)
    if os.environ.get("EQ_UPDATE_GOLDENS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(actual, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return
    if not path.is_file():
        test.fail(f"Missing golden {path.name}. Regenerate with EQ_UPDATE_GOLDENS=1 and note why.")
    expected = json.loads(path.read_text(encoding="utf-8"))
    test.assertEqual(actual, expected, f"Golden mismatch: {path.name}")
