"""
app/main.py
Fábrica de la aplicación FastAPI con todos los middlewares y routers.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.api.routes import auth, usuarios, inventario, comercial
from app.db.session import engine
from app.db.models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Se ejecuta al inicio: crea tablas y datos iniciales.
    En producción las migraciones se manejan con Alembic.
    """
    Base.metadata.create_all(bind=engine)
    _seed_initial_data()
    yield
    # Cleanup al cerrar (si necesario)


def _seed_initial_data():
    """Inserta datos iniciales solo si la DB está vacía."""
    from sqlalchemy.orm import Session
    from app.db.session import SessionLocal
    from app.db.models import Usuario, Categoria, Configuracion, FichaPlanta, Producto, Proveedor, Cliente, RolEnum
    from app.core.security import hash_password

    db: Session = SessionLocal()
    try:
        # Admin por defecto
        if not db.query(Usuario).first():
            db.add(Usuario(
                nombre="Administrador",
                username="admin",
                password_hash=hash_password("Admin123!"),
                rol=RolEnum.admin,
            ))

        # Categorías
        if not db.query(Categoria).first():
            cats = ["Plantas de interior","Plantas de exterior","Suculentas y cactus",
                    "Árboles y arbustos","Semillas","Fertilizantes y sustratos",
                    "Herramientas","Macetas y decoración"]
            for c in cats:
                db.add(Categoria(nombre=c))

        # Configuración
        configs = [
            ("perm_cajero_descuento", "true",  "Cajeros pueden aplicar descuentos"),
            ("perm_cajero_clientes",  "false", "Cajeros pueden ver módulo clientes"),
            ("max_descuento_cajero",  "20",    "Descuento máximo que puede aplicar un cajero (%)"),
        ]
        for clave, valor, desc in configs:
            if not db.query(Configuracion).filter(Configuracion.clave == clave).first():
                db.add(Configuracion(clave=clave, valor=valor, descripcion=desc))

        db.flush()

        # Datos de prueba (solo si no hay productos)
        if not db.query(Producto).first():
            fichas = [
                FichaPlanta(nombre_comun="Potus", nombre_cientifico="Epipremnum aureum",
                            descripcion="Planta colgante de interior muy resistente",
                            riego="Moderado (2-3x semana)", luz="Luz indirecta",
                            sustrato="Tierra universal", temperatura_min=15, temperatura_max=30,
                            temporada_venta="Todo el año", notas_ia="Ideal para principiantes, tolera el descuido. Tóxica para mascotas."),
                FichaPlanta(nombre_comun="Lavanda", nombre_cientifico="Lavandula angustifolia",
                            descripcion="Arbusto aromático con flores moradas",
                            riego="Escaso (1x semana)", luz="Pleno sol",
                            sustrato="Arena y tierra", temperatura_min=5, temperatura_max=35,
                            temporada_venta="Primavera-Verano", temporada_floracion="Nov-Ene",
                            notas_ia="Repele mosquitos. Muy aromática. Ideal para exteriores soleados."),
                FichaPlanta(nombre_comun="Aloe Vera", nombre_cientifico="Aloe barbadensis",
                            descripcion="Suculenta medicinal",
                            riego="Escaso (1x semana)", luz="Pleno sol",
                            sustrato="Sustrato cactus", temperatura_min=10, temperatura_max=35,
                            temporada_venta="Todo el año",
                            notas_ia="Gel útil para quemaduras y piel. Muy resistente al sol."),
            ]
            for f in fichas:
                db.add(f)
            db.flush()

            prov = Proveedor(nombre="Viveros del Sur", rut="76.543.210-K",
                             contacto="Pedro Rojas", telefono="+56 9 8765 4321",
                             email="pedrorojas@viverosdelsur.cl")
            db.add(prov)
            db.flush()

            cat_ids = {c.nombre: c.id for c in db.query(Categoria).all()}
            ficha_ids = {f.nombre_comun: f.id for f in db.query(FichaPlanta).all()}

            prods = [
                ("Potus pequeño",     "PLT-001", "Plantas de interior", "Potus",   3500, 1800, 25, 5),
                ("Potus grande",      "PLT-002", "Plantas de interior", "Potus",   7500, 3500, 12, 3),
                ("Lavanda",           "PLT-003", "Plantas de exterior", "Lavanda", 4500, 2200, 18, 5),
                ("Aloe Vera",         "PLT-004", "Suculentas y cactus","Aloe Vera",4000, 1900, 22, 5),
                ("Tierra universal 10L","SUS-001","Fertilizantes y sustratos",None,3200,1500, 40, 10),
                ("Maceta terracota",  "MAC-001", "Macetas y decoración",None,     3500, 1600, 35, 8),
                ("Pala de jardín",    "HER-001", "Herramientas",        None,     5900, 2800, 15, 5),
            ]
            for nombre, codigo, cat, ficha, pv, pc, stock, smin in prods:
                db.add(Producto(
                    nombre=nombre, codigo=codigo,
                    categoria_id=cat_ids.get(cat),
                    ficha_planta_id=ficha_ids.get(ficha) if ficha else None,
                    precio_venta=pv, precio_costo=pc,
                    stock=stock, stock_minimo=smin,
                ))

            clientes = [
                ("María González", "12.345.678-9", "+56 9 1234 5678", "maria@email.com", "frecuente"),
                ("Juan Pérez",     "9.876.543-2",  "+56 9 8765 4321", "",               "regular"),
                ("Jardines SpA",   "76.111.222-3", "+56 9 5555 6666", "info@jardines.cl","mayorista"),
            ]
            for nombre, rut, tel, email, tipo in clientes:
                db.add(Cliente(nombre=nombre, rut=rut, telefono=tel, email=email, tipo=tipo))

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[SEED] Error en datos iniciales: {e}")
    finally:
        db.close()


# ── Rate Limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="2.0.0",
        description="Sistema de gestión para Jardín y Vivero Los Naranjos",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middlewares ────────────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    if settings.is_production:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

    # ── Seguridad en headers de respuesta ──────────────────────────────────────
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # ── Routers ────────────────────────────────────────────────────────────────
    app.include_router(auth.router,       prefix="/api")
    app.include_router(usuarios.router,   prefix="/api")
    app.include_router(inventario.router, prefix="/api")
    app.include_router(comercial.router,  prefix="/api")

    # ── Health check ───────────────────────────────────────────────────────────
    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "2.0.0", "app": settings.APP_NAME}

    # ── Static files / SPA ─────────────────────────────────────────────────────
    import os
    if os.path.exists("static"):
        app.mount("/static", StaticFiles(directory="static"), name="static")

        @app.get("/{path:path}")
        async def spa_fallback(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            return FileResponse("static/index.html")

        @app.get("/")
        async def root():
            return FileResponse("static/index.html")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
