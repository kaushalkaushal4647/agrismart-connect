"""
Database connection manager and query helpers using Psycopg 3 (psycopg[binary,pool]).
Provides thread-safe connection pooling, auto-commit/rollback transactions,
and dictionary row formatting for seamless API response serialization.
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
try:
    from config import Config
except ImportError:
    from backend.config import Config

logger = logging.getLogger('agrismart.database')

# Module-level connection pool instance
_pool: Optional[ConnectionPool] = None


def init_pool() -> ConnectionPool:
    """Initialize the global connection pool."""
    global _pool
    if _pool is None or _pool.closed:
        conninfo = Config.get_db_conn_string()
        logger.info("Initializing PostgreSQL connection pool for database: %s", Config.DB_NAME)
        _pool = ConnectionPool(
            conninfo=conninfo,
            min_size=Config.DB_MIN_CONNECTIONS,
            max_size=Config.DB_MAX_CONNECTIONS,
            timeout=Config.DB_TIMEOUT,
            kwargs={"row_factory": dict_row}
        )
    return _pool


def get_pool() -> ConnectionPool:
    """Return the active connection pool, initializing it if necessary."""
    global _pool
    if _pool is None or _pool.closed:
        return init_pool()
    return _pool


def close_pool() -> None:
    """Close all open connections in the pool."""
    global _pool
    if _pool is not None and not _pool.closed:
        logger.info("Closing PostgreSQL connection pool...")
        _pool.close()
        _pool = None


@contextmanager
def get_db_connection():
    """
    Context manager that yields a connection from the pool.
    Usage:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    """
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


@contextmanager
def get_db_cursor(commit: bool = True):
    """
    Context manager yielding a cursor from a pooled connection.
    Automatically commits on normal completion or rolls back on exception.
    Usage:
        with get_db_cursor() as cur:
            cur.execute("INSERT INTO ...")
    """
    with get_db_connection() as conn:
        try:
            with conn.cursor() as cur:
                yield cur
            if commit:
                conn.commit()
        except Exception as err:
            conn.rollback()
            logger.error("Database transaction rolled back due to error: %s", err)
            raise


def execute_query(query: str, params: Optional[tuple | dict] = None, commit: bool = True) -> int:
    """
    Execute an INSERT, UPDATE, or DELETE query.
    Returns rowcount of affected rows.
    """
    with get_db_cursor(commit=commit) as cur:
        cur.execute(query, params)
        return cur.rowcount


def fetch_one(query: str, params: Optional[tuple | dict] = None) -> Optional[Dict[str, Any]]:
    """
    Execute a query and return a single row as a dictionary, or None.
    """
    with get_db_cursor(commit=False) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_all(query: str, params: Optional[tuple | dict] = None) -> List[Dict[str, Any]]:
    """
    Execute a query and return all matching rows as a list of dictionaries.
    """
    with get_db_cursor(commit=False) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]


def test_connection() -> Dict[str, Any]:
    """
    Verify PostgreSQL connectivity and query metadata.
    """
    with get_db_cursor(commit=False) as cur:
        cur.execute("SELECT version() AS db_version, current_database() AS current_db, now() AS server_time;")
        info = dict(cur.fetchone())

        # Count tables in public schema
        cur.execute("""
            SELECT count(*) AS table_count 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
        """)
        table_stat = dict(cur.fetchone())
        info['table_count'] = table_stat['table_count']

        return info
