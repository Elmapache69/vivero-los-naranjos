"""
app/api/routes/usuarios.py
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.api.deps import get_db, require_admin, get_current_user, get_client_ip, log_audit
from app.core.security import hash_password, validate_password_strength
from app.db.models import Usuario, RolEnum
from app.schemas import UsuarioCreate, UsuarioUpdate, UsuarioDetalle, UsuarioPublico

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.get("", response_model=list[UsuarioDetalle])
def listar_usuarios(
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):
    return db.query(Usuario).order_by(Usuario.nombre).all()


@router.post("", response_model=UsuarioPublico, status_code=201)
def crear_usuario(
    body: UsuarioCreate,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):
    if db.query(Usuario).filter(Usuario.username == body.username).first():
        raise HTTPException(status_code=409, detail="El nombre de usuario ya existe")
    valid, msg = validate_password_strength(body.password)
    if not valid:
        raise HTTPException(status_code=422, detail=msg)
    user = Usuario(
        nombre=body.nombre,
        username=body.username,
        password_hash=hash_password(body.password),
        rol=RolEnum(body.rol)
    )
    db.add(user)
    db.flush()
    log_audit(db, admin.id, "USUARIO_CREADO", "usuarios", user.id,
              f"Creado @{user.username} rol={user.rol.value}", get_client_ip(request))
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{uid}", response_model=UsuarioPublico)
def actualizar_usuario(
    uid: int,
    body: UsuarioUpdate,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(Usuario).filter(Usuario.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if body.nombre is not None:
        user.nombre = body.nombre
    if body.rol is not None:
        user.rol = RolEnum(body.rol)
    if body.is_active is not None:
        user.is_active = body.is_active
        if body.is_active:
            user.failed_login_attempts = 0
            user.locked_until = None
    log_audit(db, admin.id, "USUARIO_ACTUALIZADO", "usuarios", uid,
              str(body.model_dump(exclude_none=True)), get_client_ip(request))
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{uid}", status_code=204)
def eliminar_usuario(
    uid: int,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(Usuario).filter(Usuario.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.rol == RolEnum.admin:
        raise HTTPException(status_code=400, detail="No se puede eliminar al administrador")
    user.is_active = False
    log_audit(db, admin.id, "USUARIO_DESACTIVADO", "usuarios", uid,
              f"@{user.username}", get_client_ip(request))
    db.commit()
