import asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._init_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database connection pool (idempotent - safe to call on every request)"""
        if self.session_factory is not None:
            return

        async with self._init_lock:
            if self.session_factory is not None:
                return

            try:
                # Build the async URL from DATABASE_URL (docker-compose sets postgresql://...).
                # The async engine needs an async driver, so force postgresql+asyncpg.
                database_url = make_url(settings.database_url).set(drivername="postgresql+asyncpg")

                # Async engines use AsyncAdaptedQueuePool by default (QueuePool is rejected for asyncio)
                self.engine = create_async_engine(
                    database_url,
                    pool_size=settings.database_pool_size,
                    max_overflow=settings.database_max_overflow,
                    pool_timeout=settings.database_pool_timeout,
                    pool_pre_ping=True,  # Validate connections
                    pool_recycle=settings.database_pool_recycle,
                    echo=False  # Set to True for SQL debugging
                )

                self.session_factory = async_sessionmaker(
                    bind=self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False
                )

                logger.info("✅ Database connection pool initialized")

            except Exception as e:
                logger.error(f"❌ Database pool initialization failed: {e}")
                self.engine = None
                self.session_factory = None
                raise

    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
        self.engine = None
        self.session_factory = None

    def get_session(self) -> AsyncSession:
        """Get database session from pool (use as `async with db_pool.get_session() as session`)"""
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        return self.session_factory()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        yield session
