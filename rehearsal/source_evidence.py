"""Bounded source citations, not Markdown rendering or executable policy extraction."""
import difflib
import hashlib
import re

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
