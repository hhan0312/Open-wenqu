from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    cases_dir = repo / "evals" / "cases"
    case_files = sorted(cases_dir.glob("*.json"))
    if not case_files:
        print("No eval cases found.")
        return 0

    print("Eval harness (V1 minimal):")
    for p in case_files:
        data = json.loads(p.read_text(encoding="utf-8"))
        print(f"- {p.name}: expect_n={data.get('expected_question_count')} min_quality={data.get('min_avg_quality')}")

    print("\n说明：完整评测需要可复现的 fake LLM / 固定随机种子与后端入口；当前仓库先落地 case 格式与 CI 钩子。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
