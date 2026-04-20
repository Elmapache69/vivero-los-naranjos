"""
app/api/routes/inventario.py
Productos, fichas de plantas, categorías, proveedores — gestión de inventario.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.api.deps import (
    get_db, get_current_user, require_admin, require_admin_or_bodeguero,
    get_client_ip, log_audit, PaginationParams
)
from app.db.models import Producto, Categoria, FichaPlanta, Proveedor
from app.schemas import (
    ProductoCreate, ProductoUpdate, ProductoOut,
    FichaCreate, FichaOut,
    CategoriaCreate, CategoriaOut,
    ProveedorCreate, ProveedorOut,
)

router = APIRouter(tags=["Inventario"])


# ── Categorías ─────────────────────────────────────────────────────────────────
cat_router = APIRouter(prefix="/categorias")

@cat_router.get("", response_model=list[CategoriaOut])
def listar_categorias(
    db: Session = Depends(get_db),
    _=Depends(get_current_user)
):
    return db.query(Categoria).order_by(Categoria.nombre).all()

@cat_router.post("", response_model=CategoriaOut, status_code=201)
def crear_categoria(
    body: CategoriaCreate,
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):
    cat = Categoria(**body.model_dump())
    db.add(cat); db.commit(); db.refresh(cat)
    return cat

router.include_router(cat_router)


# ── Fichas de plantas ──────────────────────────────────────────────────────────
ficha_router = APIRouter(prefix="/fichas")

@ficha_router.get("", response_model=list[FichaOut])
def listar_fichas(
    db: Session = Depends(get_db),
    _=Depends(require_admin_or_bodeguero)
):
    return db.query(FichaPlanta).order_by(FichaPlanta.nombre_comun).all()

@ficha_router.post("", response_model=FichaOut, status_code=201)
def crear_ficha(
    body: FichaCreate,
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):
    ficha = FichaPlanta(**body.model_dump())
    db.add(ficha); db.commit(); db.refresh(ficha)
    return ficha

@ficha_router.put("/{fid}", response_model=FichaOut)
def actualizar_ficha(
    fid: int,
    body: FichaCreate,
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):
    ficha = db.query(FichaPlanta).filter(FichaPlanta.id == fid).first()
    if not ficha:
        raise HTTPException(404, "Ficha no encontrada")
    for k, v in body.model_dump().items():
        setattr(ficha, k, v)
    db.commit(); db.refresh(ficha)
    return ficha

router.include_router(ficha_router)


# ── Productos ──────────────────────────────────────────────────────────────────
prod_router = APIRouter(prefix="/productos")

def _build_producto_out(p: Producto) -> ProductoOut:
    """Construye el schema de salida con campos calculados y joined."""
    data = {
        "id": p.id,
        "nombre": p.nombre,
        "codigo": p.codigo,
        "categoria_id": p.categoria_id,
        "categoria_nombre": p.categoria.nombre if p.categoria else None,
        "ficha_planta_id": p.ficha_planta_id,
        "ficha_nombre": p.ficha_planta.nombre_comun if p.ficha_planta else None,
        "precio_venta": p.precio_venta,
        "precio_costo": p.precio_costo,
        "stock": p.stock,
        "stock_minimo": p.stock_minimo,
        "unidad": p.unidad,
        "is_active": p.is_active,
        "margen_porcentaje": p.margen_porcentaje,
        "stock_estado": p.stock_estado,
        "created_at": p.created_at,
    }
    return ProductoOut(**data)

@prod_router.get("", response_model=list[ProductoOut])
def listar_productos(
    buscar: Optional[str] = Query(None, max_length=100),
    categoria_id: Optional[int] = None,
    solo_alertas: bool = False,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = (
        db.query(Producto)
        .options(joinedload(Producto.categoria), joinedload(Producto.ficha_planta))
        .filter(Producto.is_active == True)
    )
    if buscar:
        q = q.filter(
            Producto.nombre.ilike(f"%{buscar}%") | Producto.codigo.ilike(f"%{buscar}%")
        )
    if categoria_id:
        q = q.filter(Producto.categoria_id == categoria_id)
    if solo_alertas:
        q = q.filter(Producto.stock <= Producto.stock_minimo)

    return [_build_producto_out(p) for p in q.order_by(Producto.nombre).all()]

@prod_router.get("/codigo/{codigo}", response_model=ProductoOut)
def buscar_por_codigo(
    codigo: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    p = (
        db.query(Producto)
        .options(joinedload(Producto.categoria), joinedload(Producto.ficha_planta))
        .filter(Producto.codigo == codigo, Producto.is_active == True)
        .first()
    )
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    return _build_producto_out(p)

@prod_router.post("", response_model=ProductoOut, status_code=201)
def crear_producto(
    body: ProductoCreate,
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if body.codigo and db.query(Producto).filter(Producto.codigo == body.codigo).first():
        raise HTTPException(409, "El código ya existe")
    p = Producto(**body.model_dump())
    db.add(p); db.flush()
    log_audit(db, user.id, "PRODUCTO_CREADO", "productos", p.id, body.nombre, get_client_ip(request))
    db.commit()
    db.refresh(p)
    return _build_producto_out(p)

@prod_router.put("/{pid}", response_model=ProductoOut)
def actualizar_producto(
    pid: int,
    body: ProductoUpdate,
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    p = db.query(Producto).options(
        joinedload(Producto.categoria), joinedload(Producto.ficha_planta)
    ).filter(Producto.id == pid, Producto.is_active == True).first()
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    log_audit(db, user.id, "PRODUCTO_ACTUALIZADO", "productos", pid, body.nombre, get_client_ip(request))
    db.commit(); db.refresh(p)
    return _build_producto_out(p)

@prod_router.delete("/{pid}", status_code=204)
def eliminar_producto(
    pid: int,
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    p = db.query(Producto).filter(Producto.id == pid).first()
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    p.is_active = False
    log_audit(db, user.id, "PRODUCTO_ELIMINADO", "productos", pid, p.nombre, get_client_ip(request))
    db.commit()

router.include_router(prod_router)


# ── Proveedores ────────────────────────────────────────────────────────────────
prov_router = APIRouter(prefix="/proveedores")

@prov_router.get("", response_model=list[ProveedorOut])
def listar_proveedores(db: Session = Depends(get_db), _=Depends(require_admin)):
    return db.query(Proveedor).filter(Proveedor.is_active == True).order_by(Proveedor.nombre).all()

@prov_router.post("", response_model=ProveedorOut, status_code=201)
def crear_proveedor(body: ProveedorCreate, admin=Depends(require_admin), db: Session = Depends(get_db)):
    p = Proveedor(**body.model_dump())
    db.add(p); db.commit(); db.refresh(p)
    return p

@prov_router.put("/{pid}", response_model=ProveedorOut)
def actualizar_proveedor(pid: int, body: ProveedorCreate, admin=Depends(require_admin), db: Session = Depends(get_db)):
    p = db.query(Proveedor).filter(Proveedor.id == pid).first()
    if not p:
        raise HTTPException(404, "Proveedor no encontrado")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.commit(); db.refresh(p)
    return p

router.include_router(prov_router)
