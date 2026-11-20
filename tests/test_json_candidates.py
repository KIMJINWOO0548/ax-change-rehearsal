import unittest
from rehearsal import json_sources

class JsonCandidateTests(unittest.TestCase):
    def test_typed_changes_become_unreviewed_candidates(self):
        factory=getattr(json_sources,'build_json_candidates',None)
        self.assertTrue(callable(factory),'JSON changes need an explicit review candidate API')
        value=factory(b'{"limit":14,"keep":true}',b'{"limit":30,"keep":true}')
        self.assertEqual(len(value['candidates']),1)
        row=value['candidates'][0]
        self.assertEqual(row['pointer'],'/limit')
        self.assertEqual(row['before']['value'],'14')
        self.assertEqual(row['after']['value'],'30')
        self.assertEqual(row['review_status'],'UNREVIEWED')
        self.assertIsNone(row['executable_rule'])
        self.assertFalse(value['deployment_approval'])


    def test_missing_null_types_and_escaped_pointers(self):
        value=json_sources.build_json_candidates(b'{"a/b":null,"~":1,"same":[]}',b'{"~":"1","same":[],"new":null}')
        rows={x['pointer']:x for x in value['candidates']}
        self.assertEqual(set(rows),{'/a~1b','/~0','/new'})
        self.assertEqual(rows['/a~1b']['change'],'delete')
        self.assertIsNone(rows['/a~1b']['after'])
        self.assertEqual(rows['/new']['after']['kind'],'null')
        self.assertEqual(rows['/~0']['before']['kind'],'number')
        self.assertEqual(rows['/~0']['after']['kind'],'string')

    def test_binding_changes_with_other_document_values_not_formatting(self):
        make=json_sources.build_json_candidates
        a=make(b'{"x":1,"z":0}',b'{"x":2,"z":0}')
        b=make(b'{ "z":0, "x":1 }',b'{"z":0,"x":2}')
        self.assertEqual(a,b)
        c=make(b'{"x":1,"z":9}',b'{"x":2,"z":9}')
        self.assertNotEqual(a['candidates'][0]['candidate_id'],c['candidates'][0]['candidate_id'])
        self.assertEqual(make(b'{"x":1}',b'{"x":1}')['candidates'],[])

    def test_array_positions_and_numeric_spelling_are_not_semantic(self):
        rows=json_sources.build_json_candidates(b'[1,2]',b'[0,1,2]')['candidates']
        self.assertEqual([r['pointer'] for r in rows],['/0','/1','/2'])
        row=json_sources.build_json_candidates(b'1',b'1.0')['candidates'][0]
        self.assertEqual(row['pointer'],'')
        self.assertEqual(row['before']['value'],'1')
        self.assertEqual(row['after']['value'],'1.0')
        self.assertIn('numeric_spelling_is_not_numeric_equivalence',row['ambiguities'])

    def test_cap_fails_closed_and_invalid_sources_stay_rejected(self):
        from unittest.mock import patch
        with patch.object(json_sources,'MAX_CANDIDATES',1),self.assertRaises(ValueError):
            json_sources.build_json_candidates(b'{}',b'{"x":1,"y":2}')
        for raw in (b'{"x":1,"x":2}',b'NaN',b'"\\ud800"'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                json_sources.build_json_candidates(b'{}',raw)

    def test_candidate_mutation_does_not_change_evidence(self):
        from copy import deepcopy
        evidence=json_sources.compare_json(b'{"x":1}',b'{"x":2}')
        original=deepcopy(evidence)
        value=json_sources._json_candidates(evidence)
        value['candidates'][0]['after']['value']='forged'
        self.assertEqual(evidence,original)

    def test_cli_opt_in_and_source_bytes_preserved(self):
        import contextlib,io,json,tempfile
        from pathlib import Path
        from inspect_json_sources import main
        with tempfile.TemporaryDirectory() as root:
            a=Path(root)/'a.json';b=Path(root)/'b.json'
            a.write_bytes(b'{"x":1}');b.write_bytes(b'{"x":2}')
            outputs=[]
            for extra in ([],['--candidates']):
                output=io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(['--before',str(a),'--after',str(b),*extra]),0)
                outputs.append(json.loads(output.getvalue()))
            candidates=outputs[1].pop('change_candidates')
            self.assertEqual(outputs[0],outputs[1])
            self.assertEqual(len(candidates['candidates']),1)
            self.assertEqual(a.read_bytes(),b'{"x":1}')
            self.assertEqual(b.read_bytes(),b'{"x":2}')
