from __future__ import annotations

import json
from pathlib import Path

from silki_ai.nlp import deterministic_refinement

CASES = Path(__file__).parent / "data" / "query_refinement.jsonl"


def main() -> int:
    total = 0
    passed = 0
    for line in CASES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        result = deterministic_refinement(case["utterance"])
        actual = {
            "search_query": result.search_query,
            "quantity": result.quantity,
            **result.attributes.model_dump(),
        }
        expected = case["expected"]
        ok = all(actual.get(key) == value for key, value in expected.items())
        total += 1
        passed += int(ok)
        print(f"{'PASS' if ok else 'FAIL'} {case['id']}: {actual}")

    print(f"{passed}/{total} cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
