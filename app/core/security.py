"""
app/core/security.py
Utilidades de seguridad: hashing, JWT, TOTP (2FA).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import secrets
import base64

from jose import JWTError, jwt
from passlib.context import CryptContext
import pyotp

from app.core.config import settings

# ── Hashing ────────────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hashea una contraseña con bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica una contraseña contra su hash."""
    return pwd_context.verify(plain, hashed)


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Valida que la contraseña cumpla requisitos mínimos.
    Retorna (válida, mensaje).
    """
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"
    if not any(c.isupper() for c in password):
        return False, "Debe contener al menos una mayúscula"
    if not any(c.isdigit() for c in password):
        return False, "Debe contener al menos un número"
    return True, "OK"


# ── JWT ────────────────────────────────────────────────────────────────────────
def create_access_token(data: Dict[str, Any]) -> str:
    """Crea un JWT de acceso de corta duración."""
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload.update({"exp": expire, "type": "access"})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Crea un JWT de refresco de larga duración."""
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload.update({"exp": expire, "type": "refresh"})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodifica y valida un JWT.
    Retorna el payload o None si es inválido/expirado.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        return None


# ── TOTP (2FA) ─────────────────────────────────────────────────────────────────
def generate_totp_secret() -> str:
    """Genera un secreto TOTP aleatorio y seguro."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str) -> str:
    """Genera el URI para el QR code de Google Authenticator / Authy."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(
        name=username,
        issuer_name=settings.TOTP_ISSUER
    )


def verify_totp(secret: str, code: str) -> bool:
    """
    Verifica un código TOTP.
    Acepta ±1 ventana de tiempo (30s) para tolerancia de reloj.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


# ── Tokens de un solo uso ──────────────────────────────────────────────────────
def generate_secure_token(length: int = 32) -> str:
    """Genera un token seguro para recuperación de contraseña, etc."""
    return secrets.token_urlsafe(length)
