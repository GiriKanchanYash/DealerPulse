"""
Database service for Microsoft Fabric SQL (Lakehouse + Warehouse).

Enhancements over the original:
  - Query result cache backed by a Warehouse session table (req 3, 8).
    The cache is the FIRST place checked before calling Azure OpenAI or
    executing a heavy analytical query.
  - Clean connection management with automatic reconnect.
  - Data-Vault-aware helpers (req 5).
  - No emojis in log messages (req 1).
  - Warehouse read/write separated from Lakehouse reads (req 11).
"""

from __future__ import annotations
import hashlib
# import json
import logging
from typing import Optional
import time
import pandas as pd
import pyodbc

from config import Config

logger = logging.getLogger(__name__)


def _safe_log_event(event_type: str, payload: dict) -> None:
    """Avoid circular imports by importing Genie logging lazily."""
    try:
        from genie_middleware import log_event

        log_event(event_type, payload)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

class FabricSession:
    """
    Wraps a pyodbc connection to the Microsoft Fabric Lakehouse SQL endpoint.
    Provides a Snowpark-compatible .sql().collect() / .to_pandas() interface
    so upper-layer code requires minimal changes.
    """

    def __init__(self, connection_string: str | None = None):
        self._connection_string = connection_string or Config.get_connection_string()
        self._connection: pyodbc.Connection | None = None

    # ------------------------------------------------------------------
    def _connect(self) -> pyodbc.Connection:
        return pyodbc.connect(self._connection_string)

    def get_connection(self) -> pyodbc.Connection:
        if self._connection is None or not self._is_alive():
            self._connection = self._connect()
        return self._connection

    def _is_alive(self) -> bool:
        try:
            if self._connection:
                self._connection.execute("SELECT 1")
                return True
        except Exception:
            self._connection = None
        return False

    # ------------------------------------------------------------------
    def sql(self, query: str) -> "FabricDataFrame":
        return FabricDataFrame(query, self)

    def close(self) -> None:
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None


class FabricDataFrame:
    """Thin DataFrame shim around a SQL query string."""

    def __init__(self, query: str, session: FabricSession):
        self._query = query
        self._session = session

    def collect(self) -> list:
        conn = self._session.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(self._query)
            return cursor.fetchall()
        finally:
            cursor.close()

    def to_pandas(self) -> pd.DataFrame:
        conn = self._session.get_connection()
        return pd.read_sql(self._query, conn)


# ---------------------------------------------------------------------------
# Module-level session singletons
# ---------------------------------------------------------------------------

_lakehouse_session: FabricSession | None = None
_warehouse_session: FabricSession | None = None


def get_active_session() -> FabricSession:
    """Return the module-level Lakehouse session (read-only analytics)."""
    global _lakehouse_session
    if _lakehouse_session is None:
        _lakehouse_session = FabricSession(Config.get_connection_string())
    return _lakehouse_session


def _get_warehouse_session() -> FabricSession:
    """ Return the module-level Warehouse session (read + write)."""

    global _warehouse_session
    if _warehouse_session is None:
        _warehouse_session = FabricSession(
            Config.get_warehouse_connection_string())
    return _warehouse_session


# ---------------------------------------------------------------------------
# Public query helpers - Lakehouse
# ---------------------------------------------------------------------------


def run_df(sql: str) -> pd.DataFrame:
    """Execute SQL against the Lakehouse and return a DataFrame."""
    try:
        return get_active_session().sql(sql).to_pandas()
    except Exception as exc:
        raise RuntimeError(f"Lakehouse query failed: {exc}") from exc


def execute_query(sql: str, params: Optional[list] = None) -> pd.DataFrame:
    """Parameterised Lakehouse SELECT."""
    try:
        conn = get_active_session().get_connection()
        return pd.read_sql(sql, conn, params=params or [])
    except Exception as exc:
        raise RuntimeError(f"Lakehouse query failed: {exc}") from exc


