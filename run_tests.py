"""
Runs the 10 evaluation questions, saves the results, and updates the README table.

Run:  python run_tests.py

Outputs:
  results/test_results.json  - full details (answer, tools used, guardrail notes)
  results/test_results.md    - the markdown table
  README.md                  - the table between the TEST_RESULTS markers is replaced
"""

import json
import time
from datetime import datetime
from pathlib import Path

from helpdesk.agent import ask
from tests.cases import CASES

ROOT = Path(__file__).parent
RESULTS_DIR = ROOT / "results"
README = ROOT / "README.md"
START, END = "<!-- TEST_RESULTS_START -->", "<!-- TEST_RESULTS_END -->"
PAUSE_SECONDS = 5   # small gap between questions to respect Gemini free-tier rate limits


def _cell(text: str) -> str:
    """Make text safe for a one-line markdown table cell."""
    return text.replace("|", "\\|").replace("\n", "<br>").strip()


def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    rows = []
    for case in CASES:
        print(f"[{case['id']:>2}/{len(CASES)}] {case['question']}")
        try:
            result = ask(case["question"])
            passed = bool(case["check"](result))
        except Exception as e:
            result = {"answer": f"ERROR: {type(e).__name__}: {e}", "blocked": False,
                      "block_reason": "", "tool_log": [], "notes": []}
            passed = False
        print(f"      -> {'PASS' if passed else 'FAIL'}: {result['answer'][:100]!r}")
        rows.append({**{k: case[k] for k in ("id", "category", "question", "expect")},
                     "answer": result["answer"], "passed": passed,
                     "blocked": result["blocked"], "block_reason": result["block_reason"],
                     "tools": [t["tool"] for t in result["tool_log"]], "notes": result["notes"]})
        time.sleep(PAUSE_SECONDS)

    passed = sum(r["passed"] for r in rows)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    (RESULTS_DIR / "test_results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    lines = [
        f"**{passed}/{len(rows)} passed** — run on {stamp} (`python run_tests.py`)",
        "",
        "| # | Category | Question | Agent's actual answer | Tools / guardrails | Result |",
        "|---|----------|----------|-----------------------|--------------------|--------|",
    ]
    for r in rows:
        how = ", ".join(r["tools"]) or (f"blocked: {r['block_reason']}" if r["blocked"] else "—")
        if r["notes"]:
            how += "<br>" + ", ".join(r["notes"])
        lines.append(f"| {r['id']} | {r['category']} | {_cell(r['question'])} | {_cell(r['answer'])} "
                     f"| {_cell(how)} | {'✅ Pass' if r['passed'] else '❌ Fail'} |")
    table = "\n".join(lines)
    (RESULTS_DIR / "test_results.md").write_text(table + "\n")

    readme = README.read_text()
    if START in readme and END in readme:
        before, rest = readme.split(START, 1)
        _, after = rest.split(END, 1)
        README.write_text(f"{before}{START}\n{table}\n{END}{after}")
        print("\nREADME.md test table updated.")
    print(f"Result: {passed}/{len(rows)} passed. Details in results/test_results.json")


if __name__ == "__main__":
    main()
