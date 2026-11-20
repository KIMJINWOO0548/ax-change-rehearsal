"""Package the AX workbench and its standard-library runtime for Windows x64."""

import argparse
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'desktop/AXRehearsal/AXRehearsal.csproj'
WEBVIEW2 = '1.0.4258.31'
EXCLUDED = {'__pycache__', 'site-packages', 'test', 'tests', 'idlelib', 'tkinter', 'ensurepip'}


def write_tree(archive, path, target):
    for file in path.rglob('*'):
        relative = file.relative_to(path)
        if file.is_file() and not EXCLUDED.intersection(relative.parts) and file.suffix != '.pyc':
            archive.write(file, Path('AXRehearsal') / target / relative)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--nuget-source', type=Path, default=Path.home() / '.nuget/packages')
    args = parser.parse_args()
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32:
        parser.error('Build with x64 Python 3.12 on Windows')
    if args.output.suffix.lower() != '.zip' or args.output.exists():
        parser.error('Choose a new .zip output')
    with TemporaryDirectory(prefix='ax-windows-build-') as temporary:
        payload = Path(temporary) / 'app'
        subprocess.run(['dotnet', 'restore', str(PROJECT), '-r', 'win-x64',
                        '--source', str(args.nuget_source), '-p:NuGetAudit=false'], check=True)
        subprocess.run(['dotnet', 'publish', str(PROJECT), '-c', 'Release', '-r', 'win-x64',
                        '--self-contained', 'false', '--no-restore', '-o', str(payload),
                        '-p:DebugSymbols=false', '-p:DebugType=None'], check=True)
        with ZipFile(args.output, 'x', compression=ZIP_DEFLATED) as archive:
            write_tree(archive, payload, Path())
            for name in ('fixtures', 'examples', 'rehearsal', 'web'):
                write_tree(archive, ROOT / name, Path(name))
            archive.write(ROOT / 'desktop_workbench.py', 'AXRehearsal/desktop_workbench.py')
            archive.write(ROOT / 'docs/windows-app.md', 'AXRehearsal/사용법.md')
            base = Path(sys.base_prefix)
            for name in ('python.exe', 'python3.dll', 'python312.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt'):
                archive.write(base / name, f'AXRehearsal/python/{name}')
            for name in ('DLLs', 'Lib'):
                write_tree(archive, base / name, Path('python') / name)
            for name in ('LICENSE.txt', 'NOTICE.txt'):
                archive.write(args.nuget_source / 'microsoft.web.webview2' / WEBVIEW2 / name,
                              f'AXRehearsal/WebView2-{name}')
    print(args.output.resolve())


if __name__ == '__main__':
    main()
