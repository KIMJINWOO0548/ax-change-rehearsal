"""Validation for independent, local synthetic notification observations."""
from collections import Counter
import re

from .adapters import INTENT_ROLES, canonical, digest

VERSION = 1
SIDES = ('baseline', 'candidate')
PHASES = ('initial', 'first', 'replay')
OBSERVATION_STAGES = dict(zip(('initial_observation', 'observation', 'replay_observation'), PHASES))
MAX_ROWS = 64
WORK_KEY = re.compile(r'[A-Za-z0-9_:-]{1,128}')
ROW_ID = re.compile(r'intent_[1-9][0-9]{0,7}')


class EffectManifestMismatch(ValueError):
    """Structurally readable effect evidence with incompatible provenance."""


def _valid_counts(value):
    return (type(value) is dict and set(value) == set(INTENT_ROLES)
            and all(type(v) is int and 0 <= v <= MAX_ROWS for v in value.values()))


def validate_expectations(payload, registered_ids):
    if (type(payload) is not dict or set(payload) != {'version', 'cases'}
            or type(payload['version']) is not int or payload['version'] != VERSION
            or type(payload['cases']) is not dict or set(payload['cases']) != set(registered_ids)
            or not 0 < len(payload['cases']) <= MAX_ROWS
            or any(type(value) is not dict or set(value) != set(SIDES)
                   or not all(_valid_counts(counts) for counts in value.values())
                   for value in payload['cases'].values())):
        raise ValueError('Invalid registered notification intent expectations')


def _validate_observation(obs):
    if type(obs) is not dict or set(obs) != {'state', 'rows', 'reason'}:
        raise ValueError('Invalid notification observation')
    state, rows, reason = obs['state'], obs['rows'], obs['reason']
    if state in ('UNCONFIRMED', 'NOT_REACHED'):
        if rows is None and reason == {'UNCONFIRMED': 'OBSERVATION_FAILED', 'NOT_REACHED': 'STAGE_NOT_REACHED'}[state]:
            return
        raise ValueError('Unconfirmed notification observation cannot contain rows')
    if state != 'OBSERVED' or reason is not None or type(rows) is not list or len(rows) > MAX_ROWS:
        raise ValueError('Invalid notification observation state or limit')
    ids = set()
    for row in rows:
        if (type(row) is not dict or set(row) != {'operation_key', 'id', 'role', 'kind'}
                or row['role'] not in INTENT_ROLES or row['kind'] != 'NOTIFICATION_INTENT'
                or type(row['operation_key']) is not str or not WORK_KEY.fullmatch(row['operation_key'])
                or type(row['id']) is not str or not ROW_ID.fullmatch(row['id']) or row['id'] in ids):
            raise ValueError('Invalid synthetic notification intent row')
        ids.add(row['id'])


def validate_intent_checkpoint(value):
    if type(value) is not dict or set(value) != {'stored_rows', 'notification_intents'} or type(value['stored_rows']) is not list:
        raise ValueError('Invalid notification checkpoint')
    _validate_observation(value['notification_intents'])
    if value['notification_intents']['state'] == 'NOT_REACHED':
        raise ValueError('Completed checkpoint cannot be unreached')


def observation(state, rows=None):
    result = {'state': state, 'rows': rows, 'reason': {'OBSERVED': None, 'UNCONFIRMED': 'OBSERVATION_FAILED',
                                                     'NOT_REACHED': 'STAGE_NOT_REACHED'}[state]}
    _validate_observation(result)
    return result


def build_effects(key, expected, observations):
    if type(key) is not str or not WORK_KEY.fullmatch(key) or not _valid_counts(expected) or set(observations) != set(PHASES):
        raise ValueError('Invalid synthetic notification context')
    for item in observations.values():
        _validate_observation(item)
    initial, first, replay = (observations[phase]['rows'] for phase in PHASES)
    findings = set()
    if initial is not None and any(row['operation_key'] == key for row in initial):
        findings.add('UNEXPECTED_EFFECT')
    changes = {'first': None, 'replay': None}
    for label, rows in (('first', first), ('replay', replay)):
        if initial is None or rows is None:
            findings.add('UNCONFIRMED')
            continue
        if rows[:len(initial)] != initial:
            findings.add('PREEXISTING_CHANGED')
        previous_ids = {row['id'] for row in initial}
        added = [row for row in rows if row['id'] not in previous_ids]
        if any(row['operation_key'] != key for row in added):
            findings.add('UNEXPECTED_EFFECT')
        counts = Counter(row['role'] for row in added if row['operation_key'] == key)
        changes[label] = {role: counts[role] for role in INTENT_ROLES}
        for role in INTENT_ROLES:
            if counts[role] < expected[role]:
                findings.add('MISSING')
            if counts[role] > expected[role]:
                findings.add('DUPLICATE' if expected[role] > 0 else
                             ('WRONG_ROLE' if any(expected.values()) else 'UNEXPECTED_EFFECT'))
    if first is not None and replay is not None and first != replay:
        findings.add('REPLAY_CHANGED')
    return {'operation_key': key, 'expectations': expected, 'observations': observations,
            'changes': changes, 'findings': sorted(findings)}


