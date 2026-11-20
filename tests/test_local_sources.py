import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rehearsal.source_evidence import inspect_local_sources, MAX_BYTES
from inspect_sources import main


class LocalSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.before=self.root/'before.md'; self.after=self.root/'after.markdown'
        self.before.write_bytes(b'# Policy\n\n14 days\n')
        self.after.write_bytes(b'# Policy\n\n30 days\n')

    def test_reads_real_files_without_synthetic_or_business_claim(self):
        snapshots={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (self.before,self.after)}
        result=inspect_local_sources(self.before,self.after)
        self.assertEqual(result['provenance'],'unverified_local_files')
        self.assertNotIn('synthetic_only',result)
        self.assertFalse(result['business_validated'])
        self.assertFalse(result['deployment_approval'])
        self.assertEqual(result['changes'][-1]['change'],'replace')
        self.assertNotIn(str(self.root),json.dumps(result))
        self.assertEqual(snapshots,{p:(p.read_bytes(),p.stat().st_mtime_ns) for p in snapshots})

    def test_invalid_source_never_creates_files_or_reads_special_inputs(self):
        invalid=[self.root/'missing.md',self.root,self.root/'input.pdf','https://example.com/policy.md']
        for value in invalid:
            with self.subTest(value=str(value)),self.assertRaises(ValueError):
                inspect_local_sources(value,self.after)
        self.assertFalse((self.root/'missing.md').exists())

    def test_oversize_invalid_utf8_and_nul_rejected(self):
        for raw in (b'x'*(MAX_BYTES+1),b'\xff',b'a\x00b'):
            self.before.write_bytes(raw)
            with self.assertRaises(ValueError):inspect_local_sources(self.before,self.after)

    def test_cli_modes_are_exclusive_and_local_errors_hide_paths(self):
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=main(['--before',str(self.before),'--after',str(self.after)])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(out.getvalue())['provenance'],'unverified_local_files')
        for args in (['--before',str(self.before)],['--policy-version','returns-20261201','--before',str(self.before),'--after',str(self.after)]):
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):main(args)
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(err):
            code=main(['--before',str(self.root/'secret.md'),'--after',str(self.after)])
        self.assertEqual(code,1)
        self.assertNotIn('secret.md',err.getvalue())

    def test_change_after_first_read_is_rejected(self):
        import rehearsal.source_evidence as sources
        original=sources._read_local_markdown
        def changed(path):
            result=original(path)
            if Path(path)==self.after:self.before.write_bytes(b'changed during comparison')
            return result
        with patch.object(sources,'_read_local_markdown',changed),self.assertRaises(ValueError):
            inspect_local_sources(self.before,self.after)

    def test_symlink_input_is_rejected_where_supported(self):
        alias=self.root/'alias.md'
        try:alias.symlink_to(self.before)
        except OSError as exc:self.skipTest('symlink creation unavailable: '+str(exc.errno))
        with self.assertRaises(ValueError):inspect_local_sources(alias,self.after)

    def test_same_file_compares_equal_without_modifying_it(self):
        result=inspect_local_sources(self.before,self.before)
        self.assertTrue(result['raw_bytes_equal'])
        self.assertTrue(result['block_sequence_equal'])

    def test_windows_ctime_is_not_assumed_equivalent_between_path_and_handle(self):
        from types import SimpleNamespace
        from rehearsal.source_evidence import _file_identity
        a=SimpleNamespace(st_dev=1,st_ino=2,st_size=3,st_mtime_ns=4,st_ctime_ns=5)
        b=SimpleNamespace(st_dev=1,st_ino=2,st_size=3,st_mtime_ns=4,st_ctime_ns=6)
        self.assertEqual(_file_identity(a)==_file_identity(b),os.name=='nt')

    def test_unc_device_and_alternate_stream_paths_never_open(self):
        import rehearsal.source_evidence as sources
        for path in (r'\\server\share\a.md',r'/\server\share\a.md',r'\\?\C:\a.md',r'C:\a.txt:stream.md','file:source.md'):
            with self.subTest(path=path),patch.object(sources.os,'open') as opened:
                with self.assertRaises(ValueError):inspect_local_sources(path,self.after)
                opened.assert_not_called()

    @unittest.skipUnless(os.name=='nt','Windows drive mapping boundary')
    def test_network_mapped_drive_is_rejected_before_open(self):
        import rehearsal.source_evidence as sources
        with patch.object(sources,'_windows_local_drive',return_value=False),patch.object(sources.os,'open') as opened:
            with self.assertRaises(ValueError):inspect_local_sources(self.before,self.after)
            opened.assert_not_called()

    @unittest.skipUnless(os.name=='nt','Windows UNC current directory boundary')
    def test_relative_path_resolving_to_unc_is_rejected_before_open(self):
        import rehearsal.source_evidence as sources
        with patch.object(sources.os.path,'abspath',return_value=r'\\server\share\source.md'),patch.object(sources.os,'open') as opened:
            with self.assertRaises(ValueError):inspect_local_sources('source.md',self.after)
            opened.assert_not_called()

    @unittest.skipUnless(os.name=='nt','Windows reparse metadata boundary')
    def test_reparse_attribute_is_rejected_without_is_junction(self):
        from types import SimpleNamespace
        import rehearsal.source_evidence as sources
        with patch.object(Path,'is_symlink',return_value=False),patch.object(Path,'is_junction',return_value=False,create=True),patch.object(Path,'lstat',return_value=SimpleNamespace(st_file_attributes=0x400)),patch.object(sources.os,'open') as opened:
            with self.assertRaises(ValueError):inspect_local_sources(self.before,self.after)
            opened.assert_not_called()
