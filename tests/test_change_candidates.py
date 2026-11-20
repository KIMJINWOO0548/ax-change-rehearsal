import contextlib
import io
import json
import unittest
from rehearsal.source_evidence import compare_sources
from rehearsal.change_candidates import build_change_candidates


class ChangeCandidateTests(unittest.TestCase):
    def candidates(self,before,after):
        return build_change_candidates(compare_sources(before.encode(),after.encode()))

    def test_dates_quantities_and_boundaries_are_unreviewed_literals(self):
        result=self.candidates('Effective 2026-12-01; <= 14 days','Effective 2027-01-15; < 21 days')
        row=result['candidates'][0]
        self.assertEqual(row['review_status'],'UNREVIEWED')
        self.assertIsNone(row['executable_rule'])
        self.assertFalse(result['deployment_approval'])
        self.assertEqual([x['text'] for x in row['removed_markers']],['2026-12-01','<=','14 days'])
        self.assertEqual([x['text'] for x in row['added_markers']],['2027-01-15','<','21 days'])
        self.assertTrue(all(x['anchor'] for x in row['added_markers']))

    def test_unchanged_markers_are_not_changed_and_duplicates_are_counted(self):
        row=self.candidates('14 days and 14 days, exclude opened','14 days, exclude opened')['candidates'][0]
        self.assertEqual([x['text'] for x in row['removed_markers']],['14 days'])
        self.assertEqual(row['added_markers'],[])

    def test_marker_offsets_and_lines_refer_to_exact_original_block(self):
        source='Heading\nsecond: 14일 이하'
        row=self.candidates(source,source.replace('14','30'))['candidates'][0]
        for marker in row['before_markers']:
            self.assertEqual(source[marker['start']:marker['end']],marker['text'])
            self.assertEqual(marker['line'],2)
        self.assertEqual([x['text'] for x in row['before_markers']],['14일','이하'])

    def test_invalid_dates_remain_uncertain_and_code_is_not_a_rule(self):
        row=self.candidates('2026-12-01','2026-99-99')['candidates'][0]
        self.assertFalse(row['after_markers'][0]['calendar_valid'])
        code=self.candidates('```\nx=14\n```','```\nx=30\n```')['candidates'][0]
        self.assertEqual(code['before_markers'],[])
        self.assertEqual(code['after_markers'],[])
        self.assertIn('non_prose_requires_review',code['ambiguities'])

    def test_text_changes_and_unchanged_documents_are_not_guessed(self):
        row=self.candidates('Exclude opened','Include opened')['candidates'][0]
        self.assertEqual(row['before_markers'],[])
        self.assertIn('meaning_scope_and_exceptions_not_inferred',row['ambiguities'])
        self.assertEqual(self.candidates('Same','Same')['candidates'],[])

    def test_marker_limit_fails_instead_of_silent_truncation(self):
        with self.assertRaises(ValueError):self.candidates('',' '.join(['14']*2049))

    def test_cli_opt_in_does_not_change_default_comparison(self):
        from inspect_sources import main
        def run(extra):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['--policy-version','returns-20261201',*extra]),0)
            return json.loads(output.getvalue())
        ordinary=run([]);expanded=run(['--candidates'])
        self.assertNotIn('change_candidates',ordinary)
        expanded.pop('change_candidates')
        self.assertEqual(ordinary,expanded)

    def test_sentence_punctuation_does_not_hide_changed_numbers(self):
        for before,after,old,new in (
            ('Limit 14.','Limit 30.','14','30'),
            ('Limit 14, exceptions apply','Limit 30, exceptions apply','14','30'),
            ('Limit 1,000.','Limit 2,000.','1,000','2,000'),
            ('Limit -0.5.','Limit +0.25.','-0.5','+0.25')):
            with self.subTest(before=before):
                row=self.candidates(before,after)['candidates'][0]
                self.assertEqual([x['text'] for x in row['removed_markers']],[old])
                self.assertEqual([x['text'] for x in row['added_markers']],[new])

    def test_malformed_numeric_chains_are_not_silently_split_into_thresholds(self):
        row=self.candidates('Text','Malformed 12,34 or 1.2.3')['candidates'][0]
        self.assertEqual(row['after_markers'],[])
