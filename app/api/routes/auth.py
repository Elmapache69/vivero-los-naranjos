"""
app/api/routes/auth.py
Autenticación: login, refresh, 2FA setup/verify, cambio de contraseña.
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_client_ip, log_audit, get_db
from app.core.security import (
    verify_password, hash_password, validate_password_strength,
    create_access_token, create_refresh_token, decode_token,
    generate_totp_secret, get_totp_uri, verify_totp,
)
from app.db.models import Usuario, RolEnum
from app.schemas import (
    LoginRequest, LoginResponse, RefreshRequest, TokenResponse,
    Setup2FAResponse, Verify2FARequest, ChangePasswordRequest, UsuarioPublico,
)

router = APIRouter(prefix="/auth", tags=["Autenticación"])

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Login con username + password.
    Si el usuario tiene 2FA activo, se requiere totp_code.
    Bloquea la cuenta tras 5 intentos fallidos.
    """
    ip = get_client_ip(request)
    user: Usuario | None = db.query(Usuario).filter(
        Usuario.username == body.username.lower(),
        Usuario.is_active == True
    ).first()

    # ── Cuenta bloqueada ────────────────────────────────────────────────────
    if user and user.locked_until and user.locked_until > datetime.now(timezone.utc):
        remaining = int((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60)
        log_audit(db, user.id, "LOGIN_BLOQUEADO", ip_address=ip)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Cuenta bloqueada. Intenta en {remaining} minutos."
        )

    # ── Verificar credenciales ──────────────────────────────────────────────
    if not user or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
                log_audit(db, user.id, "CUENTA_BLOQUEADA",
                          detalle=f"Bloqueada por {MAX_LOGIN_ATTEMPTS} intentos fallidos", ip_address=ip)
            log_audit(db, user.id, "LOGIN_FALLIDO", ip_address=ip)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos"
        )

    # ── Verificar 2FA si está activado ──────────────────────────────────────
    if user.totp_enabled and user.totp_verified:
        if not body.totp_code:
            # Login parcial — frontend debe pedir el código TOTP
            return LoginResponse(
                access_token="",
                refresh_token="",
                requires_2fa=True,
                user=UsuarioPublico.model_validate(user)
            )
        if not verify_totp(user.totp_secret, body.totp_code):
            log_audit(db, user.id, "2FA_FALLIDO", ip_address=ip)
            db.commit()
            raise HTTPException(status_code=401, detail="Código 2FA inválido")

    # ── Login exitoso ───────────────────────────────────────────────────────
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)

    token_data = {"sub": str(user.id), "rol": user.rol.value}
    access_token  = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    log_audit(db, user.id, "LOGIN_EXITOSO", ip_address=ip)
    db.commit()

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        requires_2fa=False,
        user=UsuarioPublico.model_validate(user)
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    """Obtiene un nuevo access token usando el refresh token."""
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token inválido")

    user = db.query(Usuario).filter(
        Usuario.id == int(payload["sub"]),
        Usuario.is_active == True
    ).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    token_data = {"sub": str(user.id), "rol": user.rol.value}
    return TokenResponse(access_token=create_access_token(token_data))


@router.post("/2fa/setup", response_model=Setup2FAResponse)
def setup_2fa(
    request: Request,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Genera el secreto TOTP y el URI para el QR code."""
    secret = generate_totp_secret()
    current_user.totp_secret = secret
    current_user.totp_enabled = True
    current_user.totp_verified = False  # Requiere verificación

    log_audit(db, current_user.id, "2FA_SETUP_INICIADO", ip_address=get_client_ip(request))
    db.commit()

    return Setup2FAResponse(
        secret=secret,
        uri=get_totp_uri(secret, current_user.username),
        message="Escanea el QR con Google Authenticator o Authy, luego verifica con /2fa/verify"
    )


@router.post("/2fa/verify")
def verify_2fa(
    body: Verify2FARequest,
    request: Request,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verifica el código TOTP para activar 2FA definitivamente."""
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="Primero configura 2FA con /2fa/setup")
    if not verify_totp(current_user.totp_secret, body.code):
        raise HTTPException(status_code=400, detail="Código inválido")

    current_user.totp_verified = True
    log_audit(db, current_user.id, "2FA_ACTIVADO", ip_address=get_client_ip(request))
    db.commit()
    return {"message": "2FA activado correctamente"}


@router.delete("/2fa/disable")
def disable_2fa(
    request: Request,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Desactiva 2FA para el usuario actual (solo admins pueden hacerlo para otros)."""
    current_user.totp_enabled = False
    current_user.totp_verified = False
    current_user.totp_secret = None
    log_audit(db, current_user.id, "2FA_DESACTIVADO", ip_address=get_client_ip(request))
    db.commit()
    return {"message": "2FA desactivado"}


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cambio de contraseña autenticado."""
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")

    valid, msg = validate_password_strength(body.new_password)
    if not valid:
        raise HTTPException(status_code=422, detail=msg)

    current_user.password_hash = hash_password(body.new_password)
    current_user.password_changed_at = datetime.now(timezone.utc)

    log_audit(db, current_user.id, "PASSWORD_CAMBIADO", ip_address=get_client_ip(request))
    db.commit()
    return {"message": "Contraseña actualizada correctamente"}


@router.get("/me", response_model=UsuarioPublico)
def get_me(current_user: Usuario = Depends(get_current_user)):
    """Retorna los datos del usuario autenticado."""
    return current_user
