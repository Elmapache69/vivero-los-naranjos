"""
app/api/routes/comercial.py
Ventas, clientes, compras, mermas, cierre de caja y reportes.
"""
from datetime import datetime, timezone
from typing import Optional
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_

from app.api.deps import (
    get_db, get_current_user, require_admin, require_admin_or_cajero,
    get_client_ip, log_audit, PaginationParams
)
from app.db.models import (
    Venta, VentaDetalle, Cliente, Compra, CompraDetalle,
    Merma, CierreCaja, Producto, EstadoVentaEnum, MetodoPagoEnum
)
from app.db.models import Configuracion
from app.schemas import (
    VentaCreate, VentaOut, VentaItemOut, AnularVentaRequest,
    ClienteCreate, ClienteOut,
    CompraCreate, CompraOut,
    MermaCreate, MermaOut,
    CierreCajaCreate, CierreCajaOut,
    DashboardOut, ReporteVentasOut,
    ConfiguracionUpdate, ConfiguracionOut,
)

router = APIRouter(tags=["Comercial"])


# ══════════════════════════════════════════════════════════════════
#  CLIENTES
# ══════════════════════════════════════════════════════════════════
cli_router = APIRouter(prefix="/clientes")

@cli_router.get("", response_model=list[ClienteOut])
def listar_clientes(
    buscar: Optional[str] = Query(None, max_length=100),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Cliente)
    if buscar:
        q = q.filter(
            Cliente.nombre.ilike(f"%{buscar}%") | Cliente.rut.ilike(f"%{buscar}%")
        )
    return q.order_by(Cliente.nombre).all()

@cli_router.post("", response_model=ClienteOut, status_code=201)
def crear_cliente(
    body: ClienteCreate,
    user=Depends(require_admin_or_cajero),
    db: Session = Depends(get_db),
):
    if body.rut and db.query(Cliente).filter(Cliente.rut == body.rut).first():
        raise HTTPException(409, "El RUT ya existe")
    c = Cliente(**body.model_dump())
    db.add(c); db.commit(); db.refresh(c)
    return c

@cli_router.put("/{cid}", response_model=ClienteOut)
def actualizar_cliente(cid: int, body: ClienteCreate, _=Depends(require_admin_or_cajero), db: Session = Depends(get_db)):
    c = db.query(Cliente).filter(Cliente.id == cid).first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit(); db.refresh(c)
    return c

@cli_router.get("/{cid}/historial", response_model=list[VentaOut])
def historial_cliente(cid: int, _=Depends(get_current_user), db: Session = Depends(get_db)):
    ventas = (
        db.query(Venta)
        .options(joinedload(Venta.items).joinedload(VentaDetalle.producto), joinedload(Venta.cajero))
        .filter(Venta.cliente_id == cid)
        .order_by(Venta.created_at.desc())
        .limit(50)
        .all()
    )
    return [_build_venta_out(v) for v in ventas]

router.include_router(cli_router)


# ══════════════════════════════════════════════════════════════════
#  VENTAS
# ══════════════════════════════════════════════════════════════════
venta_router = APIRouter(prefix="/ventas")

def _build_venta_out(v: Venta) -> VentaOut:
    items = [VentaItemOut(
        id=i.id, producto_id=i.producto_id,
        producto_nombre=i.producto.nombre if i.producto else "",
        cantidad=i.cantidad, precio_unitario=i.precio_unitario,
        precio_costo=i.precio_costo, subtotal=i.subtotal,
    ) for i in v.items]
    return VentaOut(
        id=v.id, numero_boleta=v.numero_boleta,
        cliente_id=v.cliente_id,
        cliente_nombre=v.cliente.nombre if v.cliente else None,
        cajero_id=v.cajero_id,
        cajero_nombre=v.cajero.nombre if v.cajero else "",
        subtotal=v.subtotal, descuento=v.descuento, total=v.total,
        metodo_pago=v.metodo_pago.value, efectivo_recibido=v.efectivo_recibido,
        vuelto=v.vuelto, estado=v.estado.value, notas=v.notas,
        items=items, created_at=v.created_at,
    )

