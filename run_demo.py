"""Run the existing synthetic prototype and write its reproducible results."""
from pathlib import Path
import json

from rehearsal.adapters import VARIANTS
from rehearsal.engine import run_suite


if __name__ == "__main__":
    result = run_suite(list(VARIANTS))
    output = Path(__file__).resolve().parent / "results" / "rehearsal_results.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for summary in result["summaries"]:
        print(summary["variant"], summary["business_counts"], summary["assertion_counts"])
    print("Saved:", output)
    print("Synthetic mocks only. Injected failures are expected. No LLM or real enterprise service was used.")

