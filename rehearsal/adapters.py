"""Trusted mock adapters. They receive business input, never fixture oracles.

Environments isolate in-memory state; this is not an OS/process security sandbox.
No module in this prototype performs network I/O or invokes a language model.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any


VARIANTS = (
    "normal", "stale_candidate", "boundary", "exception_removed",
    "wrong_effective_scope", "false_success", "duplicate_effect", "wrong_target",
    "unknown_as_zero", "observer_timeout", "unexpected_write",
)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


class OperationConflict(ValueError):
    pass


@dataclass
class Environment:
    artifact: str
    variant: str
    rows: list[dict] = field(default_factory=list)
    receipts: dict[str, tuple[str, dict]] = field(default_factory=dict)
    invocation_count: int = 0


def observe(environment: Environment) -> list[dict]:
    """Read actual mock storage, independently from the adapter response."""
    if environment.variant == "observer_timeout" and environment.invocation_count:
        raise TimeoutError("Injected observation timeout; effects are unknown")
    return copy.deepcopy(environment.rows)


class MockAdapter:
    table: str
    target_field: str
    fields: dict[str, str]
    effect_decisions: frozenset[str] = frozenset()

    def create_environment(self, artifact: str, variant: str = "normal") -> Environment:
        if artifact not in {"baseline_v1", "candidate_v2"} or variant not in VARIANTS:
            raise ValueError("Unsupported artifact or variant")
        return Environment(artifact, variant)

    def validate(self, data: dict) -> str | None:
        if any(name not in data or data[name] is None for name in self.fields):
            return "NEEDS_INPUT"
        for name, kind in self.fields.items():
            value = data[name]
            if kind == "nonnegative_integer" and (type(value) is not int or value < 0):
                return "INVALID_INPUT"
            if kind == "boolean" and type(value) is not bool:
                return "INVALID_INPUT"
            if kind in {"string", "date"} and (type(value) is not str or not value.strip()):
                return "INVALID_INPUT"
            if kind == "date":
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    return "INVALID_INPUT"
                try:
                    dt.date.fromisoformat(value)
                except ValueError:
                    return "INVALID_INPUT"
        return None

    def decide(self, data: dict, candidate: bool, variant: str) -> str:
        raise NotImplementedError

    def _write(self, env: Environment, key: str, data: dict, decision: str) -> None:
        writes = decision in self.effect_decisions
        if env.variant == "unexpected_write":
            writes = True
        if not writes or env.variant == "false_success":
            return
        target = data.get(self.target_field)
        if env.variant == "wrong_target":
            target = str(target) + "_WRONG"
        env.rows.append({
            "id": f"row_{len(env.rows) + 1}", "table": self.table,
            "target_id": target, "operation_key": key,
            "input_digest": digest(data), "decision": decision,
        })

    def invoke(self, env: Environment, key: str, business_input: dict) -> dict:
        if type(key) is not str or not key.strip():
            raise ValueError("operation_key must be a nonempty string")
        if type(business_input) is not dict:
            raise ValueError("business_input must be an object")
        original = copy.deepcopy(business_input)
        request_hash = digest(original)
        env.invocation_count += 1
        if key in env.receipts:
            previous_hash, previous_response = env.receipts[key]
            if previous_hash != request_hash:
                raise OperationConflict("Same operation key with different business input")
            if env.variant == "duplicate_effect":
                self._write(env, key, original, previous_response["decision"])
            return copy.deepcopy(previous_response)
        data = copy.deepcopy(original)
        if env.variant == "unknown_as_zero":
            for name, kind in self.fields.items():
                if kind == "nonnegative_integer" and data.get(name) is None:
                    data[name] = 0
        decision = self.validate(data)
        if decision is None:
            candidate = env.artifact == "candidate_v2" and env.variant != "stale_candidate"
            decision = self.decide(data, candidate, env.variant)
        status = decision if decision in {"NEEDS_INPUT", "INVALID_INPUT", "UNSUPPORTED"} else "DECIDED"
        response = {"status": status, "decision": decision, "receipt_id": None}
        if decision in self.effect_decisions:
            response["receipt_id"] = "receipt_" + hashlib.sha256(key.encode()).hexdigest()[:12]
        self._write(env, key, original, decision)
        env.receipts[key] = (request_hash, copy.deepcopy(response))
        return response


class ManufacturingAdapter(MockAdapter):
    table = "work_orders"
    target_field = "equipment_id"
    effect_decisions = frozenset({"DUE"})
    fields = {"equipment_id": "string", "equipment_group": "string", "mode": "string", "region": "string", "assessment_date": "date", "hours_since_inspection": "nonnegative_integer"}

    def decide(self, d: dict, candidate: bool, variant: str) -> str:
        if d["region"] != "KR" or d["equipment_group"] not in {"A", "B"} or d["mode"] not in {"normal", "special"}:
            return "UNSUPPORTED"
        active = candidate and (d["assessment_date"] >= "2026-12-01" or variant == "wrong_effective_scope")
        threshold = 80 if active else 100
        if variant != "exception_removed":
            if d["equipment_group"] == "B":
                threshold = 120
            elif d["mode"] == "special":
                threshold = 60
        due = d["hours_since_inspection"] > threshold if variant == "boundary" else d["hours_since_inspection"] >= threshold
        return "DUE" if due else "NOT_DUE"


class FinanceAdapter(MockAdapter):
    table = "ledger_entries"
    target_field = "customer_id"
    fields = {"customer_id": "string", "customer_type": "string", "product_id": "string", "region": "string", "assessment_date": "date", "monthly_recognized_spend_krw": "nonnegative_integer", "vip": "boolean"}

    def decide(self, d: dict, candidate: bool, variant: str) -> str:
        if d["region"] != "KR" or d["customer_type"] != "personal" or d["product_id"] != "P1":
            return "UNSUPPORTED"
        if d["vip"] and variant != "exception_removed":
            return "WAIVED"
        active = candidate and (d["assessment_date"] >= "2026-12-01" or variant == "wrong_effective_scope")
        threshold = 300000 if active else 500000
        waived = d["monthly_recognized_spend_krw"] > threshold if variant == "boundary" else d["monthly_recognized_spend_krw"] >= threshold
        return "WAIVED" if waived else "CHARGED"


class CustomerServiceAdapter(MockAdapter):
    table = "return_requests"
    target_field = "order_id"
    effect_decisions = frozenset({"ELIGIBLE"})
    fields = {"order_id": "string", "region": "string", "delivered_on": "date", "elapsed_days": "nonnegative_integer", "opened": "boolean", "custom_made": "boolean"}

    def decide(self, d: dict, candidate: bool, variant: str) -> str:
        if d["region"] != "KR":
            return "UNSUPPORTED"
        if (d["opened"] or d["custom_made"]) and variant != "exception_removed":
            return "INELIGIBLE"
        active = candidate and (d["delivered_on"] >= "2026-12-01" or variant == "wrong_effective_scope")
        limit = 30 if active else 14
        eligible = d["elapsed_days"] < limit if variant == "boundary" else d["elapsed_days"] <= limit
        return "ELIGIBLE" if eligible else "INELIGIBLE"


ADAPTERS = {
    "manufacturing": ManufacturingAdapter,
    "finance": FinanceAdapter,
    "customer_service": CustomerServiceAdapter,
}