@venta_router.get("", response_model=list[VentaOut])
def listar_ventas(
    page: int = 1,
    page_size: int = 50,
    cajero_id: Optional[int] = None,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = (
        db.query(Venta)
        .options(
            joinedload(Venta.cliente),
            joinedload(Venta.cajero),
            joinedload(Venta.items).joinedload(VentaDetalle.producto),
        )
        .filter(Venta.estado == EstadoVentaEnum.completada)
    )
    if cajero_id:
        q = q.filter(Venta.cajero_id == cajero_id)
    ventas = q.order_by(Venta.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return [_build_venta_out(v) for v in ventas]

@venta_router.get("/{vid}", response_model=VentaOut)
def obtener_venta(vid: int, _=Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.query(Venta).options(
        joinedload(Venta.cliente), joinedload(Venta.cajero),
        joinedload(Venta.items).joinedload(VentaDetalle.producto),
    ).filter(Venta.id == vid).first()
    if not v:
        raise HTTPException(404, "Venta no encontrada")
    return _build_venta_out(v)

@venta_router.post("", response_model=VentaOut, status_code=201)
def crear_venta(
    body: VentaCreate,
    request: Request,
    user=Depends(require_admin_or_cajero),
    db: Session = Depends(get_db),
):
    # Verificar permiso de descuento para cajeros
    if user.rol.value == "cajero" and body.descuento > 0:
        cfg = db.query(Configuracion).filter(Configuracion.clave == "perm_cajero_descuento").first()
        if not cfg or cfg.valor != "true":
            raise HTTPException(403, "Los cajeros no tienen permiso para aplicar descuentos")

    # Verificar stock para todos los items de una sola vez
    productos_ids = [i.producto_id for i in body.items]
    productos_db = {p.id: p for p in db.query(Producto).filter(
        Producto.id.in_(productos_ids), Producto.is_active == True
    ).all()}

    for item in body.items:
        prod = productos_db.get(item.producto_id)
        if not prod:
            raise HTTPException(400, f"Producto ID {item.producto_id} no encontrado")
        if prod.stock < item.cantidad:
            raise HTTPException(400, f"Stock insuficiente para '{prod.nombre}' (disponible: {prod.stock})")

    # Calcular totales
    subtotal = sum(i.cantidad * i.precio_unitario for i in body.items)
    total = max(0, subtotal - body.descuento)
    vuelto = max(0, body.efectivo_recibido - total) if body.metodo_pago == "efectivo" else 0

    num_boleta = f"B-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')[:20]}"

    venta = Venta(
        numero_boleta=num_boleta,
        cliente_id=body.cliente_id,
        cajero_id=user.id,
        subtotal=subtotal,
        descuento=body.descuento,
        total=total,
        metodo_pago=MetodoPagoEnum(body.metodo_pago),
        efectivo_recibido=body.efectivo_recibido,
        vuelto=vuelto,
        notas=body.notas,
    )
    db.add(venta)
    db.flush()

    for item in body.items:
        prod = productos_db[item.producto_id]
        db.add(VentaDetalle(
            venta_id=venta.id,
            producto_id=item.producto_id,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            precio_costo=prod.precio_costo,  # snapshot del costo actual
            subtotal=item.cantidad * item.precio_unitario,
        ))
        prod.stock -= item.cantidad

    log_audit(db, user.id, "VENTA_CREADA", "ventas", venta.id,
              f"{num_boleta} total={total}", get_client_ip(request))
    db.commit()
    db.refresh(venta)

    # Recargar con joins
    v = db.query(Venta).options(
        joinedload(Venta.cliente), joinedload(Venta.cajero),
        joinedload(Venta.items).joinedload(VentaDetalle.producto),
    ).filter(Venta.id == venta.id).first()
    return _build_venta_out(v)


@venta_router.post("/{vid}/anular")
def anular_venta(
    vid: int,
    body: AnularVentaRequest,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Anula una venta y devuelve el stock."""
    v = db.query(Venta).options(
        joinedload(Venta.items).joinedload(VentaDetalle.producto)
    ).filter(Venta.id == vid).first()
    if not v:
        raise HTTPException(404, "Venta no encontrada")
    if v.estado == EstadoVentaEnum.anulada:
        raise HTTPException(400, "La venta ya está anulada")

    v.estado = EstadoVentaEnum.anulada
    v.anulada_por_id = admin.id
    v.anulada_motivo = body.motivo
    v.anulada_en = datetime.now(timezone.utc)

    # Devolver stock
    for item in v.items:
        item.producto.stock += item.cantidad

    log_audit(db, admin.id, "VENTA_ANULADA", "ventas", vid, body.motivo, get_client_ip(request))
    db.commit()
    return {"message": f"Venta {v.numero_boleta} anulada"}

router.include_router(venta_router)


# ══════════════════════════════════════════════════════════════════
#  COMPRAS
# ══════════════════════════════════════════════════════════════════
compra_router = APIRouter(prefix="/compras")

@compra_router.get("", response_model=list[CompraOut])
def listar_compras(db: Session = Depends(get_db), _=Depends(require_admin)):
    compras = db.query(Compra).options(
        joinedload(Compra.proveedor), joinedload(Compra.usuario)
    ).order_by(Compra.created_at.desc()).all()
    return [CompraOut(
        id=c.id, numero_orden=c.numero_orden,
        proveedor_id=c.proveedor_id, proveedor_nombre=c.proveedor.nombre if c.proveedor else "",
        usuario_id=c.usuario_id, total=c.total, estado=c.estado.value,
        notas=c.notas, created_at=c.created_at,
    ) for c in compras]

@compra_router.post("", response_model=CompraOut, status_code=201)
def crear_compra(
    body: CompraCreate,
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    total = sum(i.cantidad * i.precio_unitario for i in body.items)
    num = f"OC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    compra = Compra(
        numero_orden=num,
        proveedor_id=body.proveedor_id,
        usuario_id=user.id,
        total=total,
        notas=body.notas,
    )
    db.add(compra); db.flush()

    for item in body.items:
        prod = db.query(Producto).filter(Producto.id == item.producto_id).first()
        if not prod:
            raise HTTPException(400, f"Producto ID {item.producto_id} no existe")
        db.add(CompraDetalle(
            compra_id=compra.id,
            producto_id=item.producto_id,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            subtotal=item.cantidad * item.precio_unitario,
        ))
        prod.stock += item.cantidad
        prod.precio_costo = item.precio_unitario  # Actualiza precio de costo

    log_audit(db, user.id, "COMPRA_CREADA", "compras", compra.id, num, get_client_ip(request))
    db.commit(); db.refresh(compra)
    return CompraOut(
        id=compra.id, numero_orden=compra.numero_orden,
        proveedor_id=compra.proveedor_id,
        proveedor_nombre=compra.proveedor.nombre if compra.proveedor else "",
        usuario_id=compra.usuario_id, total=compra.total,
        estado=compra.estado.value, notas=compra.notas, created_at=compra.created_at,
    )

router.include_router(compra_router)


# ══════════════════════════════════════════════════════════════════
#  MERMAS
# ══════════════════════════════════════════════════════════════════
merma_router = APIRouter(prefix="/mermas")

@merma_router.get("", response_model=list[MermaOut])
def listar_mermas(db: Session = Depends(get_db), _=Depends(get_current_user)):
    mermas = db.query(Merma).options(
        joinedload(Merma.producto), joinedload(Merma.usuario)
    ).order_by(Merma.created_at.desc()).all()
    return [MermaOut(
        id=m.id, producto_id=m.producto_id,
        producto_nombre=m.producto.nombre if m.producto else "",
        usuario_id=m.usuario_id,
        usuario_nombre=m.usuario.nombre if m.usuario else "",
        cantidad=m.cantidad, motivo=m.motivo, costo_total=m.costo_total,
        created_at=m.created_at,
    ) for m in mermas]

@merma_router.post("", response_model=MermaOut, status_code=201)
def registrar_merma(
    body: MermaCreate,
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prod = db.query(Producto).filter(Producto.id == body.producto_id, Producto.is_active == True).first()
    if not prod:
        raise HTTPException(404, "Producto no encontrado")
    if prod.stock < body.cantidad:
        raise HTTPException(400, f"Stock insuficiente (disponible: {prod.stock})")

    costo = prod.precio_costo * body.cantidad
    merma = Merma(
        producto_id=body.producto_id,
        usuario_id=user.id,
        cantidad=body.cantidad,
        motivo=body.motivo,
        costo_total=costo,
    )
    db.add(merma)
    prod.stock -= body.cantidad
    log_audit(db, user.id, "MERMA_REGISTRADA", "mermas", None,
              f"{prod.nombre} x{body.cantidad} motivo={body.motivo}", get_client_ip(request))
    db.commit(); db.refresh(merma)
    return MermaOut(
        id=merma.id, producto_id=merma.producto_id, producto_nombre=prod.nombre,
        usuario_id=merma.usuario_id, usuario_nombre=user.nombre,
        cantidad=merma.cantidad, motivo=merma.motivo, costo_total=costo,
        created_at=merma.created_at,
    )

router.include_router(merma_router)


# ══════════════════════════════════════════════════════════════════
#  CIERRE DE CAJA
# ══════════════════════════════════════════════════════════════════
cierre_router = APIRouter(prefix="/cierres-caja")

@cierre_router.get("", response_model=list[CierreCajaOut])
def listar_cierres(db: Session = Depends(get_db), _=Depends(require_admin)):
    cierres = db.query(CierreCaja).options(joinedload(CierreCaja.usuario)).order_by(CierreCaja.created_at.desc()).limit(30).all()
    return [CierreCajaOut(
        id=c.id, usuario_id=c.usuario_id,
        usuario_nombre=c.usuario.nombre if c.usuario else "",
        efectivo_contado=c.efectivo_contado, efectivo_sistema=c.efectivo_sistema,
        diferencia=c.diferencia, total_ventas=c.total_ventas,
        num_ventas=c.num_ventas, observaciones=c.observaciones, created_at=c.created_at,
    ) for c in cierres]

@cierre_router.post("", response_model=CierreCajaOut, status_code=201)
def realizar_cierre(
    body: CierreCajaCreate,
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = datetime.now(timezone.utc).date()
    ef_sistema = db.query(func.coalesce(func.sum(Venta.total), 0)).filter(
        func.date(Venta.created_at) == today,
        Venta.metodo_pago == MetodoPagoEnum.efectivo,
        Venta.estado == EstadoVentaEnum.completada,
    ).scalar()
    total_ventas = db.query(func.coalesce(func.sum(Venta.total), 0)).filter(
        func.date(Venta.created_at) == today,
        Venta.estado == EstadoVentaEnum.completada,
    ).scalar()
    num_ventas = db.query(func.count(Venta.id)).filter(
        func.date(Venta.created_at) == today,
        Venta.estado == EstadoVentaEnum.completada,
    ).scalar()

    # Ventas por método de pago
    por_metodo = db.query(Venta.metodo_pago, func.sum(Venta.total)).filter(
        func.date(Venta.created_at) == today,
        Venta.estado == EstadoVentaEnum.completada,
    ).group_by(Venta.metodo_pago).all()

    cierre = CierreCaja(
        usuario_id=user.id,
        efectivo_contado=body.efectivo_contado,
        efectivo_sistema=ef_sistema,
        diferencia=body.efectivo_contado - ef_sistema,
        total_ventas=total_ventas,
        num_ventas=num_ventas,
        total_por_metodo=json.dumps({m.value: float(t) for m, t in por_metodo}),
        observaciones=body.observaciones,
    )
    db.add(cierre)
    log_audit(db, user.id, "CIERRE_CAJA", "cierres_caja", None,
              f"ef_contado={body.efectivo_contado} dif={cierre.diferencia}", get_client_ip(request))
    db.commit(); db.refresh(cierre)
    return CierreCajaOut(
        id=cierre.id, usuario_id=cierre.usuario_id, usuario_nombre=user.nombre,
        efectivo_contado=cierre.efectivo_contado, efectivo_sistema=cierre.efectivo_sistema,
        diferencia=cierre.diferencia, total_ventas=cierre.total_ventas,
        num_ventas=cierre.num_ventas, observaciones=cierre.observaciones, created_at=cierre.created_at,
    )

router.include_router(cierre_router)


# ══════════════════════════════════════════════════════════════════
#  REPORTES
# ══════════════════════════════════════════════════════════════════
rep_router = APIRouter(prefix="/reportes")

@rep_router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), _=Depends(require_admin)):
    today = datetime.now(timezone.utc).date()
    mes_inicio = today.replace(day=1)

    ventas_hoy = db.query(func.coalesce(func.sum(Venta.total), 0)).filter(
        func.date(Venta.created_at) == today, Venta.estado == EstadoVentaEnum.completada
    ).scalar()
    num_ventas_hoy = db.query(func.count(Venta.id)).filter(
        func.date(Venta.created_at) == today, Venta.estado == EstadoVentaEnum.completada
    ).scalar()
    ventas_mes = db.query(func.coalesce(func.sum(Venta.total), 0)).filter(
        func.date(Venta.created_at) >= mes_inicio, Venta.estado == EstadoVentaEnum.completada
    ).scalar()
    from app.db.models import Producto as P, Cliente as C
    prods = db.query(func.count(P.id)).filter(P.is_active == True).scalar()
    alertas = db.query(func.count(P.id)).filter(P.is_active == True, P.stock <= P.stock_minimo).scalar()
    total_clientes = db.query(func.count(C.id)).scalar()

    # Gráfico últimos 7 días
    from sqlalchemy import text
    graf = db.execute(text("""
        SELECT DATE(created_at) as dia, COALESCE(SUM(total),0) as total
        FROM ventas WHERE estado='completada'
        AND DATE(created_at) >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY DATE(created_at) ORDER BY dia
    """)).fetchall()

    cats = db.execute(text("""
        SELECT c.nombre, COALESCE(SUM(vd.subtotal),0) as total
        FROM ventas_detalle vd
        JOIN productos p ON vd.producto_id = p.id
        JOIN categorias c ON p.categoria_id = c.id
        JOIN ventas v ON vd.venta_id = v.id
        WHERE v.estado = 'completada'
        AND DATE(v.created_at) >= DATE_TRUNC('month', CURRENT_DATE)
        GROUP BY c.nombre ORDER BY total DESC LIMIT 6
    """)).fetchall()

    return DashboardOut(
        ventas_hoy=ventas_hoy, ventas_mes=ventas_mes,
        num_ventas_hoy=num_ventas_hoy,
        productos_activos=prods, alertas_stock=alertas, total_clientes=total_clientes,
        grafico_semana=[{"dia": str(r[0]), "total": float(r[1])} for r in graf],
        ventas_por_categoria=[{"nombre": r[0], "total": float(r[1])} for r in cats],
    )

@rep_router.get("/ventas", response_model=ReporteVentasOut)
def reporte_ventas(
    periodo: str = Query("mes", pattern="^(dia|semana|mes)$"),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    from sqlalchemy import text
    filtros = {
        "dia":    "DATE(v.created_at) = CURRENT_DATE",
        "semana": "DATE(v.created_at) >= CURRENT_DATE - INTERVAL '7 days'",
        "mes":    "DATE(v.created_at) >= DATE_TRUNC('month', CURRENT_DATE)",
    }
    where = filtros[periodo]

    total_row = db.execute(text(f"""
        SELECT COALESCE(SUM(total),0), COUNT(*) FROM ventas v
        WHERE estado='completada' AND {where}
    """)).fetchone()
    total_ventas, num_ventas = float(total_row[0]), int(total_row[1])

    tops = db.execute(text(f"""
        SELECT p.nombre, SUM(vd.cantidad) as vendidos, SUM(vd.subtotal) as ingresos
        FROM ventas_detalle vd JOIN ventas v ON vd.venta_id=v.id
        JOIN productos p ON vd.producto_id=p.id
        WHERE v.estado='completada' AND {where}
        GROUP BY p.nombre ORDER BY vendidos DESC LIMIT 8
    """)).fetchall()

    margen = db.execute(text(f"""
        SELECT p.nombre,
               SUM(vd.subtotal) as ingreso,
               SUM(vd.cantidad * vd.precio_costo) as costo,
               SUM(vd.subtotal - vd.cantidad*vd.precio_costo) as margen
        FROM ventas_detalle vd JOIN ventas v ON vd.venta_id=v.id
        JOIN productos p ON vd.producto_id=p.id
        WHERE v.estado='completada' AND {where}
        GROUP BY p.nombre ORDER BY margen DESC LIMIT 8
    """)).fetchall()

    por_dia = db.execute(text(f"""
        SELECT DATE(created_at) as dia, SUM(total), COUNT(*)
        FROM ventas v WHERE estado='completada' AND {where}
        GROUP BY DATE(created_at) ORDER BY dia
    """)).fetchall()

    por_pago = db.execute(text(f"""
        SELECT metodo_pago, COUNT(*), SUM(total)
        FROM ventas v WHERE estado='completada' AND {where}
        GROUP BY metodo_pago
    """)).fetchall()

    return ReporteVentasOut(
        periodo=periodo,
        total_ventas=total_ventas, num_ventas=num_ventas,
        ticket_promedio=total_ventas/num_ventas if num_ventas else 0,
        top_productos=[{"nombre": r[0], "vendidos": int(r[1]), "ingresos": float(r[2])} for r in tops],
        margen_productos=[{"nombre": r[0], "ingreso": float(r[1]), "costo": float(r[2]), "margen": float(r[3])} for r in margen],
        ventas_por_dia=[{"dia": str(r[0]), "total": float(r[1]), "cantidad": int(r[2])} for r in por_dia],
        ventas_por_metodo=[{"metodo": r[0].value, "cantidad": int(r[1]), "total": float(r[2])} for r in por_pago],
    )

@rep_router.get("/audit-log", response_model=list)
def audit_log(
    limit: int = Query(100, le=500),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.db.models import AuditLog
    logs = db.query(AuditLog).options(joinedload(AuditLog.usuario)).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [{"id": l.id, "accion": l.accion, "tabla": l.tabla, "registro_id": l.registro_id,
             "detalle": l.detalle, "ip": l.ip_address, "timestamp": l.timestamp.isoformat(),
             "usuario": l.usuario.username if l.usuario else None} for l in logs]

router.include_router(rep_router)


# ══════════════════════════════════════════════════════════════════
#  CONFIGURACION
# ══════════════════════════════════════════════════════════════════
cfg_router = APIRouter(prefix="/configuracion")

@cfg_router.get("", response_model=list[ConfiguracionOut])
def get_config(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Configuracion).all()

@cfg_router.put("/{clave}", response_model=ConfiguracionOut)
def set_config(clave: str, body: ConfiguracionUpdate, admin=Depends(require_admin), db: Session = Depends(get_db)):
    cfg = db.query(Configuracion).filter(Configuracion.clave == clave).first()
    if cfg:
        cfg.valor = body.valor
        if body.descripcion:
            cfg.descripcion = body.descripcion
    else:
        cfg = Configuracion(clave=clave, valor=body.valor, descripcion=body.descripcion)
        db.add(cfg)
    db.commit(); db.refresh(cfg)
    return cfg

router.include_router(cfg_router)
