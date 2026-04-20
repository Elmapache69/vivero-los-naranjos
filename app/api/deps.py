"""
app/api/deps.py
Dependencias compartidas de FastAPI: autenticación, permisos, auditoría.
"""
from datetime import datetime, timezone
from typing import Optional
from functools import wraps

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.db.models import Usuario, AuditLog, RolEnum

# Esquema de autenticación Bearer
bearer_scheme = HTTPBearer()


# ── Obtener usuario actual ─────────────────────────────────────────────────────
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    """
    Valida el JWT y retorna el usuario autenticado.
    Lanza 401 si el token es inválido o el usuario está inactivo.
    """
    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: int = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token malformado")

    user = db.query(Usuario).filter(Usuario.id == user_id, Usuario.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo")

    # Verificar si la cuenta está bloqueada
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Cuenta bloqueada temporalmente. Intenta más tarde."
        )

    return user


# ── Dependencias de rol ────────────────────────────────────────────────────────
def require_role(*roles: RolEnum):
    """
    Factory de dependencias para exigir uno o más roles.
    Uso: Depends(require_role(RolEnum.admin, RolEnum.cajero))
    """
    def dependency(current_user: Usuario = Depends(get_current_user)) -> Usuario:
        if current_user.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Se requiere rol: {', '.join(r.value for r in roles)}"
            )
        return current_user
    return dependency


def require_admin(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    """Shortcut para exigir rol admin."""
    if current_user.rol != RolEnum.admin:
        raise HTTPException(status_code=403, detail="Solo administradores pueden acceder")
    return current_user


def require_admin_or_cajero(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    """Admins y cajeros."""
    if current_user.rol not in (RolEnum.admin, RolEnum.cajero):
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return current_user


def require_admin_or_bodeguero(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    """Admins y bodegueros."""
    if current_user.rol not in (RolEnum.admin, RolEnum.bodeguero):
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return current_user


# ── Auditoría ──────────────────────────────────────────────────────────────────
def get_client_ip(request: Request) -> str:
    """Extrae la IP real del cliente (considera proxies como Railway)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def log_audit(
    db: Session,
    usuario_id: Optional[int],
    accion: str,
    tabla: Optional[str] = None,
    registro_id: Optional[int] = None,
    detalle: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Registra una acción en el log de auditoría.
    Se llama desde los servicios — nunca falla silenciosamente.
    """
    try:
        log = AuditLog(
            usuario_id=usuario_id,
            accion=accion,
            tabla=tabla,
            registro_id=registro_id,
            detalle=detalle,
            ip_address=ip_address,
        )
        db.add(log)
        db.flush()  # Sin commit — se commitea junto con la transacción principal
    except Exception:
        pass  # Nunca dejar que la auditoría rompa una operación de negocio


# ── Paginación ─────────────────────────────────────────────────────────────────
class PaginationParams:
    def __init__(
        self,
        page: int = 1,
        page_size: int = 50,
    ):
        if page < 1:
            raise HTTPException(status_code=422, detail="page debe ser >= 1")
        if page_size < 1 or page_size > 200:
            raise HTTPException(status_code=422, detail="page_size debe estar entre 1 y 200")
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size
