"""
app/schemas/
Schemas Pydantic — definen contratos de entrada/salida de la API.
Separados de los modelos ORM para evitar acoplamientos.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator
import re


# ══════════════════════════════════════════════════════════════════
#  BASE
# ══════════════════════════════════════════════════════════════════
class BaseResponse(BaseModel):
    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════════════
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)
    totp_code: Optional[str] = Field(None, min_length=6, max_length=6)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    requires_2fa: bool = False
    user: "UsuarioPublico"


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Setup2FAResponse(BaseModel):
    secret: str
    uri: str
    message: str


class Verify2FARequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Las contraseñas no coinciden")
        return self


# ══════════════════════════════════════════════════════════════════
#  USUARIOS
# ══════════════════════════════════════════════════════════════════
class UsuarioCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-z0-9_]+$")
    password: str = Field(..., min_length=8)
    rol: str = Field(..., pattern=r"^(admin|cajero|bodeguero)$")

    @field_validator("username")
    @classmethod
    def username_lowercase(cls, v: str) -> str:
        return v.lower()


class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    rol: Optional[str] = Field(None, pattern=r"^(admin|cajero|bodeguero)$")
    is_active: Optional[bool] = None


class UsuarioPublico(BaseResponse):
    id: int
    nombre: str
    username: str
    rol: str
    is_active: bool
    totp_enabled: bool
    last_login: Optional[datetime]
    created_at: datetime


class UsuarioDetalle(UsuarioPublico):
    failed_login_attempts: int
    locked_until: Optional[datetime]


# ══════════════════════════════════════════════════════════════════
#  CATEGORIAS
# ══════════════════════════════════════════════════════════════════
class CategoriaCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = None


class CategoriaOut(BaseResponse):
    id: int
    nombre: str
    descripcion: Optional[str]


# ══════════════════════════════════════════════════════════════════
#  FICHAS DE PLANTAS
# ══════════════════════════════════════════════════════════════════
class FichaCreate(BaseModel):
    nombre_comun: str = Field(..., min_length=1, max_length=150)
    nombre_cientifico: Optional[str] = Field(None, max_length=200)
    descripcion: Optional[str] = None
    riego: Optional[str] = Field(None, max_length=100)
    luz: Optional[str] = Field(None, max_length=100)
    sustrato: Optional[str] = Field(None, max_length=200)
    temperatura_min: Optional[float] = Field(None, ge=-20, le=60)
    temperatura_max: Optional[float] = Field(None, ge=-20, le=60)
    temporada_venta: Optional[str] = Field(None, max_length=100)
    temporada_floracion: Optional[str] = Field(None, max_length=100)
    foto_url: Optional[str] = Field(None, max_length=500)
    notas_ia: Optional[str] = None


class FichaOut(BaseResponse, FichaCreate):
    id: int
    created_at: datetime


# ══════════════════════════════════════════════════════════════════
#  PROVEEDORES
# ══════════════════════════════════════════════════════════════════
class ProveedorCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    rut: Optional[str] = Field(None, max_length=20)
    contacto: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=200)
    direccion: Optional[str] = Field(None, max_length=300)


class ProveedorOut(BaseResponse, ProveedorCreate):
    id: int
    is_active: bool
    created_at: datetime


# ══════════════════════════════════════════════════════════════════
#  PRODUCTOS
# ══════════════════════════════════════════════════════════════════
class ProductoCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    codigo: Optional[str] = Field(None, max_length=50)
    categoria_id: Optional[int] = None
    ficha_planta_id: Optional[int] = None
    precio_venta: float = Field(..., ge=0)
    precio_costo: float = Field(0, ge=0)
    stock: int = Field(0, ge=0)
    stock_minimo: int = Field(5, ge=0)
    unidad: str = Field("unidad", max_length=30)


class ProductoUpdate(ProductoCreate):
    pass


class ProductoOut(BaseResponse):
    id: int
    nombre: str
    codigo: Optional[str]
    categoria_id: Optional[int]
    categoria_nombre: Optional[str] = None
    ficha_planta_id: Optional[int]
    ficha_nombre: Optional[str] = None
    precio_venta: float
    precio_costo: float
    stock: int
    stock_minimo: int
    unidad: str
    is_active: bool
    margen_porcentaje: float
    stock_estado: str
    created_at: datetime


# ══════════════════════════════════════════════════════════════════
#  CLIENTES
# ══════════════════════════════════════════════════════════════════
class ClienteCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    rut: Optional[str] = Field(None, max_length=20)
    telefono: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=200)
    direccion: Optional[str] = Field(None, max_length=300)
    tipo: str = Field("regular", pattern=r"^(regular|frecuente|mayorista)$")
    notas: Optional[str] = None


class ClienteOut(BaseResponse, ClienteCreate):
    id: int
    saldo_favor: float
    created_at: datetime


# ══════════════════════════════════════════════════════════════════
#  VENTAS
# ══════════════════════════════════════════════════════════════════
class VentaItemCreate(BaseModel):
    producto_id: int
    cantidad: int = Field(..., gt=0)
    precio_unitario: float = Field(..., ge=0)


class VentaCreate(BaseModel):
    cliente_id: Optional[int] = None
    metodo_pago: str = Field(..., pattern=r"^(efectivo|debito|credito|transferencia)$")
    descuento: float = Field(0, ge=0)
    efectivo_recibido: float = Field(0, ge=0)
    notas: Optional[str] = None
    items: List[VentaItemCreate] = Field(..., min_length=1)


class VentaItemOut(BaseResponse):
    id: int
    producto_id: int
    producto_nombre: str = ""
    cantidad: int
    precio_unitario: float
    precio_costo: float
    subtotal: float


class VentaOut(BaseResponse):
    id: int
    numero_boleta: str
    cliente_id: Optional[int]
    cliente_nombre: Optional[str] = None
    cajero_id: int
    cajero_nombre: str = ""
    subtotal: float
    descuento: float
    total: float
    metodo_pago: str
    efectivo_recibido: float
    vuelto: float
    estado: str
    notas: Optional[str]
    items: List[VentaItemOut] = []
    created_at: datetime


class AnularVentaRequest(BaseModel):
    motivo: str = Field(..., min_length=5, max_length=500)


# ══════════════════════════════════════════════════════════════════
#  COMPRAS
# ══════════════════════════════════════════════════════════════════
class CompraItemCreate(BaseModel):
    producto_id: int
    cantidad: int = Field(..., gt=0)
    precio_unitario: float = Field(..., ge=0)


class CompraCreate(BaseModel):
    proveedor_id: int
    notas: Optional[str] = None
    items: List[CompraItemCreate] = Field(..., min_length=1)


class CompraOut(BaseResponse):
    id: int
    numero_orden: str
    proveedor_id: int
    proveedor_nombre: str = ""
    usuario_id: int
    total: float
    estado: str
    notas: Optional[str]
    created_at: datetime


# ══════════════════════════════════════════════════════════════════
#  MERMAS
# ══════════════════════════════════════════════════════════════════
class MermaCreate(BaseModel):
    producto_id: int
    cantidad: int = Field(..., gt=0)
    motivo: str = Field(..., min_length=3, max_length=200)


class MermaOut(BaseResponse):
    id: int
    producto_id: int
    producto_nombre: str = ""
    usuario_id: int
    usuario_nombre: str = ""
    cantidad: int
    motivo: str
    costo_total: float
    created_at: datetime


# ══════════════════════════════════════════════════════════════════
#  CIERRE CAJA
# ══════════════════════════════════════════════════════════════════
class CierreCajaCreate(BaseModel):
    efectivo_contado: float = Field(..., ge=0)
    observaciones: Optional[str] = None


class CierreCajaOut(BaseResponse):
    id: int
    usuario_id: int
    usuario_nombre: str = ""
    efectivo_contado: float
    efectivo_sistema: float
    diferencia: float
    total_ventas: float
    num_ventas: int
    observaciones: Optional[str]
    created_at: datetime


# ══════════════════════════════════════════════════════════════════
#  REPORTES
# ══════════════════════════════════════════════════════════════════
class DashboardOut(BaseModel):
    ventas_hoy: float
    ventas_mes: float
    num_ventas_hoy: int
    productos_activos: int
    alertas_stock: int
    total_clientes: int
    grafico_semana: List[dict]
    ventas_por_categoria: List[dict]


class ReporteVentasOut(BaseModel):
    periodo: str
    total_ventas: float
    num_ventas: int
    ticket_promedio: float
    top_productos: List[dict]
    margen_productos: List[dict]
    ventas_por_dia: List[dict]
    ventas_por_metodo: List[dict]


# ══════════════════════════════════════════════════════════════════
#  CONFIGURACION
# ══════════════════════════════════════════════════════════════════
class ConfiguracionUpdate(BaseModel):
    valor: str
    descripcion: Optional[str] = None


class ConfiguracionOut(BaseModel):
    clave: str
    valor: str
    descripcion: Optional[str]


# ══════════════════════════════════════════════════════════════════
#  AUDIT LOG
# ══════════════════════════════════════════════════════════════════
class AuditLogOut(BaseModel):
    id: int
    usuario_id: Optional[int]
    usuario_nombre: Optional[str] = None
    accion: str
    tabla: Optional[str]
    registro_id: Optional[int]
    detalle: Optional[str]
    ip_address: Optional[str]
    timestamp: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
#  PAGINACION
# ══════════════════════════════════════════════════════════════════
class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int
