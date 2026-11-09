"""Explicit offline replay for this registered synthetic workbench only.

Saved data is never interpreted as code, URLs, file names, or adapter selectors.
A replay does not retry any external operation or change a review decision.
"""
import copy
import re

from .adapters import canonical, digest
from .app import _validate_configuration, execute_run


HASH = re.compile(r'[0-9a-f]{64}')


def _same_evidence(left, right):
    # Python considers True == 1 == 1.0. Exact JSON evidence must retain types.
    try:
        return canonical(left) == canonical(right)
    except (TypeError, ValueError, RecursionError):
        raise ValueError('Replay evidence is missing or inconsistent.') from None


def replay_report(report):
    """Compare exact deterministic evidence, excluding only run identity/time.

A matching replay says nothing about actual business accuracy or deployment.
The caller must separately verify the saved record's storage integrity.
"""
    if type(report) is not dict or report.get('synthetic_only') is not True:
        raise ValueError('Only registered synthetic reports can be replayed.')
    configuration = report.get('configuration')
    _validate_configuration(configuration)
    manifest = report.get('manifest')
    if (type(manifest) is not dict
            or not HASH.fullmatch(str(report.get('manifest_sha256', '')))
            or digest(manifest) != report['manifest_sha256']
            or not _same_evidence(manifest.get('configuration'), configuration)
            or type(report.get('scope')) is not dict
            or not _same_evidence(report['scope'], manifest.get('scope'))
            or type(report.get('cases')) is not list or not report['cases']
            or any(type(case) is not dict for case in report['cases'])
            or [case.get('id') for case in report['cases']] != report['scope'].get('selected_case_ids')):
        raise ValueError('Replay evidence is missing or inconsistent.')
    # execute_run accepts only registered synthetic versions/case IDs. Saved
    # source paths, rule text, output, or expectations never control execution.
    fresh = execute_run(copy.deepcopy(configuration))
    result = {'original_run_id': report.get('run_id'), 'replayed_run_id': fresh['run_id'],
              'synthetic_only': True, 'deployment_approval': False,
              'scope': fresh['scope'], 'counts': fresh['counts'],
              'readiness': fresh['readiness'], 'changed_sections': []}
    if not _same_evidence(fresh['manifest'], manifest):
        return {**result, 'status': 'INCOMPATIBLE',
                'reason': 'Source, policy, scenario, or FAQ evidence differs; review a new run.'}
    ignored = {'run_id', 'created_at', 'record'}
    changed = sorted(key for key in set(report) | set(fresh)
                     if key not in ignored and (key not in report or key not in fresh
                        or not _same_evidence(report[key], fresh[key])))
    return {**result, 'status': 'DIFFERENT' if changed else 'MATCH', 'changed_sections': changed,
            'reason': 'Recorded evidence differs.' if changed else
            'Deterministic evidence matches within the recorded synthetic scope.'}
