import hashlib
import unittest
from unittest.mock import patch
from rehearsal.source_evidence import snapshot_markdown, compare_sources, inspect_policy_sources


class SourceEvidenceTests(unittest.TestCase):
    def test_blocks_preserve_lines_and_distinguish_duplicates(self):
        text = '# Heading\n\nSame\n\nSame\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n[^1]: Note\n    continuation\n\n```python\n# not a heading\n\nprint(1)\n```\n'
        result = snapshot_markdown(text.encode())
        self.assertEqual([b['kind'] for b in result['blocks']],
                         ['heading','paragraph','paragraph','table','footnote','fenced_code'])
        lines = text.splitlines()
        for block in result['blocks']:
            self.assertEqual(block['text'], '\n'.join(lines[block['line_start']-1:block['line_end']]))
            self.assertEqual(block['sha256'], hashlib.sha256(block['text'].encode()).hexdigest())
        self.assertEqual(result['blocks'][1]['sha256'], result['blocks'][2]['sha256'])
        self.assertNotEqual(result['blocks'][1]['anchor'], result['blocks'][2]['anchor'])

    def test_line_endings_have_explicit_raw_and_normalized_hashes(self):
        a=snapshot_markdown(b'# H\n\nBody\n'); b=snapshot_markdown(b'# H\r\n\r\nBody\r\n')
        self.assertEqual(a['content_sha256'],b['content_sha256'])
        self.assertNotEqual(a['raw_sha256'],b['raw_sha256'])
        self.assertEqual(a['blocks'],b['blocks'])

    def test_diff_retains_equal_exclusions_and_exact_replacements(self):
        output=compare_sources(b'# Policy\n\n14 days\n\nExclude opened goods\n',b'# Policy\n\n30 days\n\nExclude opened goods\n\nNew footnote\n')
        self.assertEqual([c['change'] for c in output['changes']],['equal','replace','equal','insert'])
        self.assertTrue(output['requires_human_review'])
        self.assertFalse(output['deployment_approval'])
        self.assertEqual(output['changes'][1]['before'][0]['text'],'14 days')
        self.assertEqual(output['changes'][1]['after'][0]['text'],'30 days')
        self.assertEqual(compare_sources(b'a\n\nb',b'a')['changes'][-1]['change'],'delete')

    def test_empty_and_fenced_content_are_not_lost(self):
        self.assertEqual(snapshot_markdown(b' \n\n')['blocks'],[])
        block=snapshot_markdown(b'~~~\n\n# h\n| x |\n')['blocks'][0]
        self.assertEqual(block['kind'],'fenced_code')
        self.assertEqual(block['line_end'],4)

    def test_malformed_and_bounded_inputs_fail(self):
        for raw in (b'\xff',b'a\x00b',b'a'*262145,b'\n'*4097,('a\n\n'*1025).encode()):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):snapshot_markdown(raw)
        with self.assertRaises(ValueError):snapshot_markdown('text')

    def test_registered_versions_are_repeatable_and_distinct(self):
        old=inspect_policy_sources('returns-20261201'); new=inspect_policy_sources('returns-20270115')
        self.assertEqual(old,inspect_policy_sources('returns-20261201'))
        self.assertNotEqual(old['after']['content_sha256'],new['after']['content_sha256'])
        self.assertTrue(old['synthetic_only'])
        self.assertFalse(old['rules_extracted'])
        with self.assertRaises(ValueError):inspect_policy_sources('../secret')

    def test_registered_bytes_drift_is_rejected(self):
        from pathlib import Path
        original=Path.open
        import io
        def changed(path,*args,**kwargs):
            if args == ('rb',) and path.name=='policy_after.md':return io.BytesIO(b'changed')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',changed),self.assertRaises(ValueError):
            inspect_policy_sources('returns-20261201')

    def test_unicode_separators_and_longer_code_fences_preserve_content(self):
        result=snapshot_markdown('````\n```\nA\u2028B\n````\n# End'.encode())
        self.assertEqual(result['line_count'],5)
        self.assertEqual(result['blocks'][0]['line_end'],4)
        self.assertIn('A\u2028B',result['blocks'][0]['text'])
        self.assertEqual(result['blocks'][1]['kind'],'heading')

    def test_repeated_blocks_have_deterministic_complete_alignment(self):
        before=('same\n\n'*200).encode()
        after=('same\n\n'*100+'changed\n\n'+'same\n\n'*100).encode()
        result=compare_sources(before,after)
        self.assertEqual(result,compare_sources(before,after))
        self.assertEqual(sum(len(c['before']) for c in result['changes']),200)
        self.assertEqual(sum(len(c['after']) for c in result['changes']),201)

    def test_cli_emits_json_and_redacts_invalid_identifier(self):
        import contextlib,io,json
        from inspect_sources import main
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=main(['--policy-version','returns-20270115'])
        self.assertEqual(code,0)
        self.assertTrue(json.loads(out.getvalue())['requires_human_review'])
        self.assertEqual(err.getvalue(),'')
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=main(['--policy-version','private-local-path'])
        self.assertEqual(code,1)
        self.assertEqual(out.getvalue(),'')
        self.assertNotIn('private-local-path',err.getvalue())
        self.assertEqual(json.loads(err.getvalue())['error'],'SOURCE_EVIDENCE_UNAVAILABLE')

    def test_inspection_never_changes_registered_artifacts(self):
        from rehearsal.policies import ROOT,get_policy
        paths=[ROOT/name for name,_ in get_policy('returns-20261201').files]
        before={str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in paths}
        inspect_policy_sources('returns-20261201')
        self.assertEqual(before,{str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in paths})

    def test_blank_line_only_change_is_not_document_equality(self):
        result=compare_sources(b'A\n\nB\n',b'A\n\n \nB\n')
        self.assertTrue(result['block_sequence_equal'])
        self.assertFalse(result['normalized_document_equal'])
        self.assertFalse(result['raw_bytes_equal'])
        newline=compare_sources(b'A\r\n',b'A\n')
        self.assertTrue(newline['normalized_document_equal'])
        self.assertFalse(newline['raw_bytes_equal'])
