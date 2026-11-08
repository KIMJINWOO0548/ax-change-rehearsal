"""Optional passphrase sealing of verified local recovery bundles.

Only the new sealed copy is encrypted. Original files and process memory are not.
The fixed format authenticates bytes, not reviewer identity or freshness. No
key material is persisted; Python cannot promise erasure of immutable buffers.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import tempfile

from . import recovery
from .storage import MAX_DATABASE_BYTES, MAX_LEDGER_ROWS, LIMIT, canonical
from .validation import _reject_constant, _unique_pairs

MAGIC = b'AXSEALED'
VERSION = 1
# There are deliberately no algorithm or KDF-cost fields to negotiate.
HEADER = struct.Struct('>8sB16s12sQ')
MANIFEST_LENGTH = struct.Struct('>I')
MAX_CIPHERTEXT = 4 + recovery.MANIFEST_LIMIT + MAX_DATABASE_BYTES + 16
MAX_SEALED_BYTES = HEADER.size + MAX_CIPHERTEXT
MIN_CIPHERTEXT = 4 + 1 + 1 + 16


class SealedError(recovery.RecoveryError):
    """Safe error text, without user paths, content, or key material."""


class SealedDependencyError(SealedError):
    """The optional cryptography dependency is unavailable."""


def _crypto():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError:
        raise SealedDependencyError('Optional cryptography dependency is unavailable') from None
    return AESGCM, Scrypt


def check_support():
    """Check optional dependencies before a CLI prompts for a secret."""
    _crypto()


def _phrase(value):
    if type(value) is not bytes or not 1 <= len(value) <= 1024:
        raise SealedError('Passphrase must be UTF-8 bytes, 12 characters minimum and 1024 bytes maximum')
    try: length = len(value.decode('utf-8'))
    except UnicodeError: length = 0
    if length < 12:
        raise SealedError('Passphrase must be UTF-8 bytes, 12 characters minimum and 1024 bytes maximum')


def _derive_key(passphrase, salt):
    _, Scrypt = _crypto()
    return Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(passphrase)


def _local_path(value):
    raw = os.fspath(value)
    if not isinstance(raw, str) or raw.startswith(('//', '\\\\')) or (os.name == 'posix' and '\\' in raw):
        raise SealedError('Unsafe local sealed backup path')
    return recovery._path(value)


def _separate(destination, source):
    if destination == source or source in destination.parents or destination in source.parents:
        raise SealedError('Source and destination must be separate')


def _destination(value, source):
    path = _local_path(value)
    _separate(path, source)
    # Reject early, then still publish/create exclusively to avoid overwrites.
    if path.exists(): raise SealedError('Destination already exists')
    recovery._private(path.parent, directory=True)
    return path


def _read_file(path, maximum):
    """Bound the actual descriptor, not only a preceding path stat."""
    recovery._private(path, maximum=maximum)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 1 <= info.st_size <= maximum
                or (os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077))):
            raise SealedError('Unsafe sealed backup input')
        data = stream.read(maximum + 1)
        if len(data) != info.st_size or len(data) > maximum:
            raise SealedError('Invalid sealed backup size')
    return data


def _manifest(raw):
    if not 1 <= len(raw) <= recovery.MANIFEST_LIMIT: raise SealedError('Invalid manifest')
    data = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    if (type(data) is not dict or set(data) != recovery.FIELDS
            or type(data['format_version']) is not int or data['format_version'] != recovery.FORMAT_VERSION
            or data['encrypted'] is not False or data['authenticated'] is not False
            or type(data['ledger_count']) is not int or not 0 <= data['ledger_count'] <= MAX_LEDGER_ROWS
            or type(data['run_count']) is not int or not 0 <= data['run_count'] <= LIMIT
            or type(data['created_at']) is not str or len(data['created_at']) > 64):
        raise SealedError('Invalid manifest')
    if dt.datetime.fromisoformat(data['created_at']).tzinfo is None: raise SealedError('Invalid manifest')
    for name in ('database_sha256', 'ledger_head'):
        digest = data[name]
        if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise SealedError('Invalid manifest')
    if raw != canonical(data).encode('utf-8'): raise SealedError('Noncanonical manifest')
    return data


def _validate_checksum(data, manifest):
    """Validate bounded bytes only; this does not parse SQLite or its ledger."""
    if not 1 <= len(data) <= MAX_DATABASE_BYTES or hashlib.sha256(data).hexdigest() != manifest['database_sha256']:
        raise SealedError('Invalid database checksum')


def _summary(manifest, verification):
    return {**manifest, 'sealed_format_version': VERSION, 'encrypted': True,
            'integrity_protected': True, 'signer_authenticated': False,
            'verification': verification,
            'database_verified': verification != 'AUTHENTICATED_ENVELOPE'}


def _decrypt(source_file, passphrase):
    check_support()
    _phrase(passphrase)
    source = _local_path(source_file)
    recovery._private(source.parent, directory=True)
    raw = _read_file(source, MAX_SEALED_BYTES)
    if len(raw) < HEADER.size: raise SealedError('Invalid sealed header')
    header = raw[:HEADER.size]
    magic, version, salt, nonce, length = HEADER.unpack(header)
    if (magic != MAGIC or version != VERSION or not MIN_CIPHERTEXT <= length <= MAX_CIPHERTEXT
            or len(raw) != HEADER.size + length):
        raise SealedError('Invalid sealed header')
    AESGCM, _ = _crypto()
    payload = AESGCM(_derive_key(passphrase, salt)).decrypt(nonce, raw[HEADER.size:], header)
    if len(payload) < 4: raise SealedError('Invalid sealed payload')
    length = MANIFEST_LENGTH.unpack(payload[:4])[0]
    if not 1 <= length <= recovery.MANIFEST_LIMIT or len(payload) <= 4 + length:
        raise SealedError('Invalid sealed payload')
    manifest = _manifest(payload[4:4 + length])
    database = payload[4 + length:]
    _validate_checksum(database, manifest)
    return source, manifest, database


def _write_exact(stream, data):
    if stream.write(data) != len(data):
        raise SealedError('Incomplete write')


def _publish(destination, header, ciphertext):
    """Publish a complete fsynced inode with atomic, non-overwriting link."""
    fd, name = tempfile.mkstemp(prefix='.sealed-', dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            _write_exact(stream, header)
            _write_exact(stream, ciphertext)
            stream.flush(); os.fsync(stream.fileno())
        # os.link fails if destination exists, unlike replace/rename on POSIX.
        os.link(temporary, destination, follow_symlinks=False)
    finally:
        # This is our ciphertext-only staging file, never a supplied user file.
        temporary.unlink()
    recovery._sync_directory(destination.parent)


def seal_backup(source_bundle, destination_file, passphrase):
    """Seal an already validated plaintext bundle, preserving both originals."""
    try:
        _phrase(passphrase)
        check_support()
        AESGCM, _ = _crypto()
        source = _local_path(source_bundle)
        target = _destination(destination_file, source)
        source, manifest, _ = recovery._inspect(source)
        database = _read_file(source / recovery.DATABASE, MAX_DATABASE_BYTES)
        # Check the bytes actually encrypted, even if source changed after inspect.
        _validate_checksum(database, manifest)
        raw_manifest = canonical(manifest).encode('utf-8')
        if len(raw_manifest) > recovery.MANIFEST_LIMIT: raise SealedError('Invalid manifest size')
        payload = MANIFEST_LENGTH.pack(len(raw_manifest)) + raw_manifest + database
        salt, nonce = os.urandom(16), os.urandom(12)
        header = HEADER.pack(MAGIC, VERSION, salt, nonce, len(payload) + 16)
        ciphertext = AESGCM(_derive_key(passphrase, salt)).encrypt(nonce, payload, header)
        _publish(target, header, ciphertext)
        return _summary(manifest, 'SOURCE_DATABASE_VERIFIED')
    except SealedDependencyError: raise
    except Exception:
        raise SealedError('Sealed backup creation failed') from None


def inspect_sealed(source_file, passphrase):
    """Authenticate envelope, canonical manifest and checksum without disk writes.

    This deliberately does not parse SQLite or validate schema/ledger semantics.
    A passphrase holder can forge an envelope containing an invalid database.
    """
    try:
        _, manifest, _ = _decrypt(source_file, passphrase)
        return _summary(manifest, 'AUTHENTICATED_ENVELOPE')
    except SealedDependencyError: raise
    except Exception:
        raise SealedError('Sealed backup validation failed') from None


def restore_sealed(source_file, destination_dir, passphrase):
    """Authenticate first, then validate a new private plaintext workspace.

    Wrong passwords/tampering create no output. A failure after plaintext output
    starts, including an authenticated invalid SQLite schema or ledger, retains
    that new folder and incomplete marker; no secure erase claim.
    """
    try:
        source = _local_path(source_file)
        target = _destination(destination_dir, source)
        _, manifest, database = _decrypt(source, passphrase)
        target = recovery._new_destination(target, source)
        with recovery._create_file(target / recovery.INCOMPLETE) as marker:
            _write_exact(marker, b'Incomplete sealed recovery; do not use as workspace.\n')
            marker.flush(); os.fsync(marker.fileno())
        recovery._sync_directory(target)
        with recovery._create_file(target / recovery.DATABASE) as stream:
            _write_exact(stream, database)
            stream.flush(); os.fsync(stream.fileno())
        if recovery._checksum(target / recovery.DATABASE) != manifest['database_sha256']:
            raise SealedError('Restored checksum mismatch')
        runs, head, count = recovery._validated_database(target / recovery.DATABASE)
        if (head, count, len(runs)) != (manifest['ledger_head'], manifest['ledger_count'], manifest['run_count']):
            raise SealedError('Restored evidence mismatch')
        (target / recovery.INCOMPLETE).unlink()
        recovery._sync_directory(target)
        return _summary(manifest, 'RESTORED_DATABASE_VERIFIED')
    except SealedDependencyError: raise
    except Exception:
        raise SealedError('Sealed backup validation failed') from None
