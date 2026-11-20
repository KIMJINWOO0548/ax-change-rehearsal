"""Domain-neutral execution and observation comparison.

The evaluator sees the oracles; adapters only see business_input.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from contextvars import ContextVar
from pathlib import Path

from . import assert_sources_unchanged
from .adapters import ADAPTERS, VARIANTS, digest, observe, observe_intents
from .effects import PHASES, VERSION as EFFECT_VERSION, build_effects, observation
from .validation import load_json, validate_pack, validate_selection
from .storage import StorageError


ROOT = Path(__file__).resolve().parents[1]
stage_recorder = ContextVar('stage_recorder', default=None)


def _stage_call(key, stage, operation):
    record = stage_recorder.get()
    if record is None:
        return operation()
    record(key, stage, 'STARTED', {})
    try:
        value = operation()
    except BaseException as exc:
        record(key, stage, 'FAILED', {'error_type': type(exc).__name__})
        raise
    record(key, stage, 'COMPLETED', {'value': copy.deepcopy(value)})
    return value


def load_packs(domains: list[str] | None = None) -> list[dict]:
    requested = sorted(ADAPTERS) if domains is None else domains
    validate_selection(requested, ADAPTERS, "domains")
    packs = [load_json(ROOT / "fixtures" / domain / "pack.json") for domain in requested]
    for domain, pack in zip(requested, packs):
        validate_pack(pack, ROOT)
        if pack["pack_id"] != domain:
            raise ValueError("Pack domain does not match its directory")
    return packs


def manifest_for(pack: dict, variant: str, adapter) -> dict:
    assert_sources_unchanged()
    source_files = [ROOT / "rehearsal" / name for name in ("engine.py", "adapters.py", "validation.py", "__init__.py")]
    source_files += [ROOT / "fixtures" / pack["pack_id"] / rel for rel in pack["source_documents"].values()]
    sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    sources.update(adapter.policy_fingerprint())
    content = {
        "pack_digest": digest(pack), "domain": pack["pack_id"], "variant": variant,
        "baseline_artifact": pack["baseline_artifact"], "candidate_artifact": pack["candidate_artifact"],
        "sources": sources,
        "execution": "deterministic_in_memory_mock", "seed": 0,
        "model": None, "prompt": None, "parser": None, "index": None,
    }
    return {**content, "sha256": digest(content)}


def check_observation(adapter, expected: dict, response: dict | None, before: list, after: list, key: str, data: dict) -> list[str]:
    errors = []
    if response is not None:
        for field in ("status", "decision"):
            if response.get(field) != expected[field]:
                errors.append(f"{field}: expected {expected[field]}, observed {response.get(field)}")
    if len(after) - len(before) != expected["state_delta"]["count"]:
        errors.append(f"state_count: expected {expected['state_delta']['count']}, observed {len(after) - len(before)}")
    # First implementation owns isolated append-only state. Reject silent deletion/modification.
    if after[:len(before)] != before:
        errors.append("preexisting_state_changed")
    for row in after[len(before):]:
        for field, wanted in (
            ("table", expected["state_delta"]["table"]),
            ("target_id", data.get(adapter.target_field)),
            ("operation_key", key), ("input_digest", digest(data)),
            ("decision", expected["decision"]),
        ):
            if row.get(field) != wanted:
                errors.append(f"state_{field}: expected {wanted}, observed {row.get(field)}")
    return errors


def _snapshot(env) -> list[dict]:
    snapshot = observe(env)
    if type(snapshot) is not list or any(type(row) is not dict for row in snapshot):
        raise ValueError("Observation must be a list of row objects")
    # Preserve evidence even if a faulty observer returns its live storage object.
    return copy.deepcopy(snapshot)


def run_side(adapter, artifact: str, variant: str, case: dict, expected: dict, key: str, *, effect_counts=None) -> dict:
    env = adapter.create_environment(artifact, variant)
    initial, response, replay_response, first_after, after = None, None, None, None, None
    invocation_error, observation_error = None, None
    errors = []
    effect_observations = {phase: observation('NOT_REACHED') for phase in PHASES} if effect_counts is not None else None

    def observe_stage(stage, phase):
        if effect_observations is None:
            return _stage_call(key, stage, lambda: _snapshot(env))

        def capture():
            effect_observations[phase] = observation('UNCONFIRMED')
            stored_rows = _snapshot(env)
            try:
                effect_observations[phase] = observation('OBSERVED', observe_intents(env))
            except Exception as exc:
                if isinstance(exc, StorageError):
                    raise
            return {'stored_rows': stored_rows, 'notification_intents': effect_observations[phase]}

        return _stage_call(key, stage, capture)['stored_rows']

    try:
        initial = observe_stage('initial_observation', 'initial')
    except Exception as exc:
        if isinstance(exc, StorageError): raise
        observation_error = {"type": type(exc).__name__, "message": str(exc), "stage": "initial"}
    if observation_error is None:
        try:
            response = _stage_call(key, 'invocation', lambda: adapter.invoke(env, key, copy.deepcopy(case["business_input"])))
            if not isinstance(response, dict):
                errors.append("invalid_response: expected an object")
                response = None
            else:
                response = copy.deepcopy(response)
        except Exception as exc:
            if isinstance(exc, StorageError): raise
            invocation_error = {"type": type(exc).__name__, "message": str(exc), "stage": "invoke"}
        # Observe before replay: a later call must not hide a broken first call.
        try:
            first_after = observe_stage('observation', 'first')
            after = first_after
        except Exception as exc:
            if isinstance(exc, StorageError): raise
            observation_error = {"type": type(exc).__name__, "message": str(exc), "stage": "after"}
        if first_after is not None:
            errors.extend(check_observation(adapter, expected, response, initial, first_after, key, case["business_input"]))
        if response is not None and invocation_error is None and observation_error is None:
            try:
                replay_response = _stage_call(key, 'replay_invocation', lambda: adapter.invoke(env, key, copy.deepcopy(case["business_input"])))
                if response != replay_response:
                    errors.append("idempotent_response_changed")
                replay_response = copy.deepcopy(replay_response)
            except Exception as exc:
                if isinstance(exc, StorageError): raise
                invocation_error = {"type": type(exc).__name__, "message": str(exc), "stage": "replay"}
            # Replay failure may also occur after a write. Inspect it independently.
            after = None
            try:
                after = observe_stage('replay_observation', 'replay')
                if after != first_after:
                    errors.append("idempotent_state_changed")
                errors.extend(check_observation(adapter, expected, response, initial, after, key, case["business_input"]))
            except Exception as exc:
                if isinstance(exc, StorageError): raise
                observation_error = {"type": type(exc).__name__, "message": str(exc), "stage": "replay_after"}
    if response is not None:
        for field in ("status", "decision"):
            if response.get(field) != expected[field]:
                errors.append(f"{field}: expected {expected[field]}, observed {response.get(field)}")
    incomplete = invocation_error is not None or observation_error is not None
    effects = None
    if effect_observations is not None:
        effects = build_effects(key, effect_counts, effect_observations)
        incomplete |= 'UNCONFIRMED' in effects['findings']
        errors.extend('notification_intents:' + finding for finding in effects['findings'] if finding != 'UNCONFIRMED')
    return {
        "artifact": artifact, "variant": variant, "operation_key": key,
        "expected": expected, "response": response, "replay_response": replay_response,
        "initial_state": initial, "first_observed_state": first_after, "observed_state": after,
        "invocation_error": invocation_error, "observation_error": observation_error,
        "effect_status": "UNKNOWN_EFFECT" if observation_error else "OBSERVED",
        "assertion_errors": sorted(set(errors)),
        "assertion_status": "FAIL" if errors else ("INCOMPLETE" if incomplete else "PASS"),
        **({'effects': effects} if effects is not None else {}),
    }


def run_pack(pack: dict, variant: str = "normal", *, policy_version=None) -> dict:
    if variant not in VARIANTS:
        raise ValueError("Unsupported variant")
    if policy_version is not None: pack = copy.deepcopy(pack)
    validate_pack(pack, ROOT, policy_version=policy_version)
    policy = None
    if policy_version is not None:
        from .policies import get_policy
        policy = get_policy(policy_version)
    adapter = policy.adapter() if policy is not None else ADAPTERS[pack["pack_id"]]()
    manifest = manifest_for(pack, variant, adapter)
    effect_expectations = None
    if policy is not None:
        manifest.update(policy_version=policy_version, policy_artifacts=policy.fingerprints(),
                        registry_source_sha256=hashlib.sha256((ROOT / 'rehearsal/policies.py').read_bytes()).hexdigest())
        if policy.effect_file is not None:
            registered_cases = policy.load_pack()['cases']
            effect_expectations = policy.effect_expectations([case['id'] for case in registered_cases])
            manifest.update(effect_evidence_version=EFFECT_VERSION, effect_expectations=effect_expectations,
                            effect_expectations_sha256=digest(effect_expectations))
            for name in ('rehearsal/effects.py', 'contracts/mock-effects-v1.schema.json'):
                manifest['sources'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        manifest['sha256'] = digest({k:v for k,v in manifest.items() if k != 'sha256'})
    cases = []
    for case in pack["cases"]:
        prefix = manifest["sha256"][:16] + ":" + case["id"]
        effect = effect_expectations['cases'][case['id']] if effect_expectations is not None else None
        before = run_side(adapter, pack["baseline_artifact"], "normal", case, case["expected_before"], prefix + ":baseline:decide",
                          **({'effect_counts': effect['baseline']} if effect is not None else {}))
        after = run_side(adapter, pack["candidate_artifact"], variant, case, case["expected_after"], prefix + ":candidate:decide",
                         **({'effect_counts': effect['candidate']} if effect is not None else {}))
        sides = (before, after)
        if any(side["assertion_status"] == "FAIL" for side in sides):
            verdict = "FAIL"
        elif any(side["assertion_status"] == "INCOMPLETE" for side in sides) or case["intended_behavior"] == "INDETERMINATE":
            verdict = "INCONCLUSIVE"
        else:
            verdict = "PASS_WITHIN_SCOPE"
        assertions = "FAIL" if any(s["assertion_status"] == "FAIL" for s in sides) else ("INCOMPLETE" if any(s["assertion_status"] == "INCOMPLETE" for s in sides) else "PASS")
        cases.append({"id": case["id"], "label": case["label"], "input": case["business_input"], "intended_behavior": case["intended_behavior"], "baseline": before, "candidate": after, "business_verdict": verdict, "assertion_status": assertions})
    assert_sources_unchanged()
    adapter.policy_fingerprint()
    if policy is not None: policy.fingerprints()
    counts = Counter(c["business_verdict"] for c in cases)
    readiness = "BLOCKED" if counts["FAIL"] else ("REVIEW_REQUIRED" if counts["INCONCLUSIVE"] else "PASS_WITHIN_REGISTERED_SCOPE")
    return {"domain": pack["pack_id"], "title": pack["title"], "manifest": manifest, "variant": variant, "cases": cases, "readiness": readiness, "counts": dict(counts)}


def run_suite(variants: list[str], domains: list[str] | None = None) -> dict:
    validate_selection(variants, VARIANTS, "variants")
    packs = load_packs(domains)
    results = [run_pack(pack, variant) for variant in variants for pack in packs]
    summaries = []
    for variant in variants:
        subset = [c for r in results if r["variant"] == variant for c in r["cases"]]
        counts = Counter(c["business_verdict"] for c in subset)
        assertions = Counter(c["assertion_status"] for c in subset)
        summaries.append({"variant": variant, "cases": len(subset), "business_counts": dict(counts), "assertion_counts": dict(assertions)})
    return {"prototype_version": "0.2.0", "synthetic_only": True, "llm_executed": False, "real_enterprise_system_connected": False, "variants": variants, "summaries": summaries, "runs": results}

