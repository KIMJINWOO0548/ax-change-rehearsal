"""Closed, reviewed synthetic policy registry. No external imports or mutable registration.

Identifiers select fixed local fixtures, never paths from saved/client input.
This is a small authored scenario registry, not policy extraction or company validation.
"""
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
import hashlib
from .adapters import CustomerServiceAdapter

ROOT = Path(__file__).resolve().parents[1]

@dataclass(frozen=True)
class PolicyVersion:
    identifier: str
    effective_date: str
    new_window_days: int
    pack_path: str
    faq_root: str
    files: tuple
    old_window_days: int = 14

    def fingerprints(self):
        actual = {name: hashlib.sha256((ROOT / name).read_text('utf-8').replace('\r\n','\n').replace('\r','\n').encode('utf-8')).hexdigest() for name, _ in self.files}
        if actual != dict(self.files):
            raise ValueError('Registered synthetic policy artifacts changed; review a new version.')
        return actual

    def load_pack(self):
        from .validation import load_json
        self.fingerprints()
        return load_json(ROOT / self.pack_path)

    def verify_pack(self, pack):
        from .adapters import canonical
        registered = self.load_pack()
        selected = pack.get('cases', [])
        by_id = {case['id']: case for case in registered['cases']}
        if (not selected or any(case.get('id') not in by_id or canonical(case) != canonical(by_id[case['id']]) for case in selected)
                or canonical({k:v for k,v in pack.items() if k != 'cases'}) != canonical({k:v for k,v in registered.items() if k != 'cases'})):
            raise ValueError('Pack does not match selected registered policy')

    def policy_hashes(self):
        return {side: sha for name,sha in self.files for side in ('before','after') if name.endswith('policy_'+side+'.md')}

    def adapter(self):
        return RegisteredReturnAdapter(self)

class RegisteredReturnAdapter(CustomerServiceAdapter):
    def __init__(self, policy):
        self.policy = policy

    def decide(self, d, candidate, variant):
        if d['region'] != 'KR': return 'UNSUPPORTED'
        if (d['opened'] or d['custom_made']) and variant != 'exception_removed': return 'INELIGIBLE'
        active = candidate and (d['delivered_on'] >= self.policy.effective_date or variant == 'wrong_effective_scope')
        limit = self.policy.new_window_days if active else self.policy.old_window_days
        eligible = d['elapsed_days'] < limit if variant == 'boundary' else d['elapsed_days'] <= limit
        return 'ELIGIBLE' if eligible else 'INELIGIBLE'

VERSIONS = MappingProxyType({
    'returns-20261201': PolicyVersion('returns-20261201', '2026-12-01', 30, 'fixtures/customer_service/pack.json', 'examples/customer_service', (('fixtures/customer_service/pack.json', '29d229d9fa09867b18e048e76dba97500fb57b8c70ff1ae1a226bb1565b2214e'), ('fixtures/customer_service/policy_before.md', '7046cbf8d42d0ad363b5584f21062a4620aaddd5230141fb6ce91b5693ae57ba'), ('fixtures/customer_service/policy_after.md', '71f79958873021393a7c8ea03c56a3d313aaaa207eb0ac370e8d00405ea846cd'), ('examples/customer_service/faq_stale.json', '1d6f081ac6274b7afc6c017bd27f23f253232399992db234935cb3afd88565ef'), ('examples/customer_service/faq_corrected.json', '01ae4adb43bed6a15537c08089167e694e89224bd147ba12d17f207b62d7f000'))),
    'returns-20270115': PolicyVersion('returns-20270115', '2027-01-15', 21, 'fixtures/customer_service/versions/returns-20270115/pack.json', 'fixtures/customer_service/versions/returns-20270115', (('fixtures/customer_service/versions/returns-20270115/pack.json', '8843973d688dfa3a00a6ddab68e63e6953bc58caa71172435325121c3c6675e0'), ('fixtures/customer_service/versions/returns-20270115/policy_before.md', '38d81a54ec27c282ac3584908b068cc2f6f334c48a3e679448f394adbaad17a0'), ('fixtures/customer_service/versions/returns-20270115/policy_after.md', '5c3196a3ef7fa166142f1615d0f67ea108aec0c91cdee296581703df4cf25791'), ('fixtures/customer_service/versions/returns-20270115/faq_stale.json', '0ff90e765a283c9b4674cbc14acb4add950ad741e5755e2171a17585af990a06'), ('fixtures/customer_service/versions/returns-20270115/faq_corrected.json', '601435f5d28f111bd327f328545d6e69a22ae07ca628e25c79f04b4e9bf50935'))),
})

def get_policy(identifier):
    if type(identifier) is not str or identifier not in VERSIONS:
        raise ValueError('Unknown registered synthetic policy version')
    return VERSIONS[identifier]
