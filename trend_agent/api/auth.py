"""
认证鉴权模块

支持:
  1. JWT Bearer Token
  2. API Key
  3. 开发模式跳过认证
"""

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
import threading
import base64
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from trend_agent.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class AuthContext:
    """请求认证上下文"""
    tenant_id: str
    auth_method: str    # "api_key" | "jwt" | "dev_bypass"
    role: str = "user"
    user_id: str = ""


class JWTValidator:
    """JWT 验证器 (HMAC-SHA256)"""

    def __init__(self, secret: str = ""):
        self._secret = (secret or settings.auth.jwt_secret).encode()

    def issue(self, payload: Dict, expires_in_seconds: int = 86400) -> str:
        now = int(time.time())
        body = dict(payload or {})
        body.setdefault("iat", now)
        body["exp"] = now + max(1, int(expires_in_seconds))

        header_b64 = self._b64url_encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
        )
        payload_b64 = self._b64url_encode(
            json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        )
        signing_input = f"{header_b64}.{payload_b64}".encode()
        sig = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        sig_b64 = self._b64url_encode(sig)
        return f"{header_b64}.{payload_b64}.{sig_b64}"

    def validate(self, token: str) -> Optional[Dict]:
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            signing_input = f"{parts[0]}.{parts[1]}".encode()
            expected_sig = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
            actual_sig = self._b64url_decode(parts[2])
            if not hmac.compare_digest(expected_sig, actual_sig):
                return None
            payload = json.loads(self._b64url_decode(parts[1]))
            if payload.get("exp", 0) < time.time():
                return None
            return payload
        except Exception as e:
            logger.warning("JWT validation failed: %s", e)
            return None

    def _b64url_encode(self, value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    def _b64url_decode(self, value: str) -> bytes:
        padding = "=" * ((4 - len(value) % 4) % 4)
        return base64.urlsafe_b64decode(value + padding)


class UserAuthStore:
    """本地用户存储 (SQLite)"""

    def __init__(self, db_path: str = ""):
        self._db_path = db_path or os.getenv("AUTH_DB_PATH", "trend_auth_users.db")
        self._lock = threading.Lock()
        self._ready = False

    def register_user(self, username: str, password: str, tenant_id: str = "default", role: str = "user") -> Tuple[bool, str]:
        uname = (username or "").strip()
        if len(uname) < 3:
            return False, "Username must be at least 3 characters"
        if len(password or "") < 6:
            return False, "Password must be at least 6 characters"
        self._ensure_schema()
        pwd_hash, salt = self._hash_password(password)
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO auth_users (username, password_hash, password_salt, tenant_id, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (uname, pwd_hash, salt, tenant_id, role, int(time.time())),
                )
                conn.commit()
            return True, "ok"
        except sqlite3.IntegrityError:
            return False, "Username already exists"

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, str]]:
        uname = (username or "").strip()
        if not uname or not password:
            return None
        self._ensure_schema()
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT username, password_hash, password_salt, tenant_id, role FROM auth_users WHERE username = ? LIMIT 1",
                    (uname,),
                ).fetchone()
        except Exception as exc:
            logger.error("authenticate user failed: %s", exc)
            return None
        if row is None:
            return None
        expected_hash = str(row["password_hash"] or "")
        actual_hash, _ = self._hash_password(password, str(row["password_salt"] or ""))
        if not hmac.compare_digest(expected_hash, actual_hash):
            return None
        return {
            "username": str(row["username"]),
            "tenant_id": str(row["tenant_id"] or "default"),
            "role": str(row["role"] or "user"),
        }

    def _ensure_schema(self):
        with self._lock:
            if self._ready:
                return
            with self._connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS auth_users (
                        username TEXT PRIMARY KEY,
                        password_hash TEXT NOT NULL,
                        password_salt TEXT NOT NULL,
                        tenant_id TEXT NOT NULL DEFAULT 'default',
                        role TEXT NOT NULL DEFAULT 'user',
                        created_at INTEGER NOT NULL
                    )
                """)
                conn.commit()
            self._ready = True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _hash_password(self, password: str, salt_hex: str = "") -> Tuple[str, str]:
        salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", (password or "").encode(), salt, 150000)
        return digest.hex(), salt.hex()


# Global singletons
_jwt_validator = JWTValidator()
_user_store = UserAuthStore()
_bearer_scheme = HTTPBearer(auto_error=False)


def register_user(username: str, password: str, tenant_id: str = "default", role: str = "user") -> Tuple[bool, str]:
    return _user_store.register_user(username, password, tenant_id, role)


def authenticate_user(username: str, password: str) -> Optional[Dict[str, str]]:
    return _user_store.authenticate_user(username, password)


def issue_access_token(username: str, tenant_id: str, role: str, expires_in_seconds: int = 86400) -> str:
    return _jwt_validator.issue(
        {"sub": username, "tenant_id": tenant_id, "role": role},
        expires_in_seconds=expires_in_seconds,
    )


async def get_auth_context(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> AuthContext:
    """认证依赖 - 从请求中提取认证信息"""
    # JWT Bearer
    if credentials:
        payload = _jwt_validator.validate(credentials.credentials)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return AuthContext(
            tenant_id=payload.get("tenant_id", "default"),
            auth_method="jwt",
            role=payload.get("role", "user"),
            user_id=payload.get("sub", ""),
        )

    # API Key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        # Simple API key validation (in production, check against DB)
        if len(api_key) < 8:
            raise HTTPException(status_code=401, detail="Invalid API Key")
        return AuthContext(
            tenant_id=request.headers.get("X-Tenant-Id", "default"),
            auth_method="api_key",
            role="service",
            user_id=f"api_key:{api_key[:8]}",
        )

    # Dev bypass
    if settings.env == "development":
        return AuthContext(
            tenant_id="default",
            auth_method="dev_bypass",
            role="admin",
            user_id="dev_user",
        )

    raise HTTPException(
        status_code=401,
        detail="Authentication required. Use Authorization: Bearer <token> or X-API-Key header.",
    )
