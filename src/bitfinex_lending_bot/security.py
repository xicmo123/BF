from __future__ import annotations

from cryptography.fernet import Fernet


def _derive_fernet_key(raw_key: str) -> bytes:
    """
    Derive a valid 32-byte Fernet key from an arbitrary-length string.
    If the key is already a valid Fernet key (44 base64 bytes), use it directly.
    Otherwise, hash it to produce a deterministic 32-byte key and base64-encode it.
    """
    key = raw_key.strip()
    # Attempt to use as-is if it's a valid Fernet key
    try:
        Fernet(key.encode())
        return key.encode()
    except Exception:
        pass

    # Derive a 32-byte key via SHA-256 and base64-encode it (Fernet requires this format)
    import hashlib
    import base64

    digest = hashlib.sha256(key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(secret: str, key: str) -> str:
    """
    Encrypt a secret (e.g. API secret) using Fernet symmetric encryption.
    Returns a base64-encoded ciphertext string.
    """
    if not key:
        raise ValueError("encryption key must not be empty")
    if not secret:
        raise ValueError("secret must not be empty")
    fernet_key = _derive_fernet_key(key)
    f = Fernet(fernet_key)
    encrypted = f.encrypt(secret.encode())
    return encrypted.decode()


def decrypt_secret(encrypted: str, key: str) -> str:
    """
    Decrypt a previously encrypted secret.
    Takes the base64-encoded ciphertext and returns the original plaintext.
    """
    if not key:
        raise ValueError("encryption key must not be empty")
    if not encrypted:
        raise ValueError("encrypted value must not be empty")
    fernet_key = _derive_fernet_key(key)
    f = Fernet(fernet_key)
    decrypted = f.decrypt(encrypted.encode())
    return decrypted.decode()