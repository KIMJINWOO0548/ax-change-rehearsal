import json
from pathlib import Path
import tempfile
import unittest
from rehearsal.source_evidence import inspect_local_sources
from rehearsal.change_candidates import build_change_candidates
from rehearsal.candidate_review import record_candidate_review, verify_candidate_review


class CandidateReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.before=self.root/'before.md';self.after=self.root/'after.md';self.record=self.root/'review.json'
        self.before.write_bytes(b'Private source 14 days\n\nUnchanged\n\nLimit 100.')
        self.after.write_bytes(b'Private source 30 days\n\nUnchanged\n\nLimit 200.')
        self.ids=[c['candidate_id'] for c in build_change_candidates(inspect_local_sources(self.before,self.after))['candidates']]
        self.assertEqual(len(self.ids),2)

    def decisions(self,status='CONFIRMED_CHANGE'):
        return [dict(candidate_id=i,decision=status,reason='Reviewed original clause') for i in self.ids]

    def create(self,decisions):
        return record_candidate_review(self.before,self.after,self.record,reviewer='Operator',decisions=decisions)

    def test_partial_review_keeps_missing_candidates_pending(self):
        self.create(self.decisions()[:1]);result=verify_candidate_review(self.record,self.before,self.after)
        self.assertEqual(result['binding'],'CURRENT');self.assertFalse(result['review_complete'])
        self.assertEqual(result['current_unreviewed_count'],1)
        self.assertEqual(result['recorded_counts']['PENDING'],1)
        self.assertNotIn(b'Private source',self.record.read_bytes())
        self.assertNotIn(str(self.root).encode(),self.record.read_bytes())

    def test_clarification_remains_open_and_final_dispositions_are_not_approval(self):
        self.create(self.decisions('NEEDS_CLARIFICATION'))
        result=verify_candidate_review(self.record,self.before,self.after)
        self.assertFalse(result['review_complete']);self.assertEqual(result['current_unreviewed_count'],2)
        other=self.root/'final.json'
        record_candidate_review(self.before,self.after,other,reviewer='Operator',decisions=self.decisions())
        final=verify_candidate_review(other,self.before,self.after)
        self.assertTrue(final['review_complete']);self.assertFalse(final['deployment_approval']);self.assertFalse(final['authenticated'])

    def test_source_drift_never_carries_decisions_forward(self):
        self.create(self.decisions());before=self.record.read_bytes()
        self.after.write_bytes(b'Private source 31 days\n\nUnchanged\n\nLimit 201.')
        result=verify_candidate_review(self.record,self.before,self.after)
        self.assertEqual(result['binding'],'STALE');self.assertFalse(result['review_complete'])
        self.assertEqual(result['current_unreviewed_count'],result['current_candidate_count'])
        self.assertEqual(result['recorded_counts']['CONFIRMED_CHANGE'],2)
        self.assertEqual(self.record.read_bytes(),before)

    def test_unknown_duplicate_invalid_decisions_never_create_record(self):
        variants=[self.decisions()+self.decisions()[:1],[dict(candidate_id='0'*64,decision='NOT_A_RULE',reason='r')],
                  [dict(candidate_id=self.ids[0],decision='APPROVED',reason='r')],
                  [dict(candidate_id=self.ids[0],decision='CONFIRMED_CHANGE',reason=' ')],
                  [dict(candidate_id=self.ids[0],decision='CONFIRMED_CHANGE',reason='x'*1001)]]
        for value in variants:
            with self.subTest(value=str(value)[:80]),self.assertRaises(ValueError):self.create(value)
            self.assertFalse(self.record.exists())

    def test_overwrite_and_corruption_are_rejected(self):
        self.create([]);raw=self.record.read_bytes()
        with self.assertRaises(ValueError):self.create(self.decisions())
        self.assertEqual(raw,self.record.read_bytes())
        data=json.loads(raw);data['record']['candidates'][0]['decision']='CONFIRMED_CHANGE'
        self.record.write_text(json.dumps(data),'utf-8')
        with self.assertRaises(ValueError):verify_candidate_review(self.record,self.before,self.after)

    def test_recomputed_checksum_cannot_substitute_candidate_ids(self):
        from rehearsal.storage import sha
        self.create(self.decisions());data=json.loads(self.record.read_bytes())
        data['record']['candidates'][0]['candidate_id']='0'*64
        data['record_sha256']=sha(data['record'])
        self.record.write_text(json.dumps(data),'utf-8')
        with self.assertRaises(ValueError):verify_candidate_review(self.record,self.before,self.after)

    def test_empty_current_candidates_cannot_make_stale_review_complete(self):
        self.create(self.decisions());self.after.write_bytes(self.before.read_bytes())
        result=verify_candidate_review(self.record,self.before,self.after)
        self.assertEqual(result['binding'],'STALE');self.assertEqual(result['current_candidate_count'],0)
        self.assertFalse(result['review_complete'])
        with self.assertRaises(ValueError):record_candidate_review(self.before,self.after,self.root/'empty.json',reviewer='r',decisions=[])
        self.assertFalse((self.root/'empty.json').exists())

    def test_cli_status_and_output_do_not_disclose_reviewer_reasons(self):
        import contextlib,io
        from review_candidates import main
        selection=self.root/'decisions.json';selection.write_text(json.dumps(self.decisions()),'utf-8')
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            code=main(['record','--before',str(self.before),'--after',str(self.after),'--destination',str(self.record),'--decisions',str(selection),'--reviewer','private reviewer'])
        self.assertEqual(code,0);self.assertNotIn('private reviewer',out.getvalue());self.assertNotIn('Reviewed original clause',out.getvalue())
        self.after.write_bytes(b'Changed')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['verify','--before',str(self.before),'--after',str(self.after),'--source',str(self.record)]),2)
        self.record.write_bytes(b'invalid confidential data');err=io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main(['verify','--before',str(self.before),'--after',str(self.after),'--source',str(self.record)]),1)
        self.assertNotIn('confidential',err.getvalue());self.assertNotIn(str(self.root),err.getvalue())

    def test_large_and_duplicate_key_json_are_rejected(self):
        self.create([])
        for raw in (b'x'*(512*1024+1),b'{"format_version":1,"format_version":1}'):
            self.record.write_bytes(raw)
            with self.assertRaises(ValueError):verify_candidate_review(self.record,self.before,self.after)
