import aiosqlite
import logging
from app.core.config import settings

logger = logging.getLogger("nexa.database")

# Global pool connection for fast reads
_db_connection: aiosqlite.Connection = None

async def init_db():
    """Initialize SQLite DB with WAL mode & high busy_timeout"""
    global _db_connection
    try:
        _db_connection = await aiosqlite.connect(settings.DATABASE_URL, timeout=30.0)
        _db_connection.row_factory = aiosqlite.Row
        await _db_connection.execute("PRAGMA journal_mode=WAL;")
        await _db_connection.execute("PRAGMA busy_timeout=30000;")
        await create_tables(_db_connection)
        logger.info("✅ Enterprise SQLite DB initialized with WAL mode & busy_timeout=30s")
    except Exception as e:
        logger.error(f"❌ Database Initialization Error: {e}")
        raise e

async def get_db() -> aiosqlite.Connection:
    """Dependency injection helper for routes"""
    global _db_connection
    if _db_connection is None:
        await init_db()
    return _db_connection

async def close_db():
    global _db_connection
    if _db_connection:
        await _db_connection.close()
        _db_connection = None
        logger.info("🔒 Database connection closed")

async def create_tables(db: aiosqlite.Connection):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) UNIQUE NOT NULL,
            location VARCHAR(255),
            il VARCHAR(100),
            ilce VARCHAR(100),
            mahalle VARCHAR(100),
            description TEXT,
            cover_image_url VARCHAR(500),
            lat FLOAT,
            lng FLOAT,
            ada_no VARCHAR(50),
            parsel_no VARCHAR(50),
            tkgm_verified INTEGER DEFAULT 0,
            location_accuracy_score INTEGER DEFAULT 100,
            location_status VARCHAR(50) DEFAULT 'verified',
            location_source VARCHAR(255) DEFAULT 'System',
            reverse_geocoded_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for col_def in [
        ("location_accuracy_score", "INTEGER DEFAULT 100"),
        ("location_status", "VARCHAR(50) DEFAULT 'verified'"),
        ("location_source", "VARCHAR(255) DEFAULT 'System'"),
        ("reverse_geocoded_address", "TEXT")
    ]:
        try:
            await db.execute(f"ALTER TABLE projects ADD COLUMN {col_def[0]} {col_def[1]}")
        except Exception:
            pass
    await db.execute("""
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            unit_type VARCHAR(50),
            area_m2 FLOAT,
            price FLOAT,
            available_count INTEGER,
            plan_url VARCHAR(500),
            images TEXT,
            delivery_date VARCHAR(100)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            name VARCHAR(255),
            phone VARCHAR(20),
            email VARCHAR(255),
            interested_units TEXT,
            notes TEXT,
            stage VARCHAR(50) DEFAULT 'Yeni Talep',
            budget VARCHAR(100) DEFAULT 'Belirtilmedi',
            assigned_agent VARCHAR(100) DEFAULT 'Yönetici',
            firebase_synced INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_contact TIMESTAMP,
            UNIQUE(project_id, phone)
        )
    """)
    for col_def in [
        ("stage", "VARCHAR(50) DEFAULT 'Yeni Talep'"),
        ("budget", "VARCHAR(100) DEFAULT 'Belirtilmedi'"),
        ("assigned_agent", "VARCHAR(100) DEFAULT 'Yönetici'"),
        ("firebase_synced", "INTEGER DEFAULT 0")
    ]:
        try:
            await db.execute(f"ALTER TABLE customers ADD COLUMN {col_def[0]} {col_def[1]}")
        except Exception:
            pass
    await db.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
            unit_id INTEGER REFERENCES units(id),
            status VARCHAR(50),
            offer_price FLOAT,
            contract_signed TIMESTAMP,
            payment_plan TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            doc_type VARCHAR(50),
            title VARCHAR(255),
            content TEXT,
            file_url VARCHAR(500),
            category VARCHAR(100) DEFAULT 'Genel',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
            direction VARCHAR(10),
            message_text TEXT,
            ai_response TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            twilio_sid VARCHAR(255)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
            chunk_text TEXT,
            embedding TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(100) UNIQUE NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            role VARCHAR(50) DEFAULT 'agent',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.commit()
