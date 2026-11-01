"""Host-side authentication, sessions, RBAC, and login throttling."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.database.repository import Repository
from app.schemas.models import new_id
from app.security.audit_logger import AuditLogger


class Role(StrEnum):
    VIEWER = "viewer"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class Permission(StrEnum):
    READ = "read"
    CREATE_PROJECT = "create_project"
    DELETE_PROJECT = "delete_project"
    APPROVE = "approve"
    OPERATE = "operate"
    ADMIN = "admin"


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    username: str
    role: Role


class AuthSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    user: AuthenticatedUser
    token: str
    csrf_token: str
    expires_at: datetime


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.READ}),
    Role.DEVELOPER: frozenset({Permission.READ, Permission.CREATE_PROJECT, Permission.DELETE_PROJECT, Permission.OPERATE}),
    Role.REVIEWER: frozenset({Permission.READ, Permission.APPROVE}),
    Role.ADMIN: frozenset(Permission),
}


def _password_hash(password: str, salt: bytes | None = None) -> str:
    if not 12 <= len(password) <= 256:
        raise ValueError("password must be between 12 and 256 characters")
    actual_salt = salt or os.urandom(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=actual_salt, n=2**14, r=8, p=1)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(actual_salt).decode() + "$" + base64.urlsafe_b64encode(derived).decode()


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_text, digest_text = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


class RateLimiter:
    def __init__(self, limit: int = 60, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] >= self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


class AuthenticationError(PermissionError):
    pass


class AuthorizationDenied(AuthenticationError):
    pass


class AuthService:
    def __init__(self, repository: Repository, audit: AuditLogger, session_ttl_seconds: int = 3600) -> None:
        self.repository = repository
        self.audit = audit
        self.session_ttl_seconds = session_ttl_seconds
        self.rate_limiter = RateLimiter()
        self.login_limiter = RateLimiter(limit=10, window_seconds=300)

    def create_user(self, username: str, password: str, role: Role) -> AuthenticatedUser:
        normalized = username.strip().lower()
        if not 3 <= len(normalized) <= 120 or any(char.isspace() for char in normalized):
            raise ValueError("username must be 3-120 non-space characters")
        user = AuthenticatedUser(user_id=new_id("USER"), username=normalized, role=role)
        self.repository.create_user(user.user_id, user.username, _password_hash(password), role.value)
        self.audit.record("USER_CREATED", actor_id=user.user_id, payload={"username": normalized, "role": role.value})
        return user

    def login(self, username: str, password: str, client_key: str) -> AuthSession:
        if not self.login_limiter.allow(client_key):
            raise AuthenticationError("login rate limit exceeded")
        record = self.repository.get_user_by_username(username.strip().lower())
        if record is None or not record["is_active"] or not _verify_password(password, record["password_hash"]):
            self.audit.record("LOGIN_FAILED", actor_id=username.strip().lower()[:120], payload={"client": client_key[:80]})
            raise AuthenticationError("invalid credentials")
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        expires = datetime.now(UTC) + timedelta(seconds=self.session_ttl_seconds)
        session_id = new_id("SESSION")
        self.repository.create_session(
            session_id, hashlib.sha256(token.encode()).hexdigest(), record["user_id"],
            hashlib.sha256(csrf_token.encode()).hexdigest(), expires.isoformat(),
        )
        user = AuthenticatedUser(user_id=record["user_id"], username=record["username"], role=record["role"])
        self.audit.record("LOGIN_SUCCEEDED", actor_id=user.user_id, payload={"role": user.role.value})
        return AuthSession(
            session_id=session_id,
            user=user, token=token, csrf_token=csrf_token, expires_at=expires,
        )

    def authenticate(self, token: str | None) -> tuple[AuthenticatedUser, str]:
        if not token or not self.rate_limiter.allow(hashlib.sha256(token.encode()).hexdigest()[:24]):
            raise AuthenticationError("authentication required")
        record = self.repository.get_session(hashlib.sha256(token.encode()).hexdigest())
        if record is None or not record["is_active"]:
            raise AuthenticationError("authentication required")
        if datetime.fromisoformat(record["expires_at"]) <= datetime.now(UTC):
            self.repository.delete_session(record["token_hash"])
            raise AuthenticationError("session expired")
        self.repository.touch_session(record["session_id"])
        return AuthenticatedUser(user_id=record["user_id"], username=record["username"], role=record["role"]), record["session_id"]

    def require(self, token: str | None, permission: Permission) -> tuple[AuthenticatedUser, str]:
        user, session_id = self.authenticate(token)
        if permission not in ROLE_PERMISSIONS[user.role]:
            self.audit.record("AUTHORIZATION_DENIED", actor_id=user.user_id, payload={"permission": permission.value})
            raise AuthorizationDenied("insufficient permission")
        return user, session_id

    def require_csrf(self, session_id: str, csrf_token: str | None) -> None:
        if not csrf_token:
            raise AuthenticationError("CSRF token required")
        record = self.repository.get_session_by_id(session_id)
        if record is None or not hmac.compare_digest(
            record["csrf_hash"], hashlib.sha256(csrf_token.encode()).hexdigest()
        ):
            raise AuthenticationError("invalid CSRF token")

    def rotate_csrf(self, session_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self.repository.update_session_csrf(session_id, hashlib.sha256(token.encode()).hexdigest())
        return token

    def logout(self, token: str | None) -> None:
        if token:
            self.repository.delete_session(hashlib.sha256(token.encode()).hexdigest())
