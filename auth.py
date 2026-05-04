from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from database import connect, now_text, row_to_dict


PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 390_000
SALT_BYTES = 16


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class User:
    id: int
    username: str


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = stored_hash.split("$", 3)
        if algorithm != PBKDF2_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = _unb64(salt_text)
        expected = _unb64(digest_text)
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def user_count() -> int:
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()
    return int(row["total"])


def create_user(username: str, password: str) -> User:
    username = username.strip()
    if not username:
        raise AuthError("Informe um usuário.")
    if len(password) < 8:
        raise AuthError("A senha precisa ter pelo menos 8 caracteres.")

    with connect() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO users (username, password_hash, created_at)
                VALUES (?, ?, ?)
                """,
                (username, hash_password(password), now_text()),
            )
        except Exception as exc:
            message = str(exc).lower()
            if "unique" in message:
                raise AuthError("Já existe um usuário com esse nome.") from exc
            raise

    return User(id=int(cursor.lastrowid), username=username)


def authenticate(username: str, password: str) -> User | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()

        data = row_to_dict(row)
        if not data or not verify_password(password, data["password_hash"]):
            return None

        conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (now_text(), data["id"]),
        )

    return User(id=int(data["id"]), username=str(data["username"]))
