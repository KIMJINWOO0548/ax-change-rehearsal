"""Bounded source citations, not Markdown rendering or executable policy extraction."""
import difflib
import hashlib
import os
from pathlib import Path
import re
import stat

MAX_BYTES = 256 * 1024
MAX_LINES = 4096
MAX_BLOCKS = 1024
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
HEADING = re.compile(r'^ {0,3}#{1,6}(?:\s|$)')
TABLE_DIVIDER = re.compile(r'^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def snapshot_markdown(raw):
    """Retain normalized source and line citations; labels are navigational only."""
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError('Source size or type unsupported')
    text = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    if '\x00' in text:
        raise ValueError('NUL in source')
    # Only LF is a line boundary: Unicode paragraph separators remain source text.
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    if len(lines) > MAX_LINES:
        raise ValueError('Source line limit exceeded')
    source_sha = _sha(text.encode('utf-8'))
    blocks, i = [], 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        start = i
        fence = FENCE.match(lines[i])
        if fence:
            marker = fence[1]
            closing = re.compile(r'^ {0,3}' + re.escape(marker[0]) + '{' + str(len(marker)) + r',}\s*$')
            i += 1
            while i < len(lines):
                end = closing.fullmatch(lines[i])
                i += 1
                if end:
                    break
            kind = 'fenced_code'
        elif HEADING.match(lines[i]):
            i += 1
            kind = 'heading'
        else:
            i += 1
            while i < len(lines) and lines[i].strip() and not FENCE.match(lines[i]) and not HEADING.match(lines[i]):
                i += 1
            kind = ('table' if i-start >= 2 and TABLE_DIVIDER.fullmatch(lines[start+1])
                    else 'footnote' if re.match(r'^ {0,3}\[\^[^\]]+\]:', lines[start])
                    else 'paragraph')
        content = '\n'.join(lines[start:i])
        content_sha = _sha(content.encode('utf-8'))
        blocks.append({'kind': kind, 'line_start': start+1, 'line_end': i,
                       'text': content, 'sha256': content_sha,
                       'anchor': f'{source_sha}:{start+1}-{i}:{content_sha}'})
        if len(blocks) > MAX_BLOCKS:
            raise ValueError('Source block limit exceeded')
    return {'format_version': 1, 'raw_sha256': _sha(raw), 'content_sha256': source_sha,
            'normalization': 'UTF-8; CRLF/CR converted to LF; no other rewriting',
            'line_count': len(lines), 'blocks': blocks}


def compare_sources(before, after):
    left, right = snapshot_markdown(before), snapshot_markdown(after)
    a, b = left['blocks'], right['blocks']
    matcher = difflib.SequenceMatcher(None, [(x['kind'], x['sha256']) for x in a],
                                     [(x['kind'], x['sha256']) for x in b], autojunk=False)
    changes = [{'change': tag, 'before': a[i:j], 'after': b[k:l]}
               for tag, i, j, k, l in matcher.get_opcodes()]
    return {'before': left, 'after': right, 'changes': changes,
            'raw_bytes_equal': left['raw_sha256'] == right['raw_sha256'],
            'normalized_document_equal': left['content_sha256'] == right['content_sha256'],
            'block_sequence_equal': all(c['change'] == 'equal' for c in changes),
            'comparison': 'exact normalized blocks; not semantic policy judgment',
            'requires_human_review': True, 'rules_extracted': False,
            'deployment_approval': False}


def inspect_policy_sources(identifier):
    """Only registered authored fixtures; no path, URL, or upload is interpreted."""
    from .policies import ROOT, get_policy
    policy = get_policy(identifier)
    expected = policy.fingerprints()
    contents = {}
    for side in ('before', 'after'):
        names = [name for name in expected if name.endswith('policy_' + side + '.md')]
        if len(names) != 1:
            raise ValueError('Registered source selection invalid')
        with (ROOT / names[0]).open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        snapshot = snapshot_markdown(raw)
        if snapshot['content_sha256'] != expected[names[0]]:
            raise ValueError('Registered source changed during inspection')
        contents[side] = raw
    result = compare_sources(contents['before'], contents['after'])
    if policy.fingerprints() != expected:
        raise ValueError('Registered source changed during inspection')
    return {'policy_version': identifier, 'synthetic_only': True, **result}


def _file_identity(info):
    # Windows stat/fstat can expose different creation/change ctime values.
    # Device/inode/length/mtime remain comparable across the path and handle.
    identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    return identity if os.name == 'nt' else identity + (info.st_ctime_ns,)


def _windows_local_drive(path):
    import ctypes
    get_type = ctypes.windll.kernel32.GetDriveTypeW
    get_type.argtypes = [ctypes.c_wchar_p]
    get_type.restype = ctypes.c_uint
    # Removable, fixed, optical and RAM disks; remote/unknown roots fail closed.
    return get_type(path.anchor) in {2, 3, 5, 6}


def _local_path(value, *, allowed_suffixes=('.md', '.markdown')):
    raw = os.fspath(value)
    if (not isinstance(raw, str) or '\x00' in raw or '://' in raw
            or raw.replace('\\', '/').startswith('//') or ':' in os.path.splitdrive(raw)[1]):
        raise ValueError('Only local Markdown files are supported')
    path = Path(os.path.abspath(raw))
    if str(path).replace('\\', '/').startswith('//'):
        raise ValueError('Network source paths are unsupported')
    if os.name == 'nt' and not _windows_local_drive(path):
        raise ValueError('Only local drives are supported')
    if path.suffix.lower() not in allowed_suffixes:
        raise ValueError('Unsupported local file extension')
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError('Linked source paths are unsupported')
        if os.name == 'nt':
            try:
                attributes = getattr(item.lstat(), 'st_file_attributes', 0)
            except FileNotFoundError:
                continue
            except OSError:
                raise ValueError('Local source unavailable') from None
            # Also works on supported Python versions before is_junction exists.
            if attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                raise ValueError('Reparse source paths are unsupported')
    return path


def _read_local_markdown(value, *, allowed_suffixes=('.md', '.markdown'), maximum=MAX_BYTES):
    path = _local_path(value, allowed_suffixes=allowed_suffixes)
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ValueError('Unsupported source type or size')
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or _file_identity(opened) != _file_identity(before):
                raise ValueError('Source changed before inspection')
            raw = stream.read(maximum + 1)
            if _file_identity(os.fstat(stream.fileno())) != _file_identity(before):
                raise ValueError('Source changed during inspection')
        if len(raw) > maximum or _file_identity(path.lstat()) != _file_identity(before):
            raise ValueError('Source changed during inspection')
        return path, raw, _file_identity(before)
    except OSError:
        raise ValueError('Local source unavailable') from None


def inspect_local_sources(before, after):
    """Read explicitly selected local Markdown only; provenance is unverified.

    Nothing is uploaded, executed, persisted, or inferred to be synthetic.
    Metadata drift checks are not a lock against a hostile local file owner.
    """
    left, right = _read_local_markdown(before), _read_local_markdown(after)
    result = compare_sources(left[1], right[1])
    try:
        for path, raw, identity in (left, right):
            _local_path(path)
            if _file_identity(path.lstat()) != identity:
                raise ValueError('Source changed during comparison')
    except OSError:
        raise ValueError('Local source unavailable') from None
    return {'provenance': 'unverified_local_files', 'business_validated': False, **result}
