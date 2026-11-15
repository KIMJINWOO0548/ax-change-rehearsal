"""Segment rollover keeps every original report and refuses pending work."""
import tempfile
import unittest
from pathlib import Path
from rehearsal.storage import EvidenceStore
from rehearsal.recovery import inspect_backup, restore_backup, RecoveryError
from tests.test_storage import report

class RetentionTests(unittest.TestCase):
    def test_101_reports_retained_without_eviction(self):
        from rehearsal.recovery import rollover_workspace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); store=EvidenceStore(root/'active')
            originals=[report() for _ in range(100)]
            for value in originals: store.save(value)
            outcome=rollover_workspace(store.workspace, root/'archive', root/'next')
            self.assertEqual(outcome['archived_run_count'],100)
            next_store=EvidenceStore(root/'next'); next_store.save(report())
            self.assertEqual(len(store.list_runs())+len(next_store.list_runs()),101)
            restore_backup(root/'archive',root/'restore')
            restored=EvidenceStore(root/'restore')
            self.assertEqual({x['run_id'] for x in restored.list_runs()}, {x['run_id'] for x in originals})

    def test_pending_attempt_blocks_rollover_without_new_workspace(self):
        from rehearsal.recovery import rollover_workspace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); store=EvidenceStore(root/'active')
            store.begin_attempt({'faq_version':'corrected','api_version':'corrected'})
            with self.assertRaises(RecoveryError): rollover_workspace(store.workspace,root/'archive',root/'next')
            self.assertFalse((root/'next').exists())
            self.assertEqual(store.list_attempts()[0]['state'],'INCOMPLETE')

    def test_existing_next_workspace_is_never_reused(self):
        from rehearsal.recovery import rollover_workspace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); store=EvidenceStore(root/'active'); store.save(report())
            target=root/'next'; target.mkdir(); (target/'keep').write_text('keep')
            with self.assertRaises(RecoveryError): rollover_workspace(store.workspace,root/'archive',target)
            self.assertEqual((target/'keep').read_text(),'keep')
            self.assertFalse((root/'archive').exists())
