import logging

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from src.core.config import settings

logger = logging.getLogger(__name__)


def _engine_kwargs() -> dict:
    if settings.db_null_pool:
        # AWS Lambda + Supabase transaction pooler: let Supavisor do the pooling
        # (see Settings.db_null_pool). Pool sizing knobs don't apply to NullPool.
        return {"poolclass": NullPool}
    return {
        # Ping a pooled connection before handing it out so a stale/dropped
        # connection (server restart, pooler timeout) is transparently replaced
        # instead of surfacing as an error on the next query.
        "pool_pre_ping": True,
        # Sized explicitly rather than left on SQLAlchemy's defaults (5 + 10):
        # the right numbers depend on the deployment (uvicorn worker count x the
        # upstream pooler's own connection ceiling, e.g. Supabase's), so they're
        # env-tunable. pool_recycle caps connection age so a pooler that silently
        # drops idle connections never hands us a dead one.
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
    }


try:
    engine = create_engine(settings.database_url, **_engine_kwargs())
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Database engine created successfully")
except Exception as e:
    logger.error(f"Failed to create database engine: {e}")
    raise

Base = declarative_base()


def get_db():
    """Dependency for FastAPI routes to get database session"""
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        raise
    finally:
        db.close()
