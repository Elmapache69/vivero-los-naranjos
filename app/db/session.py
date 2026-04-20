"""
app/db/session.py
Conexión a la base de datos con SQLAlchemy.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from app.core.config import settings

# Motor de base de datos
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,       # Verifica conexión antes de usar
    pool_recycle=3600,        # Recicla conexiones cada hora
    echo=settings.DEBUG,      # Log SQL solo en desarrollo
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db():
    """
    Dependency de FastAPI para inyectar sesión de DB.
    Garantiza cierre de sesión aunque haya excepciones.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
