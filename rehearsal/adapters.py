"""Trusted mock adapters. They receive business input, never fixture oracles.

Environments isolate in-memory state; this is not an OS/process security sandbox.
These business mock adapters perform no network I/O or language-model calls.
The separate opt-in network_probe diagnostic only contacts disposable loopback services.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_FILES = MappingProxyType({
    "manufacturing": ("fixtures/manufacturing/mock_policy.json",
                      "144e7d3d76d83839dbd469e04e125e9ce1d0481b9eb21be60c5fa9971e00e3a0"),
    "finance": ("fixtures/finance/mock_policy.json",
                "e96601703e38e8e802d203eb3b2768347e3d4769197ddb44c31d577ad43c6cbc"),
    "returns-20261201": ("fixtures/customer_service/mock_policy.json",
                         "05def996ef3f07b801aaae805abc2f2d926414c0880b04b3771cdd4d4c5a30b9"),
    "returns-20270115": ("fixtures/customer_service/versions/returns-20270115/mock_policy.json",
                         "355ae2b35365de3bed30fefa39265f0010b953249108270d20d71db2a42eb595"),
})
INTENT_ROLES = ('REVIEWER', 'CUSTOMER')
MOCK_INTENT_FILE = 'fixtures/customer_service/versions/returns-20270115/mock_effects_v1.json'
MOCK_INTENT_SHA = '8234f0fec7f72a933c1eebdbe9cbd9e72dcfc1a70729651689db7202dbe90cbf'

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
    notification_intents: list[dict] = field(default_factory=list)


def observe(environment: Environment) -> list[dict]:
    """Read actual mock storage, independently from the adapter response."""
    if environment.variant == "observer_timeout" and environment.invocation_count:
        raise TimeoutError("Injected observation timeout; effects are unknown")
    return copy.deepcopy(environment.rows)


def observe_intents(environment: Environment) -> list[dict]:
    return copy.deepcopy(environment.notification_intents)


class MockAdapter:
    policy_profile: str
    table: str
    target_field: str
    fields: dict[str, str]
    effect_decisions: frozenset[str] = frozenset()

    def __init__(self, policy_profile=None):
        self.policy_path, self.policy_sha256 = POLICY_FILES[policy_profile or self.policy_profile]
        self.policy = self._read_policy()

    def _read_policy(self):
        payload = (ROOT / self.policy_path).read_text('utf-8')
        if hashlib.sha256(payload.encode('utf-8')).hexdigest() != self.policy_sha256:
            raise ValueError('Registered mock policy changed; review a new version.')
        policy = json.loads(payload)
        if (policy['schema_version'] != 1 or dt.date.fromisoformat(policy['effective_date']).isoformat() != policy['effective_date']
                or any(type(policy[key]) is not int or policy[key] < 0
                       for key in ('baseline_threshold', 'candidate_threshold'))):
            raise ValueError('Invalid registered mock policy.')
        return policy

    def policy_fingerprint(self):
        self._read_policy()
        return {self.policy_path: self.policy_sha256}

    def threshold(self, effective_input, candidate, variant):
        active = candidate and (effective_input >= self.policy['effective_date'] or variant == 'wrong_effective_scope')
        return self.policy['candidate_threshold' if active else 'baseline_threshold']

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
    policy_profile = "manufacturing"
    table = "work_orders"
    target_field = "equipment_id"
    effect_decisions = frozenset({"DUE"})
    fields = {"equipment_id": "string", "equipment_group": "string", "mode": "string", "region": "string", "assessment_date": "date", "hours_since_inspection": "nonnegative_integer"}

    def decide(self, d: dict, candidate: bool, variant: str) -> str:
        policy = self.policy
        if d["region"] != policy["region"] or d["equipment_group"] not in policy["allowed_groups"] or d["mode"] not in policy["allowed_modes"]:
            return "UNSUPPORTED"
        threshold = self.threshold(d["assessment_date"], candidate, variant)
        if variant != "exception_removed":
            threshold = policy["group_thresholds"].get(d["equipment_group"], policy["mode_thresholds"].get(d["mode"], threshold))
        due = d["hours_since_inspection"] > threshold if variant == "boundary" else d["hours_since_inspection"] >= threshold
        return "DUE" if due else "NOT_DUE"


class FinanceAdapter(MockAdapter):
    policy_profile = "finance"
    table = "ledger_entries"
    target_field = "customer_id"
    fields = {"customer_id": "string", "customer_type": "string", "product_id": "string", "region": "string", "assessment_date": "date", "monthly_recognized_spend_krw": "nonnegative_integer", "vip": "boolean"}

    def decide(self, d: dict, candidate: bool, variant: str) -> str:
        policy = self.policy
        if any(d[key] != policy[key] for key in ("region", "customer_type", "product_id")):
            return "UNSUPPORTED"
        if d[policy["waive_if_true"]] and variant != "exception_removed":
            return "WAIVED"
        threshold = self.threshold(d["assessment_date"], candidate, variant)
        waived = d["monthly_recognized_spend_krw"] > threshold if variant == "boundary" else d["monthly_recognized_spend_krw"] >= threshold
        return "WAIVED" if waived else "CHARGED"


class CustomerServiceAdapter(MockAdapter):
    policy_profile = "returns-20261201"
    table = "return_requests"
    target_field = "order_id"
    effect_decisions = frozenset({"ELIGIBLE"})
    fields = {"order_id": "string", "region": "string", "delivered_on": "date", "elapsed_days": "nonnegative_integer", "opened": "boolean", "custom_made": "boolean"}

    def __init__(self, policy_profile=None):
        super().__init__(policy_profile)
        self.notification_role = self._intent_role()

    def _intent_role(self):
        if self.policy_path != POLICY_FILES['returns-20270115'][0]:
            return None
        text = (ROOT / MOCK_INTENT_FILE).read_text('utf-8')
        if hashlib.sha256(text.encode('utf-8')).hexdigest() != MOCK_INTENT_SHA:
            raise ValueError('Registered mock notification policy changed.')
        data = json.loads(text)
        if (type(data) is not dict or set(data) != {'version', 'notification_role'} or type(data['version']) is not int
                or data['version'] != 1 or data['notification_role'] not in INTENT_ROLES):
            raise ValueError('Invalid mock notification policy.')
        return data['notification_role']

    def policy_fingerprint(self):
        sources = super().policy_fingerprint()
        if self._intent_role() is not None:
            sources[MOCK_INTENT_FILE] = MOCK_INTENT_SHA
        return sources

    def _write(self, env: Environment, key: str, data: dict, decision: str) -> None:
        before = len(env.rows)
        super()._write(env, key, data, decision)
        if self.notification_role is not None and len(env.rows) > before:
            env.notification_intents.append({'id': f'intent_{len(env.notification_intents) + 1}',
                                             'operation_key': key, 'role': self.notification_role,
                                             'kind': 'NOTIFICATION_INTENT'})

    def decide(self, d: dict, candidate: bool, variant: str) -> str:
        if d["region"] != self.policy["region"]:
            return "UNSUPPORTED"
        if any(d[key] for key in self.policy["exclude_if_true"]) and variant != "exception_removed":
            return "INELIGIBLE"
        limit = self.threshold(d["delivered_on"], candidate, variant)
        eligible = d["elapsed_days"] < limit if variant == "boundary" else d["elapsed_days"] <= limit
        return "ELIGIBLE" if eligible else "INELIGIBLE"


ADAPTERS = {
    "manufacturing": ManufacturingAdapter,
    "finance": FinanceAdapter,
    "customer_service": CustomerServiceAdapter,
}

