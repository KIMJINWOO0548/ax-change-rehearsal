#!/usr/bin/env python3
"""Validate package structure, references and fixture consistency.

This does not implement the proposed product, execute an AI model, validate
business effectiveness, or replace a full JSON Schema validator.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rehearsal.validation import load_json, validate_pack


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate() -> dict:
    required = [
        "README.md", "PROJECT_PLAN.md", "START_HERE.md", "AGENTS.md",
        "TASKS.md", "contracts/CONTRACTS.md", "contracts/domain-pack.schema.json",
        "docs/VALIDATION.md", "docs/DEMO.md",
    ]
    for relative in required:
        path = ROOT / relative
        check(path.is_file() and path.stat().st_size > 0, f"Missing {relative}")
    schema = json.loads((ROOT / "contracts/domain-pack.schema.json").read_text("utf-8"))
    check(schema["$schema"] == "https://json-schema.org/draft/2020-12/schema", "Schema dialect")
    check(schema["$defs"]["case"]["properties"]["expected_after"]["$ref"] == "#/$defs/expected", "Schema reference")
    paths = sorted((ROOT / "fixtures").glob("*/pack.json"))
    check(len(paths) == 3, "Expected three starter packs")
    ids, domains, behavior, per_domain = set(), set(), Counter(), {}
    statuses = {"DECIDED", "NEEDS_INPUT", "INVALID_INPUT", "UNSUPPORTED"}
    tables = {"manufacturing": "work_orders", "finance": "ledger_entries", "customer_service": "return_requests"}
    case_required = set(schema["$defs"]["case"]["required"])
    for path in paths:
        pack = load_json(path)
        validate_pack(pack, ROOT)
        check(set(pack) == set(schema["required"]), f"Pack keys: {path}")
        domain = pack["pack_id"]
        check(domain in tables and domain not in domains, f"Domain: {domain}")
        domains.add(domain)
        check(pack["schema_version"] == "1.0", f"Pack version: {domain}")
        check(pack["provenance"] == "authored_synthetic_example", f"Provenance: {domain}")
        check(pack["expert_reviewed"] is False, f"Expert-review claim: {domain}")
        check(pack["timezone"] == "Asia/Seoul", f"Timezone: {domain}")
        dt.date.fromisoformat(pack["effective_date"])
        check(pack["baseline_artifact"] != pack["candidate_artifact"], f"Artifact separation: {domain}")
        for relative in pack["source_documents"].values():
            source = (path.parent / relative).resolve()
            check(source.is_relative_to(ROOT), f"Outside reference: {relative}")
            check(source.is_file(), f"Missing source: {relative}")
            check("합성" in source.read_text("utf-8"), f"Synthetic label: {relative}")
        check(len(pack["cases"]) == 12, f"Starter case count: {domain}")
        per_domain[domain] = len(pack["cases"])
        for case in pack["cases"]:
            cid = case["id"]
            check(set(case) == case_required, f"Case keys: {cid}")
            check(cid not in ids, f"Duplicate case id: {cid}")
            ids.add(cid)
            check(set(case["business_input"]) == set(pack["input_fields"]), f"Input keys: {cid}")
            check(len(case["tags"]) == len(set(case["tags"])), f"Duplicate tags: {cid}")
            for side in ("expected_before", "expected_after"):
                expected = case[side]
                check(set(expected) == {"status", "decision", "state_delta"}, f"Expected keys: {cid}")
                check(expected["status"] in statuses, f"Status: {cid}")
                delta = expected["state_delta"]
                check(set(delta) == {"table", "count"}, f"State keys: {cid}")
                check(delta["table"] == tables[domain], f"State table: {cid}")
                check(type(delta["count"]) is int and delta["count"] >= 0, f"Count: {cid}")
                if domain == "finance" or expected["status"] != "DECIDED":
                    check(delta["count"] == 0, f"Unexpected expected write: {cid}")
                if expected["status"] != "DECIDED":
                    check(expected["decision"] == expected["status"], f"Diagnostic decision: {cid}")
            before, after = case["expected_before"], case["expected_after"]
            intent = case["intended_behavior"]
            check(intent in {"CHANGE", "PRESERVE", "INDETERMINATE"}, f"Intent: {cid}")
            if intent == "CHANGE":
                check(before != after and after["status"] == "DECIDED", f"Changed expectation: {cid}")
            elif intent == "PRESERVE":
                check(before == after and after["status"] == "DECIDED", f"Preserved expectation: {cid}")
            else:
                check(after["status"] != "DECIDED", f"Indeterminate expectation: {cid}")
            behavior[intent] += 1
    check(len(ids) == 36, "Total case count")
    for path in ROOT.rglob("*.md"):
        text = path.read_text("utf-8")
        check(text.count("```") % 2 == 0, f"Unbalanced code fence: {path}")
    return {
        "status": "passed",
        "scope": "package_structure_references_and_fixture_consistency_only",
        "packs": len(paths),
        "cases": len(ids),
        "cases_by_pack": per_domain,
        "cases_by_intended_behavior": dict(sorted(behavior.items())),
        "full_product_implemented": False,
        "prototype_source_present": (ROOT / "rehearsal/engine.py").is_file(),
        "execution_tests_performed_by_this_check": False,
        "ai_evaluation_performed": False,
        "expert_review_performed": False,
        "full_json_schema_validation_performed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable check result")
    args = parser.parse_args()
    result = validate()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Package checks passed: {result['packs']} synthetic packs, {result['cases']} scenarios.")
        print("Structure/references/fixture consistency only; product and AI performance were not tested.")


if __name__ == "__main__":
    main()

