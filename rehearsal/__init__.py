"""Synthetic rehearsal package with process-lifetime source drift detection.

This is not code signing, an OS sandbox, or protection against a local writer.
Restart after upgrades. Keep the checkout immutable while a process is running.
"""
import hashlib
from pathlib import Path

__version__ = '0.7.0'

_SOURCE_ROOT = Path(__file__).resolve().parent
# Capture before submodules import, rather than fingerprinting newer disk code
# and attributing it to an already-imported implementation at execution time.
_STARTUP_SOURCES = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in _SOURCE_ROOT.glob('*.py')}


def assert_sources_unchanged():
    try:
        current = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in _SOURCE_ROOT.glob('*.py')}
    except OSError as error:
        raise RuntimeError('Execution sources changed; restart and review before running.') from error
    if current != _STARTUP_SOURCES:
        raise RuntimeError('Execution sources changed; restart and review before running.')