def execute_non_query(sql: str, params: Optional[list] = None) -> int:
    """Non-SELECT statement against the Lakehouse (DDL etc.)."""
    try:
        conn = get_active_session().get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params or [])
        conn.commit()
        rows = cursor.rowcount
        cursor.close()
        return rows
    except Exception as exc:
        raise RuntimeError(f"Lakehouse non-query failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Public query helpers - Warehouse (read + write)
# ---------------------------------------------------------------------------

def get_warehouse_connection() -> pyodbc.Connection:
    return _get_warehouse_session().get_connection()


def run_warehouse_df(sql: str) -> pd.DataFrame:
    """SELECT from the Warehouse."""

    try:
        conn = _get_warehouse_session().get_connection()
        return pd.read_sql(sql, conn)
    except Exception as exc:
        raise RuntimeError(f"Warehouse read failed: {exc}") from exc


def run_warehouse_non_query(sql: str, params: Optional[list] = None) -> int:
    """INSERT / UPDATE / DELETE against the Warehouse."""

    try:
        conn = _get_warehouse_session().get_connection()
        cursor = conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        conn.commit()
        rows = cursor.rowcount
        cursor.close()
        return rows
    except Exception as exc:
        raise RuntimeError(f"Warehouse write failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Query result cache (req 3, 8)
#
# The cache table (dbo.QUERY_RESULT_CACHE) is checked BEFORE every AI call
# and every heavy analytical query.  If a matching row is found within TTL,
# the cached JSON payload is returned directly.
# ---------------------------------------------------------------------------

_CACHE_TABLE = f"[{Config.WAREHOUSE_SCHEMA}].[{Config.CACHE_TABLE_NAME}]"

print(f"Cache enabled: {Config.CACHE_ENABLED}, table: {_CACHE_TABLE}, TTL: {Config.CACHE_TTL_SECONDS} seconds")

def _cache_key(question: str) -> str:
    """Deterministic 64-char hex key for a natural-language question."""
    return hashlib.sha256(question.strip().lower().encode()).hexdigest()

def cache_get(question: str) -> Optional[dict]:
    """
    Return cached entry for the given question if it exists and has not expired.

    Returns a dict with keys:
        - sql
        - result_json
        - row_count

    Returns None when there is no valid cache entry.
    """
    if not Config.CACHE_ENABLED:
        return None

    start_time = time.time()
    key = _cache_key(question)

    try:
        df = run_warehouse_df(
            f"""
            SELECT GENERATED_SQL,
                   RESULT_JSON,
                   ROW_COUNT
            FROM   {_CACHE_TABLE}
            WHERE  CACHE_KEY = '{key}'
              AND  EXPIRES_AT > FORMAT(GETDATE(), 'yyyy-MM-dd HH:mm:ss')
            """
        )

        if df.empty:
            # 🔹 Log cache miss
            _safe_log_event(
                "CACHE_MISS",
                {
                    "summary": "Cache miss",
                    "cache_key": key,
                    "relevance": 0.2,
                },
            )
            return None

        # Increment hit counter (best-effort)
        try:
            run_warehouse_non_query(
                f"""
                UPDATE {_CACHE_TABLE}
                SET    HIT_COUNT = HIT_COUNT + 1
                WHERE  CACHE_KEY = '{key}'
                """
            )
        except Exception:
            pass

        row = df.iloc[0]

        # Fabric Warehouse returns column names in uppercase
        def _get(r, *names):
            for name in names:
                value = r.get(name)
                if value is not None:
                    return value
            return None

        result = {
            "sql": _get(row, "GENERATED_SQL", "generated_sql") or "",
            "result_json": _get(row, "RESULT_JSON", "result_json") or "[]",
            "row_count": int(_get(row, "ROW_COUNT", "row_count") or 0),
        }

        duration = round(time.time() - start_time, 3)

        # 🔹 Log cache hit
        _safe_log_event(
            "CACHE_HIT",
            {
                "summary": f"{result['row_count']} rows (cache) in {duration}s",
                "sql": result["sql"],
                "cache_key": key,
                "relevance": 1.0,
                "details": f"Cache retrieval time: {duration}s",
            },
        )

        return result

    except Exception as exc:
        duration = round(time.time() - start_time, 3)

        # 🔹 Log cache error
        _safe_log_event(
            "CACHE_ERROR",
            {
                "summary": "Cache lookup failed",
                "details": f"{str(exc)} | Time: {duration}s",
                "cache_key": key,
                "relevance": 0.0,
            },
        )

        logger.debug("Cache lookup failed: %s", exc)
        return None


def cache_set(question: str, sql: str, result_df: pd.DataFrame) -> None:
    """
    Persist a query result in the Warehouse cache table.
    Large result sets (> CACHE_MAX_ROWS) are not cached.
    """
    if not Config.CACHE_ENABLED:
        return

    if len(result_df) > Config.CACHE_MAX_ROWS:
        logger.debug("Result too large to cache (%d rows)", len(result_df))
        return

    key = _cache_key(question)
    q_esc = question.replace("'", "''")[:2000]
    sql_esc = sql.replace("'", "''")
    ttl = Config.CACHE_TTL_SECONDS

    try:
        result_json = result_df.to_json(orient="records", date_format="iso")
        result_json = result_json.replace("'", "''")
    except Exception:
        return

    nrows = len(result_df)
    try:
        # Try UPDATE first
        rows_updated = run_warehouse_non_query(f"""
            UPDATE {_CACHE_TABLE}
            SET    GENERATED_SQL = '{sql_esc}',
                   RESULT_JSON   = '{result_json}',
                   ROW_COUNT     = {nrows},
                   CREATED_AT    =  FORMAT(GETDATE(), 'yyyy-MM-dd HH:mm:ss'),
                   EXPIRES_AT    = FORMAT(
                       DATEADD(SECOND, {ttl}, GETDATE()), 'yyyy-MM-dd HH:mm:ss'),
                   QUESTION_TEXT = '{q_esc}',
                   HIT_COUNT     = 0
            WHERE  CACHE_KEY = '{key}'
        """)
        if rows_updated == 0:
            # No existing row - INSERT with all values explicit (no DEFAULT)
            # run_warehouse_non_query(f"""
            run_warehouse_non_query(f"""
                INSERT INTO {_CACHE_TABLE}
                    (CACHE_KEY, QUESTION_HASH, QUESTION_TEXT, GENERATED_SQL,
                     RESULT_JSON, ROW_COUNT, CREATED_AT, EXPIRES_AT, HIT_COUNT)
                VALUES (
                    '{key}', '{key}', '{q_esc}', '{sql_esc}',
                    '{result_json}', {nrows},
                    FORMAT(GETDATE(), 'yyyy-MM-dd HH:mm:ss'),
                    FORMAT(DATEADD(SECOND, {ttl},
                           GETDATE()), 'yyyy-MM-dd HH:mm:ss'),
                    0
                )
            """)
    except Exception as exc:
        logger.debug("Cache write failed: %s", exc)


def cache_invalidate(question: str) -> None:
    """Delete a specific question from the cache."""
    key = _cache_key(question)
    try:
        # run_warehouse_non_query(
        run_warehouse_non_query(
            f"DELETE FROM {_CACHE_TABLE} WHERE cache_key = '{key}'"
        )
    except Exception:
        pass


def cache_purge_expired() -> int:
    """Delete all expired entries; returns number of rows removed."""
    try:
        return run_warehouse_non_query(

            f"DELETE FROM {_CACHE_TABLE} WHERE EXPIRES_AT <= FORMAT(GETDATE(), 'yyyy-MM-dd HH:mm:ss')"
        )
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Data Vault schema discovery helpers (req 5, 7)
# ---------------------------------------------------------------------------

def list_tables_in_schema(schema: str = "INFORMATION_MART") -> pd.DataFrame:
    """
    Return all base tables and views in the given schema.
    Used by the AI YAML enrichment pipeline.
    """
    sql = f"""
        SELECT
            TABLE_NAME,
            TABLE_TYPE
        FROM   INFORMATION_SCHEMA.TABLES
        WHERE  TABLE_SCHEMA = '{schema}'
        ORDER  BY TABLE_NAME
    """
    return run_df(sql)


def get_table_columns(table_name: str, schema: str = "INFORMATION_MART") -> pd.DataFrame:
    """Return column metadata for a single table."""
    sql = f"""
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            IS_NULLABLE,
            ORDINAL_POSITION
        FROM   INFORMATION_SCHEMA.COLUMNS
        WHERE  TABLE_SCHEMA = '{schema}'
          AND  TABLE_NAME   = '{table_name}'
        ORDER  BY ORDINAL_POSITION
    """
    return run_df(sql)


def get_primary_keys(table_name: str, schema: str = "INFORMATION_MART") -> list[str]:
    """Return column names that form the primary key of a table."""
    sql = f"""
        SELECT  kcu.COLUMN_NAME
        FROM    INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        JOIN    INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                ON  tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                AND tc.TABLE_SCHEMA    = kcu.TABLE_SCHEMA
        WHERE   tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
          AND   tc.TABLE_SCHEMA    = '{schema}'
          AND   tc.TABLE_NAME      = '{table_name}'
        ORDER   BY kcu.ORDINAL_POSITION
    """
    try:
        df = run_df(sql)
        return df["COLUMN_NAME"].tolist() if not df.empty else []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def normalize_upper(df: pd.DataFrame) -> pd.DataFrame:
    """Convert all column names to uppercase (matches Fabric/Snowflake defaults)."""
    df.columns = [c.upper() for c in df.columns]
    return df


def sql_escape(value: str) -> str:
    """Escape a string value for safe embedding in a SQL literal."""
    if value is None:
        return "NULL"
    return str(value).replace("'", "''")


def test_connection() -> bool:
    """Verify the Lakehouse connection is alive."""
    try:
        rows = get_active_session().sql("SELECT 1 AS probe").collect()
        return len(rows) > 0
    except Exception as exc:
        logger.error("Connection test failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Lakehouse connection...")
    # print(Config.get_connection_string())
    # print(Config.FABRIC_ORDERLENS_DATABASE)
    if test_connection():
        print("Connection successful.")
        df = run_df(
            "SELECT TOP 5 * FROM INFORMATION_MART.FACT_ORDER_HISTORY_VW")
        print(f"Sample query returned {len(df)} rows.")
    else:
        print("Connection failed. Check configuration.")