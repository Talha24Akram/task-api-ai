"""Run evals/cases.json through the live endpoint and print the score.

Usage: python evals/run_eval.py [base_url]   (default http://127.0.0.1:8000)
Needs the server to be running. Key field: category.
"""
import json
import sys
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
cases = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))


def triage(text: str):
    req = urllib.request.Request(f"{BASE}/tasks/triage", data=json.dumps({"text": text}).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


hits, failures, low_ok, low_total = 0, [], 0, 0
for c in cases:
    status, out = triage(c["text"])
    got = out.get("category") if status == 200 else f"HTTP {status}"
    ok = got == c["expected_category"]
    hits += ok
    if c.get("expect_low_confidence"):
        low_total += 1
        low_ok += status == 200 and out.get("confidence", 1) < 0.5
    print(f"{'PASS' if ok else 'FAIL'} #{c['id']} [{c['kind']}] expected={c['expected_category']} got={got} "
          f"priority={out.get('priority')} conf={out.get('confidence')}")
    if not ok:
        failures.append((c["id"], c["text"], c["expected_category"], got))

print(f"\ncategory match: {hits}/{len(cases)} = {100 * hits / len(cases):.0f}%")
print(f"'when unsure' cases with confidence < 0.5: {low_ok}/{low_total}")
for f in failures:
    print("failed:", f)
