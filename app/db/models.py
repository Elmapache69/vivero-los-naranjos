"""
app/db/models.py
Modelos SQLAlchemy — fuente única de verdad del esquema de base de datos.
"""
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, Enum, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, relationship
import enum


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ── Enums ──────────────────────────────────────────────────────────────────────
class RolEnum(str, enum.Enum):
    admin    = "admin"
    cajero   = "cajero"
    bodeguero = "bodeguero"


class TipoClienteEnum(str, enum.Enum):
    regular   = "regular"
    frecuente = "frecuente"
    mayorista = "mayorista"


class MetodoPagoEnum(str, enum.Enum):
    efectivo      = "efectivo"
    debito        = "debito"
    credito       = "credito"
    transferencia = "transferencia"


class EstadoCompraEnum(str, enum.Enum):
    pendiente = "pendiente"
    recibida  = "recibida"
    cancelada = "cancelada"


class EstadoVentaEnum(str, enum.Enum):
    completada = "completada"
    anulada    = "anulada"


# ── Mixins ─────────────────────────────────────────────────────────────────────
class TimestampMixin:
    """Agrega created_at y updated_at automáticos."""
    created_at: Mapped[datetime] = Column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = Column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    """Soft delete — nunca borra físicamente."""
    is_active: Mapped[bool] = Column(Boolean, default=True, nullable=False)


# ── Modelos ────────────────────────────────────────────────────────────────────
class Usuario(Base, TimestampMixin):
    __tablename__ = "usuarios"

    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(100), nullable=False)
    username    = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    rol         = Column(Enum(RolEnum), nullable=False, default=RolEnum.cajero)
    is_active   = Column(Boolean, default=True, nullable=False)

    # 2FA
    totp_secret    = Column(String(64), nullable=True)
    totp_enabled   = Column(Boolean, default=False, nullable=False)
    totp_verified  = Column(Boolean, default=False, nullable=False)

    # Seguridad
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until          = Column(DateTime(timezone=True), nullable=True)
    last_login            = Column(DateTime(timezone=True), nullable=True)
    password_changed_at   = Column(DateTime(timezone=True), default=utcnow)

    # Relaciones
    ventas         = relationship("Venta", foreign_keys="[Venta.cajero_id]", back_populates="cajero")
    compras        = relationship("Compra", back_populates="usuario")
    mermas         = relationship("Merma", back_populates="usuario")
    audit_logs     = relationship("AuditLog", back_populates="usuario")
    cierres_caja   = relationship("CierreCaja", back_populates="usuario")

    def __repr__(self) -> str:
        return f"<Usuario {self.username} ({self.rol})>"


class AuditLog(Base):
    """Registro inmutable de todas las acciones importantes."""
    __tablename__ = "audit_logs"

    id          = Column(Integer, primary_key=True, index=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    accion      = Column(String(100), nullable=False, index=True)
    tabla       = Column(String(50), nullable=True)
    registro_id = Column(Integer, nullable=True)
    detalle     = Column(Text, nullable=True)
    ip_address  = Column(String(45), nullable=True)
    timestamp   = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    usuario     = relationship("Usuario", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_timestamp_accion", "timestamp", "accion"),
    )


class Configuracion(Base):
    """Configuración del sistema en base de datos."""
    __tablename__ = "configuracion"

    clave       = Column(String(100), primary_key=True)
    valor       = Column(Text, nullable=False)
    descripcion = Column(String(255), nullable=True)
    updated_at  = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Categoria(Base, TimestampMixin):
    __tablename__ = "categorias"

    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(100), nullable=False, unique=True)
    descripcion = Column(Text, nullable=True)

    productos   = relationship("Producto", back_populates="categoria")


class FichaPlanta(Base, TimestampMixin):
    __tablename__ = "fichas_plantas"

    id                 = Column(Integer, primary_key=True, index=True)
    nombre_comun       = Column(String(150), nullable=False, index=True)
    nombre_cientifico  = Column(String(200), nullable=True)
    descripcion        = Column(Text, nullable=True)
    riego              = Column(String(100), nullable=True)
    luz                = Column(String(100), nullable=True)
    sustrato           = Column(String(200), nullable=True)
    temperatura_min    = Column(Float, nullable=True)
    temperatura_max    = Column(Float, nullable=True)
    temporada_venta    = Column(String(100), nullable=True)
    temporada_floracion = Column(String(100), nullable=True)
    foto_url           = Column(String(500), nullable=True)
    notas_ia           = Column(Text, nullable=True)

    productos = relationship("Producto", back_populates="ficha_planta")


