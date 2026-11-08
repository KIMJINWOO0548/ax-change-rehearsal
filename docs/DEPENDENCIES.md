# Optional encryption dependencies

Verified against official registry/vendor sources on **2026-11-08 UTC**. This is an optional encryption environment, not a new requirement for the standard-library-only application. Import optional cryptographic components only when encrypted backup/restore is requested; fail clearly if unavailable. Never silently substitute a homemade cipher or an unencrypted backup.

## Reproducible installation

Use a dedicated virtual environment, then run:

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements-encryption.txt
python -m pip check
```

The lock explicitly selects the official PyPI index, pins the complete runtime dependency closure, requires SHA-256 hashes, and prohibits source builds. Each hash was copied from the official versioned PyPI JSON `urls[].digests.sha256` field for a non-yanked wheel. All release wheels are included so the same lock can resolve different supported platforms; source tarball hashes are deliberately excluded. A hash verifies artifact integrity against the reviewed lock, not publisher trust or absence of malicious code. Do not disable these controls to resolve an installation failure. Organizations may mirror these exact approved artifacts into their own controlled package repository.

## Reviewed package inventory

| Package | Locked version | Metadata Python requirement | License expression | Purpose |
| --- | --- | --- | --- | --- |
| cryptography | 50.0.2 | >=3.9, excluding 3.9.0/3.9.1 | Apache-2.0 OR BSD-3-Clause | AES-GCM and Scrypt |
| cffi | 2.1.1 | >=3.10 | MIT-0 | cryptography dependency except PyPy |
| pycparser | 3.0 | >=3.10 | BSD-3-Clause | cffi dependency except PyPy |
| typing-extensions | 4.16.0 | >=3.9 | PSF-2.0 | cryptography dependency on Python <3.11 |

`cryptography` requires cffi >=2.0.0 outside PyPy and typing-extensions >=4.13.2 below Python 3.11. No optional SSH/bcrypt extra is installed. pycparser 3.0 is deliberately retained for Python 3.10 compatibility; the newest release observed (3.12) requires Python >=3.11. All other pins were the latest stable PyPI versions observed at review time. These third-party licenses do not change the original project's license. Preserve upstream notices when redistributing installed binaries; cryptography wheels include bundled native dependencies and their license notices, so this table is not a complete binary-distribution notice inventory. No wheels are vendored in this repository.

Versioned registry evidence, including hashes, dependency markers, licenses, upload dates, and wheel filenames:

- https://pypi.org/pypi/cryptography/50.0.2/json
- https://pypi.org/pypi/cffi/2.1.1/json
- https://pypi.org/pypi/pycparser/3.0/json
- https://pypi.org/pypi/typing-extensions/4.16.0/json

Upstream source and documentation:

- https://github.com/pyca/cryptography/tree/50.0.2
- https://cryptography.io/en/latest/changelog/
- https://github.com/python-cffi/cffi
- https://github.com/eliben/pycparser
- https://github.com/python/typing_extensions

## Compatibility and verification limits

The dependency-resolution matrix is **64-bit x86 CPython 3.10, 3.11, 3.12, and 3.13 on Ubuntu and Windows**. The standard-library core retains Python 3.10 compatibility; the sealed backup feature additionally requires the locked optional cryptographic packages. Dependency resolution alone does not establish feature availability. Dependency verification performed for this review:

- Download-only pip resolution with hash verification succeeded for all eight Python/platform combinations (Windows `win_amd64`; Linux compatible `manylinux_2_28_x86_64`, `manylinux_2_17_x86_64`, and `manylinux2014_x86_64` tags). Stable-ABI cryptography wheels cover the relevant Python versions; cffi supplies interpreter-specific wheels.
- A first Linux cross-download using only the explicit 2.28 tag failed to find cffi. Including the older compatible manylinux tags resolved it. This was a cross-download tag configuration issue, not a need for source compilation.
- Cross-download environment markers are evaluated by pip on the running interpreter. The Python 3.10-only typing-extensions wheel was therefore independently downloaded from its official PyPI URL and its SHA-256 verified against the lock metadata. Native Python 3.10 CI must still verify the marker-resolved full install.
- A clean isolated Linux CPython 3.12 virtual environment installed the lock successfully and executed Scrypt-derived 256-bit-key AES-GCM encrypt/decrypt smoke testing. The installed backend reported OpenSSL 4.0.3 (29 Sep 2026), matching the vendor's 50.0.2 wheel changelog.
- Download resolution does **not** prove execution on Windows or all Python versions. Actual per-platform CI and the application's backup corruption/wrong-password/restore tests remain release gates. Other architectures, PyPy, free-threaded builds, macOS, and older operating systems are not claimed as application-supported merely because their wheel hashes appear in this lock.

## Cryptographic API boundary

Use `cryptography.hazmat.primitives.ciphers.aead.AESGCM` with a 32-byte key for AES-256-GCM, and `cryptography.hazmat.primitives.kdf.scrypt.Scrypt` for password derivation. The format profile uses Scrypt N=2^17, r=8, p=1, a 32-byte derived key, a 16-byte salt, and a 12-byte AES-GCM nonce. The backup format contract and implementation own the authenticated metadata, resource limits, and exact serialization. Do not accept unbounded KDF work factors from an untrusted file. A fresh salt and unique nonce must be generated for each encryption; authenticate format metadata and reject authentication failures before restoration. The dependency smoke test is not a security review or validation of the application's format.

- https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM
- https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#scrypt

## Security advisory snapshot and maintenance

On **2026-11-08 UTC**, queries to `https://api.osv.dev/v1/query` for each exact package/version above returned `{}` (no matching published advisory), and the four official PyPI version JSON responses each contained an empty `vulnerabilities` list. Also reviewed the vendor advisory index and changelog:

- https://github.com/pyca/cryptography/security/advisories
- https://cryptography.io/en/latest/changelog/
- https://google.github.io/osv.dev/api/#tag/api/operation/OSV_QueryAffected

The vendor records a PKCS#7 issue fixed in 50.0.0 (CVE-2026-69247); the selected pin is newer. The 50.0.2 changelog records updated bundled OpenSSL wheels. These checks are a dated snapshot, **not a guarantee of safety, a comprehensive native-component audit, FIPS validation, or enterprise certification**. Recheck advisories and bundled OpenSSL before deployment and regularly afterward. Refresh pins and official hashes deliberately, repeat native matrix tests, and review license notices whenever dependencies change. Do not automatically float production versions.
