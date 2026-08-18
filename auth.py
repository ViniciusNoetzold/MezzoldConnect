from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass

from database import connect, now_text, row_to_dict


PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 390_000
SALT_BYTES = 16
ROLE_CLIENTE = "cliente"
ROLE_EQUIPE = "equipe"
ROLE_ADMIN = "admin"
VALID_ROLES = (ROLE_CLIENTE, ROLE_EQUIPE, ROLE_ADMIN)


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: str
    is_active: bool
    must_change_password: bool


def _normalize_role(role: str | None) -> str:
    value = str(role or "").strip().lower()
    if value not in VALID_ROLES:
        return ROLE_CLIENTE
    return value


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


def _user_from_row(row: sqlite3.Row | None) -> User | None:
    data = row_to_dict(row)
    if not data:
        return None
    return User(
        id=int(data["id"]),
        username=str(data["username"]),
        role=_normalize_role(str(data.get("role") or ROLE_CLIENTE)),
        is_active=bool(int(data.get("is_active") or 0)),
        must_change_password=bool(int(data.get("must_change_password") or 0)),
    )


def get_user(user_id: int) -> User | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, username, role, is_active, must_change_password FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
    return _user_from_row(row)


def create_user(
    username: str,
    password: str,
    role: str = ROLE_CLIENTE,
    must_change_password: bool = False,
    is_active: bool = True,
) -> User:
    username = username.strip()
    if not username:
        raise AuthError("Informe um nome de usuário.")
    if len(password) < 8:
        raise AuthError("A senha precisa ter pelo menos 8 caracteres.")

    final_role = _normalize_role(role)
    final_must_change = bool(must_change_password)
    if user_count() == 0 and role == ROLE_CLIENTE and not must_change_password:
        final_role = ROLE_ADMIN
        final_must_change = True

    with connect() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO users (username, password_hash, role, is_active, must_change_password, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    hash_password(password),
                    final_role,
                    1 if is_active else 0,
                    1 if final_must_change else 0,
                    now_text(),
                    now_text(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AuthError("Esse nome de usuário já está em uso.") from exc

    return User(
        id=int(cursor.lastrowid),
        username=username,
        role=final_role,
        is_active=bool(is_active),
        must_change_password=final_must_change,
    )


def create_admin(username: str, password: str) -> User:
    return create_user(username, password, role=ROLE_ADMIN, must_change_password=True, is_active=True)


def authenticate(username: str, password: str) -> User | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash, role, is_active, must_change_password
            FROM users
            WHERE username = ?
            """,
            (username.strip(),),
        ).fetchone()

        data = row_to_dict(row)
        if not data:
            return None
        if not bool(int(data.get("is_active") or 0)):
            return None
        if not verify_password(password, str(data["password_hash"])):
            return None

        conn.execute(
            "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (now_text(), now_text(), int(data["id"])),
        )

    return User(
        id=int(data["id"]),
        username=str(data["username"]),
        role=_normalize_role(str(data.get("role") or ROLE_CLIENTE)),
        is_active=True,
        must_change_password=bool(int(data.get("must_change_password") or 0)),
    )


def change_password(user_id: int, current_password: str, new_password: str) -> None:
    if len(new_password) < 8:
        raise AuthError("A nova senha precisa ter pelo menos 8 caracteres.")
    with connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ? AND is_active = 1",
            (int(user_id),),
        ).fetchone()
        data = row_to_dict(row)
        if not data or not verify_password(current_password, str(data["password_hash"])):
            raise AuthError("Senha atual inválida.")
        conn.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE id = ?",
            (hash_password(new_password), now_text(), int(user_id)),
        )


def reset_user_password(user_id: int, new_password: str, must_change_password: bool = True) -> None:
    if len(new_password) < 8:
        raise AuthError("A nova senha precisa ter pelo menos 8 caracteres.")
    with connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, must_change_password = ?, updated_at = ? WHERE id = ?",
            (hash_password(new_password), 1 if must_change_password else 0, now_text(), int(user_id)),
        )


def set_must_change_password(user_id: int, required: bool) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE users SET must_change_password = ?, updated_at = ? WHERE id = ?",
            (1 if required else 0, now_text(), int(user_id)),
        )


def update_user_role(user_id: int, role: str) -> None:
    normalized = _normalize_role(role)
    with connect() as conn:
        conn.execute(
            "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
            (normalized, now_text(), int(user_id)),
        )


def deactivate_user(user_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?",
            (now_text(), int(user_id)),
        )


def activate_user(user_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE users SET is_active = 1, updated_at = ? WHERE id = ?",
            (now_text(), int(user_id)),
        )


def list_users() -> list[dict[str, object]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, username, role, is_active, must_change_password, created_at, updated_at, last_login_at
            FROM users
            ORDER BY username COLLATE NOCASE
            """
        ).fetchall()
    result: list[dict[str, object]] = []
    for row in rows:
        item = row_to_dict(row) or {}
        result.append(
            {
                "id": int(item.get("id") or 0),
                "username": str(item.get("username") or ""),
                "role": _normalize_role(str(item.get("role") or ROLE_CLIENTE)),
                "is_active": bool(int(item.get("is_active") or 0)),
                "must_change_password": bool(int(item.get("must_change_password") or 0)),
                "created_at": str(item.get("created_at") or ""),
                "updated_at": str(item.get("updated_at") or ""),
                "last_login_at": str(item.get("last_login_at") or ""),
            }
        )
    return result

_current_user = None
_current_role = None

def set_current_user(username, role):
    global _current_user, _current_role
    _current_user = username
    _current_role = role

def get_current_user():
    return _current_user

def get_current_role():
    return _current_role

def verify_login(username, password):
    user = authenticate(username, password)
    if user:
        return True, user.role, user.is_active
    return False, None, False
