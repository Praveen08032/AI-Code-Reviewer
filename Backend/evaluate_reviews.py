r"""Run labeled static-review examples against real Gemini; never execute submitted code.

Run from Backend: .\venv\Scripts\python.exe evaluate_reviews.py
Each case consumes one provider request. Stop on quota errors rather than retrying.
"""
import argparse
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import statistics
import time

from app.ai_utils import AIServiceError, REVIEW_INSTRUCTIONS, get_gemini_feedback, parse_ai_feedback

ROOT = Path(__file__).resolve().parent


def summarize(rows, planned):
    completed = [row for row in rows if "review" in row]
    decisive = [row for row in completed if row["observed"] != "uncertain"]
    tp = sum(row["expected"] == row["observed"] == "issues_found" for row in decisive)
    fp = sum(row["expected"] == "no_issues" and row["observed"] == "issues_found" for row in decisive)
    fn = sum(row["expected"] == "issues_found" and row["observed"] == "no_issues" for row in decisive)
    durations = [row["seconds"] for row in completed]
    return {"planned": planned, "attempted": len(rows), "completed": len(completed),
            "provider_failures": len(rows) - len(completed), "uncertain": len(completed) - len(decisive),
            "agreement": sum(row["expected"] == row["observed"] for row in completed) / len(completed) if completed else None,
            "bug_precision": tp / (tp + fp) if tp + fp else None,
            "bug_recall_decisive_cases": tp / (tp + fn) if tp + fn else None,
            "false_alarms": fp, "missed_bugs": fn,
            "expected_issue_mentioned": sum(row.get("expected_issue_mentioned", False) for row in completed if row["expected"] == "issues_found"),
            "median_seconds": round(statistics.median(durations), 2) if durations else None,
            "max_seconds": max(durations) if durations else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "results" / "latest.json")
    args = parser.parse_args()
    cases = json.loads((ROOT / "evaluation" / "cases.json").read_text(encoding="utf-8"))[:max(1, args.limit)]
    report = {"started_at": datetime.now(timezone.utc).isoformat(),
              "model": os.getenv("GEMINI_MODEL", "models/gemini-flash-latest"),
              "review_instructions_sha256": hashlib.sha256(REVIEW_INSTRUCTIONS.encode()).hexdigest(),
              "scope": "Static AI classification against manually labeled examples. No submitted or improved code was compiled/executed. This is not proof of correctness or a security certification.",
              "cases": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for case in cases:
        started = time.monotonic()
        row = {"id": case["id"], "language": case["language"], "expected": case["expected"]}
        stop = False
        try:
            review = parse_ai_feedback(get_gemini_feedback(case["language"], case["code"],
                                       problem_description=case["requirements"], review_mode="custom"))
            observed = ("uncertain" if not review["review_complete"] else "issues_found" if review["errors"] or review["missing_items"] or
                        review["correctness_status"] == "incorrect" else "no_issues" if review["correctness_status"] == "correct" else "uncertain")
            issues = " ".join(review["errors"] + review["missing_items"]).lower()
            row.update(review=review, observed=observed,
                       expected_issue_mentioned=any(term in issues for term in case["issue_terms"]))
        except AIServiceError as error:
            row.update(error=str(error), status=error.status_code)
            stop = error.status_code in {429, 503}
        row["seconds"] = round(time.monotonic() - started, 2)
        report["cases"].append(row)
        report["summary"] = summarize(report["cases"], len(cases))
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{case['id']}: {row.get('observed', 'provider failure')} ({row['seconds']}s)", flush=True)
        if stop:
            break
    print(json.dumps(report["summary"], indent=2), flush=True)
    return 1 if report["summary"]["provider_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
