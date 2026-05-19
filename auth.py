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
    role: str = "user"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


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


def create_user(username: str, password: str, role: str = "user") -> User:
    username = username.strip()
    role = role.strip() if role.strip() in {"user", "admin"} else "user"
    if not username:
        raise AuthError("Informe um nome de usuário.")
    if len(password) < 8:
        raise AuthError("A senha precisa ter pelo menos 8 caracteres.")
    with connect() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (username, hash_password(password), role, now_text()),
            )
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise AuthError("Esse nome de usuário já está em uso.") from exc
            raise
    return User(id=int(cursor.lastrowid), username=username, role=role)


def authenticate(username: str, password: str) -> User | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        data = row_to_dict(row)
        if not data or not verify_password(password, data["password_hash"]):
            return None
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now_text(), data["id"]))
    return User(id=int(data["id"]), username=str(data["username"]), role=str(data.get("role") or "user"))


def list_users() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, username, role, created_at, last_login_at FROM users ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def set_user_role(user_id: int, role: str) -> None:
    role = role.strip() if role.strip() in {"user", "admin"} else "user"
    with connect() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
