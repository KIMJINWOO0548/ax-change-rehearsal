"""Boundary tests use literal business expectations, never fixture oracles."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rehearsal.adapters import ADAPTERS, CustomerServiceAdapter
from rehearsal.engine import load_packs
from rehearsal.validation import load_json


class AdapterInputTests(unittest.TestCase):
    def setUp(self):
        self.data = {'order_id': 'synthetic_test', 'region': 'KR', 'delivered_on': '2026-12-01',
                     'elapsed_days': 20, 'opened': False, 'custom_made': False}

    def invoke(self, data, artifact='candidate_v2'):
        adapter = CustomerServiceAdapter()
        env = adapter.create_environment(artifact)
        return adapter.invoke(env, 'key', data), env.rows

    def test_missing_and_null_each_required_field_are_unresolved(self):
        for name in self.data:
            for delete in (False, True):
                data = copy.deepcopy(self.data)
                if delete:
                    del data[name]
                else:
                    data[name] = None
                with self.subTest(field=name, delete=delete):
                    response, rows = self.invoke(data)
                    self.assertEqual(response['status'], 'NEEDS_INPUT')
                    self.assertEqual(rows, [])

    def test_invalid_dates_are_rejected_not_lexically_compared(self):
        for value in ('2026-02-29', '2026-02-30', '2026-13-01', '2026-12-32',
                      '2026-1-01', '20261201', '2026-12-01T00:00:00Z', '', 20261201):
            with self.subTest(value=value):
                response, rows = self.invoke({**self.data, 'delivered_on': value})
                self.assertEqual(response['status'], 'INVALID_INPUT')
                self.assertEqual(rows, [])

    def test_valid_leap_day_is_accepted_as_old_policy(self):
        response, rows = self.invoke({**self.data, 'delivered_on': '2024-02-29'})
        self.assertEqual(response['decision'], 'INELIGIBLE')
        self.assertEqual(rows, [])

    def test_strict_integer_and_boolean_fields(self):
        for field, value in [('elapsed_days', -1), ('elapsed_days', 1.2),
                             ('elapsed_days', True), ('elapsed_days', '20'),
                             ('opened', 'false'), ('opened', 0), ('custom_made', 1)]:
            with self.subTest(field=field, value=value):
                response, rows = self.invoke({**self.data, field: value})
                self.assertEqual(response['status'], 'INVALID_INPUT')
                self.assertEqual(rows, [])

    def test_effective_date_and_period_boundaries(self):
        checks = [('2026-11-30', 14, 'ELIGIBLE'), ('2026-11-30', 15, 'INELIGIBLE'),
                  ('2026-12-01', 15, 'ELIGIBLE'), ('2026-12-01', 30, 'ELIGIBLE'),
                  ('2026-12-01', 31, 'INELIGIBLE')]
        for day, elapsed, wanted in checks:
            with self.subTest(day=day, elapsed=elapsed):
                response, rows = self.invoke({**self.data, 'delivered_on': day, 'elapsed_days': elapsed})
                self.assertEqual(response['decision'], wanted)
                self.assertEqual(len(rows), 1 if wanted == 'ELIGIBLE' else 0)

    def test_exceptions_and_out_of_scope_have_no_effect(self):
        for overrides, decision in [({'opened': True}, 'INELIGIBLE'),
                                     ({'custom_made': True}, 'INELIGIBLE'),
                                     ({'region': 'US'}, 'UNSUPPORTED')]:
            response, rows = self.invoke({**self.data, **overrides})
            self.assertEqual(response['decision'], decision)
            self.assertEqual(rows, [])

    def test_invalid_operation_keys_rejected_before_effects(self):
        for key in ('', ' ', None, 42):
            adapter = CustomerServiceAdapter()
            env = adapter.create_environment('candidate_v2')
            with self.subTest(key=key), self.assertRaises(ValueError):
                adapter.invoke(env, key, self.data)
            self.assertEqual(env.rows, [])
            self.assertEqual(env.invocation_count, 0)

    def test_non_object_business_input_rejected_before_effects(self):
        for data in ([], None, 'input'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.invoke(data)

    def test_cross_case_and_version_state_isolation(self):
        adapter = CustomerServiceAdapter()
        before = adapter.create_environment('baseline_v1')
        after = adapter.create_environment('candidate_v2')
        other = adapter.create_environment('candidate_v2')
        adapter.invoke(after, 'same-key', self.data)
        self.assertEqual(before.rows, [])
        self.assertEqual(other.rows, [])
        self.assertEqual(len(after.rows), 1)

    def test_all_adapters_reject_bool_in_integer_field(self):
        for domain, cls in ADAPTERS.items():
            case = load_packs([domain])[0]['cases'][0]
            for field, kind in cls.fields.items():
                if kind != 'nonnegative_integer':
                    continue
                adapter = cls()
                env = adapter.create_environment('candidate_v2')
                response = adapter.invoke(env, 'bool-check', {**case['business_input'], field: True})
                self.assertEqual(response['status'], 'INVALID_INPUT')
                self.assertEqual(env.rows, [])


class JsonValidationTests(unittest.TestCase):
    def test_duplicate_json_keys_are_rejected_at_any_depth(self):
        for text in ('{"a":1,"a":2}', '{"a":{"b":1,"b":2}}'):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'pack.json'
                path.write_text(text)
                with self.assertRaises(ValueError):
                    load_json(path)

    def test_nonfinite_json_numbers_rejected(self):
        for value in ('NaN', 'Infinity', '-Infinity'):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'pack.json'
                path.write_text('{"value":' + value + '}')
                with self.assertRaises(ValueError):
                    load_json(path)