def validate_effect_report(report):
    manifest, api = report.get('manifest'), report.get('api')
    cases = report.get('cases')
    api_cases = api.get('cases') if type(api) is dict else None
    api_manifest = api.get('manifest') if type(api) is dict else None
    def has_effect(case):
        return type(case) is dict and any(type(case.get(side)) is dict and 'effects' in case[side] for side in SIDES)
    if type(manifest) is not dict or 'effect_evidence_version' not in manifest:
        if ((type(api_manifest) is dict and 'effect_evidence_version' in api_manifest)
                or any(has_effect(case) for records in (cases, api_cases) if type(records) is list for case in records)):
            raise ValueError('Missing report notification evidence version')
        return
    try:
        if (type(manifest['effect_evidence_version']) is not int or manifest['effect_evidence_version'] != VERSION
                or type(api_manifest['effect_evidence_version']) is not int or api_manifest['effect_evidence_version'] != VERSION
                or report['configuration']['policy_version'] != 'returns-20270115'
                or report['manifest_sha256'] != digest(manifest)):
            raise ValueError('Invalid report notification evidence version')
        expected = api_manifest['effect_expectations']
        scope = report['scope']
        validate_expectations(expected, [*scope['selected_case_ids'], *scope['omitted_case_ids']])
        if (manifest['effect_expectations_sha256'] != digest(expected)
                or api_manifest['effect_expectations_sha256'] != digest(expected)
                or [case['id'] for case in cases] != scope['selected_case_ids']
                or [case['id'] for case in api_cases] != scope['selected_case_ids']):
            raise ValueError('Notification evidence does not match report scope')
        for case, api_case in zip(cases, api_cases):
            for side in SIDES:
                detail, duplicate = case[side], api_case[side]
                key = api_manifest['sha256'][:16] + ':' + case['id'] + ':' + side + ':decide'
                actual = detail['effects']
                derived = build_effects(key, expected['cases'][case['id']][side], actual['observations'])
                if (detail['operation_key'] != key or duplicate['operation_key'] != key
                        or canonical(actual) != canonical(derived) or canonical(duplicate['effects']) != canonical(derived)):
                    raise ValueError('Notification evidence differs from recorded observations')
                findings = set(derived['findings'])
                if (findings - {'UNCONFIRMED'} and detail['assertion_status'] != 'FAIL') or (
                        findings and detail['assertion_status'] == 'PASS'):
                    raise ValueError('Notification evidence conflicts with assertion status')
        if (api_manifest['policy_version'] != report['configuration']['policy_version']
                or canonical(manifest['api_manifest']) != canonical(api_manifest)
                or api_manifest['sha256'] != digest({k: v for k, v in api_manifest.items() if k != 'sha256'})):
            raise EffectManifestMismatch('Notification evidence manifest is incompatible')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Invalid report notification evidence') from error


def verify_effect_stages(report, stages):
    manifest = report.get('manifest')
    if type(manifest) is not dict or 'effect_evidence_version' not in manifest:
        return
    observed = {}
    for stage in stages:
        phase = OBSERVATION_STAGES.get(stage['stage'])
        if phase is None:
            continue
        if stage['state'] == 'COMPLETED':
            value = stage['evidence']['value']
            validate_intent_checkpoint(value)
            item, stored_rows = value['notification_intents'], value['stored_rows']
        else:
            item, stored_rows = observation('UNCONFIRMED'), None
        observed[(stage['operation_key'], phase)] = item, stored_rows
    for case in report['cases']:
        for side in SIDES:
            effect = case[side]['effects']
            for phase, item in effect['observations'].items():
                checkpoint, stored_rows = observed.pop((effect['operation_key'], phase), (observation('NOT_REACHED'), None))
                expected_rows = case[side][{'initial': 'initial_state', 'first': 'first_observed_state', 'replay': 'observed_state'}[phase]]
                if item != checkpoint or (stored_rows is not None and canonical(stored_rows) != canonical(expected_rows)):
                    raise ValueError('Notification evidence does not match saved checkpoints')
    if observed:
        raise ValueError('Notification checkpoint is outside the saved report')
