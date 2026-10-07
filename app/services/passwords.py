"""Argon2id password hashing and password-policy checks."""

from functools import lru_cache
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Library defaults are Argon2id with OWASP-recommended parameters (SPEC §11).
_hasher = PasswordHasher()

COMMON_PASSWORDS_FILE = Path(__file__).resolve().parents[2] / "data" / "common_passwords.txt"
MAX_PASSWORD_LENGTH = 128

# Verified against when the email is unknown, so a login for a non-existent
# account takes as long as one for a real account (no timing-based enumeration).
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")


def hash_password(password):
    return _hasher.hash(password)


def verify_password(password_hash, password):
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def burn_verify_time(password):
    verify_password(_DUMMY_HASH, password)


def needs_rehash(password_hash):
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


@lru_cache(maxsize=1)
def _common_passwords():
    lines = COMMON_PASSWORDS_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip().lower() for line in lines if line and not line.startswith("#"))


def password_problems(password, email, min_length):
    """Return a list of human-readable reasons the password is unacceptable."""
    problems = []
    if len(password) < min_length:
        problems.append(f"Use at least {min_length} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(f"Use at most {MAX_PASSWORD_LENGTH} characters.")
    if password.lower() in _common_passwords():
        problems.append("That password is too common. Choose something less guessable.")
    if email and password.lower() == email.lower():
        problems.append("Your password must not be your email address.")
    return problems
