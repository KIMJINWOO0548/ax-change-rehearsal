#!/usr/bin/env python3
"""Measure a small registered SYNTHETIC sealed roundtrip in an isolated process.

No user files, passwords, or paths are accepted or returned. This is not a load
benchmark or a claim that maximum-size backups fit every machine.
"""
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rehearsal.app import execute_run
from rehearsal.recovery import create_backup
from rehearsal.sealed import seal_backup, inspect_sealed, restore_sealed
from rehearsal.storage import EvidenceStore


def peak_resident_bytes():
    if os.name == 'posix':
        import resource
        size = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(size if sys.platform == 'darwin' else size * 1024), 'getrusage peak RSS'
    if os.name == 'nt':
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                    'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                    'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError('Memory measurement unavailable')
        return int(counters.PeakWorkingSetSize), 'GetProcessMemoryInfo peak working set'
    return None, 'unavailable'


def main():
    # Public synthetic fixture, not a user credential. Never use it for backups.
    phrase = b'synthetic measurement phrase only'
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = EvidenceStore(root / 'source')
        report = execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})
        store.save(report)
        create_backup(root / 'source', root / 'bundle')
        measurements = {}
        for name, action in (
            ('seal', lambda: seal_backup(root / 'bundle', root / 'sample.axsealed', phrase)),
            ('inspect', lambda: inspect_sealed(root / 'sample.axsealed', phrase)),
            ('restore', lambda: restore_sealed(root / 'sample.axsealed', root / 'restored', phrase)),
        ):
            start = time.perf_counter()
            action()
            measurements[name + '_seconds'] = round(time.perf_counter() - start, 4)
        assert EvidenceStore(root / 'restored').get(report['run_id'])['report'] == report
        peak, method = peak_resident_bytes()
        print(json.dumps({'synthetic_only': True, 'cases': report['total'],
                          'database_bytes': (root / 'bundle/evidence.sqlite3').stat().st_size,
                          'sealed_bytes': (root / 'sample.axsealed').stat().st_size,
                          'peak_process_resident_bytes': peak, 'memory_method': method,
                          'scrypt_n': 2**17, 'scrypt_r': 8, 'scrypt_p': 1,
                          **measurements}, indent=2))


if __name__ == '__main__':
    main()