class Proveedor(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "proveedores"

    id        = Column(Integer, primary_key=True, index=True)
    nombre    = Column(String(200), nullable=False)
    rut       = Column(String(20), nullable=True, unique=True)
    contacto  = Column(String(100), nullable=True)
    telefono  = Column(String(20), nullable=True)
    email     = Column(String(200), nullable=True)
    direccion = Column(String(300), nullable=True)

    compras = relationship("Compra", back_populates="proveedor")


class Producto(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "productos"

    id               = Column(Integer, primary_key=True, index=True)
    nombre           = Column(String(200), nullable=False, index=True)
    codigo           = Column(String(50), unique=True, nullable=True, index=True)
    categoria_id     = Column(Integer, ForeignKey("categorias.id"), nullable=True)
    ficha_planta_id  = Column(Integer, ForeignKey("fichas_plantas.id"), nullable=True)
    precio_venta     = Column(Float, nullable=False, default=0)
    precio_costo     = Column(Float, nullable=False, default=0)
    stock            = Column(Integer, nullable=False, default=0)
    stock_minimo     = Column(Integer, nullable=False, default=5)
    unidad           = Column(String(30), nullable=False, default="unidad")

    categoria    = relationship("Categoria", back_populates="productos")
    ficha_planta = relationship("FichaPlanta", back_populates="productos")
    venta_items  = relationship("VentaDetalle", back_populates="producto")
    compra_items = relationship("CompraDetalle", back_populates="producto")
    mermas       = relationship("Merma", back_populates="producto")

    @property
    def margen_porcentaje(self) -> float:
        if self.precio_venta > 0 and self.precio_costo > 0:
            return round((self.precio_venta - self.precio_costo) / self.precio_venta * 100, 1)
        return 0.0

    @property
    def stock_estado(self) -> str:
        if self.stock == 0:
            return "sin_stock"
        if self.stock <= self.stock_minimo:
            return "bajo"
        return "ok"


class Cliente(Base, TimestampMixin):
    __tablename__ = "clientes"

    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(200), nullable=False, index=True)
    rut         = Column(String(20), unique=True, nullable=True, index=True)
    telefono    = Column(String(20), nullable=True)
    email       = Column(String(200), nullable=True)
    direccion   = Column(String(300), nullable=True)
    tipo        = Column(Enum(TipoClienteEnum), default=TipoClienteEnum.regular)
    saldo_favor = Column(Float, default=0, nullable=False)
    notas       = Column(Text, nullable=True)

    ventas = relationship("Venta", back_populates="cliente")


class Venta(Base, TimestampMixin):
    __tablename__ = "ventas"

    id                = Column(Integer, primary_key=True, index=True)
    numero_boleta     = Column(String(30), unique=True, nullable=False, index=True)
    cliente_id        = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    cajero_id         = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    subtotal          = Column(Float, nullable=False, default=0)
    descuento         = Column(Float, nullable=False, default=0)
    total             = Column(Float, nullable=False, default=0)
    metodo_pago       = Column(Enum(MetodoPagoEnum), nullable=False)
    efectivo_recibido = Column(Float, nullable=False, default=0)
    vuelto            = Column(Float, nullable=False, default=0)
    estado            = Column(Enum(EstadoVentaEnum), default=EstadoVentaEnum.completada)
    notas             = Column(Text, nullable=True)
    anulada_por_id    = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    anulada_motivo    = Column(Text, nullable=True)
    anulada_en        = Column(DateTime(timezone=True), nullable=True)

    cliente  = relationship("Cliente", back_populates="ventas")
    cajero   = relationship("Usuario", foreign_keys=[cajero_id], back_populates="ventas")
    items    = relationship("VentaDetalle", back_populates="venta", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_ventas_cajero_fecha", "cajero_id", "created_at"),
        Index("ix_ventas_fecha", "created_at"),
    )


class VentaDetalle(Base):
    __tablename__ = "ventas_detalle"

    id              = Column(Integer, primary_key=True, index=True)
    venta_id        = Column(Integer, ForeignKey("ventas.id", ondelete="CASCADE"), nullable=False)
    producto_id     = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad        = Column(Integer, nullable=False)
    precio_unitario = Column(Float, nullable=False)
    precio_costo    = Column(Float, nullable=False, default=0)  # snapshot al momento de venta
    subtotal        = Column(Float, nullable=False)

    venta    = relationship("Venta", back_populates="items")
    producto = relationship("Producto", back_populates="venta_items")


class Compra(Base, TimestampMixin):
    __tablename__ = "compras"

    id            = Column(Integer, primary_key=True, index=True)
    numero_orden  = Column(String(30), unique=True, nullable=False)
    proveedor_id  = Column(Integer, ForeignKey("proveedores.id"), nullable=False)
    usuario_id    = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    total         = Column(Float, nullable=False, default=0)
    estado        = Column(Enum(EstadoCompraEnum), default=EstadoCompraEnum.recibida)
    notas         = Column(Text, nullable=True)

    proveedor = relationship("Proveedor", back_populates="compras")
    usuario   = relationship("Usuario", back_populates="compras")
    items     = relationship("CompraDetalle", back_populates="compra", cascade="all, delete-orphan")


class CompraDetalle(Base):
    __tablename__ = "compras_detalle"

    id              = Column(Integer, primary_key=True, index=True)
    compra_id       = Column(Integer, ForeignKey("compras.id", ondelete="CASCADE"), nullable=False)
    producto_id     = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad        = Column(Integer, nullable=False)
    precio_unitario = Column(Float, nullable=False)
    subtotal        = Column(Float, nullable=False)

    compra   = relationship("Compra", back_populates="items")
    producto = relationship("Producto", back_populates="compra_items")


class Merma(Base, TimestampMixin):
    __tablename__ = "mermas"

    id          = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    cantidad    = Column(Integer, nullable=False)
    motivo      = Column(String(200), nullable=False)
    costo_total = Column(Float, nullable=False, default=0)

    producto = relationship("Producto", back_populates="mermas")
    usuario  = relationship("Usuario", back_populates="mermas")


class CierreCaja(Base, TimestampMixin):
    __tablename__ = "cierres_caja"

    id                 = Column(Integer, primary_key=True, index=True)
    usuario_id         = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    efectivo_contado   = Column(Float, nullable=False, default=0)
    efectivo_sistema   = Column(Float, nullable=False, default=0)
    diferencia         = Column(Float, nullable=False, default=0)
    total_ventas       = Column(Float, nullable=False, default=0)
    num_ventas         = Column(Integer, nullable=False, default=0)
    total_por_metodo   = Column(Text, nullable=True)  # JSON string
    observaciones      = Column(Text, nullable=True)

    usuario = relationship("Usuario", back_populates="cierres_caja")
