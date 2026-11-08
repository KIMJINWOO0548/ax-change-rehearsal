"""Hidden-input CLI contract using explicit synthetic test phrases, never secrets."""
import contextlib
import getpass
import io
import json
import unittest
from unittest.mock import patch
import warnings

import manage_sealed as cli

# Public synthetic test fixture, not a user's credential.
PHRASE = 'synthetic CLI test phrase only'


class SealedCliTests(unittest.TestCase):
    def invoke(self, args, phrases=None, tty=True):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
             patch('sys.stdin.isatty', return_value=tty), \
             patch.object(err, 'isatty', return_value=tty), \
             patch('getpass.getpass', side_effect=phrases or [PHRASE]) as prompt, \
             patch.object(cli, 'check_support'):
            code = cli.main(args)
        return code, out.getvalue(), err.getvalue(), prompt

    def test_seal_requires_confirmation_and_passes_bytes_without_logging(self):
        with patch.object(cli, 'seal_backup', return_value={'encrypted': True, 'integrity_protected': True}) as seal:
            code, out, err, prompt = self.invoke(['seal', '--source', 'bundle', '--destination', 'sealed'], [PHRASE, PHRASE])
        self.assertEqual(code, 0); self.assertEqual(err, '')
        self.assertEqual(prompt.call_count, 2)
        seal.assert_called_once_with('bundle', 'sealed', PHRASE.encode())
        self.assertFalse(json.loads(out)['deployment_approval'])
        self.assertNotIn(PHRASE, out + err)

    def test_non_tty_never_prompts_or_runs(self):
        with patch.object(cli, 'seal_backup') as seal:
            code, out, err, prompt = self.invoke(['seal', '--source', 'private-source', '--destination', 'target'], tty=False)
        self.assertEqual(code, 1); self.assertEqual(out, '')
        prompt.assert_not_called(); seal.assert_not_called()
        self.assertNotIn('private-source', err)

    def test_mismatched_short_or_oversized_input_never_runs(self):
        for phrases in ([PHRASE, PHRASE + ' different'], ['short'], ['한' * 400]):
            with self.subTest(phrases=len(phrases)), patch.object(cli, 'seal_backup') as seal:
                code, out, err, _ = self.invoke(['seal', '--source', 'bundle', '--destination', 'sealed'], phrases)
                self.assertEqual(code, 1); self.assertEqual(out, '')
                seal.assert_not_called(); self.assertNotIn(phrases[0], err)

    def test_getpass_warning_is_fatal_not_echoed_stdin_fallback(self):
        def warning(*args):
            warnings.warn('Cannot disable echo', getpass.GetPassWarning)
            raise AssertionError('Warning must stop the input call')
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
             patch('sys.stdin.isatty', return_value=True), patch.object(err, 'isatty', return_value=True), \
             patch('getpass.getpass', side_effect=warning), patch.object(cli, 'inspect_sealed') as inspect, \
             patch.object(cli, 'check_support'):
            code = cli.main(['inspect', '--source', 'sealed'])
        self.assertEqual(code, 1); inspect.assert_not_called()
        self.assertNotIn('Cannot disable echo', err.getvalue())

    def test_wrong_password_or_tamper_errors_do_not_leak_details(self):
        with patch.object(cli, 'restore_sealed', side_effect=cli.SealedError('secret detail /private/path')):
            code, out, err, _ = self.invoke(['restore', '--source', 'sealed', '--destination', 'restored'])
        self.assertEqual(code, 1); self.assertEqual(out, '')
        self.assertEqual(json.loads(err)['error'], 'SEALED_OPERATION_UNAVAILABLE')
        self.assertNotIn('secret detail', err); self.assertNotIn('private/path', err)

    def test_inspect_and_restore_prompt_once(self):
        for action in ('inspect', 'restore'):
            args = [action, '--source', 'sealed'] + (['--destination', 'restored'] if action == 'restore' else [])
            with self.subTest(action=action), patch.object(cli, action + '_sealed', return_value={}) as operation:
                code, _, _, prompt = self.invoke(args)
                self.assertEqual(code, 0); self.assertEqual(prompt.call_count, 1)
                operation.assert_called_once()

    def test_password_argument_is_not_an_available_interface(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            cli.main(['inspect', '--source', 'private-source-marker', '--password', PHRASE])
        self.assertNotIn(PHRASE, out.getvalue() + err.getvalue())
        self.assertNotIn('private-source-marker', out.getvalue() + err.getvalue())

    def test_missing_capability_fails_before_prompt(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
             patch.object(cli, 'check_support', side_effect=cli.SealedDependencyError('unavailable')), \
             patch('getpass.getpass') as prompt:
            code = cli.main(['inspect', '--source', 'sealed'])
        self.assertEqual(code, 1); self.assertEqual(out.getvalue(), '')
        self.assertEqual(json.loads(err.getvalue())['error'], 'SEALED_FEATURE_UNAVAILABLE')
        prompt.assert_not_called()
