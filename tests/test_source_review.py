import json
from pathlib import Path
import tempfile
import unittest
from rehearsal.source_review import record_review, verify_review


class SourceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.before=self.root/'before.md'; self.after=self.root/'after.md'; self.record=self.root/'review.json'
        self.before.write_bytes(b'Private source 14 days');self.after.write_bytes(b'Private source 30 days')

    def create(self,status='REVIEWED',destination=None):
        return record_review(self.before,self.after,destination or self.record,reviewer='Local reviewer',status=status,note='Check exclusions')

    def test_current_is_not_approval_and_source_text_paths_are_not_saved(self):
        before={p:p.read_bytes() for p in (self.before,self.after)}
        self.create()
        raw=self.record.read_bytes(); result=verify_review(self.record,self.before,self.after)
        self.assertEqual(result['binding'],'CURRENT');self.assertEqual(result['review_status'],'REVIEWED')
        self.assertFalse(result['authenticated']);self.assertFalse(result['deployment_approval'])
        self.assertNotIn(b'Private source',raw);self.assertNotIn(str(self.root).encode(),raw)
        self.assertEqual(raw,self.record.read_bytes())
        self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_changes_requested_never_becomes_accepted(self):
        self.create('CHANGES_REQUESTED')
        result=verify_review(self.record,self.before,self.after)
        self.assertEqual(result['binding'],'CURRENT')
        self.assertEqual(result['review_status'],'CHANGES_REQUESTED')
        self.assertFalse(result['deployment_approval'])

    def test_source_change_and_line_endings_invalidate_without_rewriting_record(self):
        self.create(); raw=self.record.read_bytes()
        self.after.write_bytes(b'Private source 31 days')
        self.assertEqual(verify_review(self.record,self.before,self.after)['binding'],'STALE')
        self.after.write_bytes(b'Private source 30 days\r\n')
        self.assertEqual(verify_review(self.record,self.before,self.after)['binding'],'STALE')
        self.assertEqual(raw,self.record.read_bytes())

    def test_existing_destinations_and_invalid_metadata_never_overwrite(self):
        self.create();raw=self.record.read_bytes()
        with self.assertRaises(ValueError):self.create()
        self.assertEqual(raw,self.record.read_bytes())
        for kwargs in ({'reviewer':''},{'status':'APPROVED'},{'note':'x'*1001}):
            params=dict(reviewer='r',status='REVIEWED',note='');params.update(kwargs)
            target=self.root/'invalid.json'
            with self.assertRaises(ValueError):record_review(self.before,self.after,target,**params)
            self.assertFalse(target.exists())

    def test_corruption_unknown_fields_and_oversize_fail_closed(self):
        self.create();original=json.loads(self.record.read_text('utf-8'))
        variants=[b'{',b'x'*32769,b'{"format_version":1,"format_version":1}']
        changed=json.loads(json.dumps(original));changed['record']['note']='rewritten';variants.append(json.dumps(changed).encode())
        changed={**original,'extra':'unknown'};variants.append(json.dumps(changed).encode())
        for raw in variants:
            self.record.write_bytes(raw)
            with self.assertRaises(ValueError):verify_review(self.record,self.before,self.after)

    def test_recomputed_checksum_cannot_grant_approval_or_change_schema(self):
        from rehearsal.storage import sha
        self.create(); original=json.loads(self.record.read_text('utf-8'))
        for change in ({'deployment_approval':True},{'authenticated':True},{'review_status':'APPROVED'},{'created_at':'yesterday'},{'provenance':'verified_business'}):
            value=json.loads(json.dumps(original));value['record'].update(change)
            value['record_sha256']=sha(value['record'])
            self.record.write_text(json.dumps(value),'utf-8')
            with self.assertRaises(ValueError):verify_review(self.record,self.before,self.after)

    def test_cli_status_codes_and_metadata_privacy(self):
        import contextlib,io
        from review_sources import main
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            code=main(['record','--before',str(self.before),'--after',str(self.after),'--destination',str(self.record),'--reviewer','private reviewer','--status','REVIEWED','--note','private note'])
        self.assertEqual(code,0)
        self.assertNotIn('private reviewer',output.getvalue());self.assertNotIn('private note',output.getvalue())
        self.after.write_bytes(b'Changed')
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            code=main(['verify','--source',str(self.record),'--before',str(self.before),'--after',str(self.after)])
        self.assertEqual(code,2);self.assertEqual(json.loads(output.getvalue())['binding'],'STALE')
        error=io.StringIO()
        self.record.write_bytes(b'invalid private content')
        with contextlib.redirect_stderr(error):
            code=main(['verify','--source',str(self.record),'--before',str(self.before),'--after',str(self.after)])
        self.assertEqual(code,1);self.assertNotIn('private content',error.getvalue());self.assertNotIn(str(self.root),error.getvalue())

    def test_flush_failure_is_not_reported_as_saved_and_file_is_preserved(self):
        from unittest.mock import patch
        with patch('rehearsal.source_review.os.fsync',side_effect=OSError('failure')):
            with self.assertRaises(ValueError):self.create()
        self.assertTrue(self.record.exists())
        before=self.record.read_bytes()
        with self.assertRaises(ValueError):self.create()
        self.assertEqual(before,self.record.read_bytes())
