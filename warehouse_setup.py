"""
warehouse_setup.py
Auto-creates all Warehouse tables the app writes to, if they do not exist.

Fabric Warehouse supported DDL types (confirmed working):
  VARCHAR(n)   - all text including timestamps stored as ISO strings
  INT          - integers
  FLOAT        - decimals
  DATE         - date-only values

Unsupported (do not use):
  NVARCHAR, DATETIME, DATETIME2, DEFAULT, IDENTITY, CONSTRAINT, PRIMARY KEY

Timestamps are stored as VARCHAR(30) ISO strings: '2026-03-17 14:30:00'
and generated with CONVERT(VARCHAR(30), GETDATE(), 120) in SQL.
"""

from __future__ import annotations

import logging

from config import Config
import config
from db_service import run_warehouse_non_query, run_warehouse_df

logger = logging.getLogger(__name__)

WH = Config.WAREHOUSE_SCHEMA  # "dbo"

# Timestamp expression used in all INSERTs/UPDATEs
# FORMAT 120 = 'YYYY-MM-DD HH:MI:SS'
TS = "CONVERT(VARCHAR(30), GETDATE(), 120)"


# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL_GENIE_HISTORY = f"""
CREATE TABLE [{WH}].[{Config.HISTORY_TABLE_NAME}] (
    ID               INT           NOT NULL,
    NORMALIZED_QUERY VARCHAR(2000) NOT NULL,
    TYPE             VARCHAR(200)  NULL,
    USER_NAME        VARCHAR(200)  NOT NULL,
    LAST_ASKED_AT    VARCHAR(30)   NOT NULL,
    FREQUENCY        INT           NOT NULL
)
"""

_DDL_SAVED_INSIGHTS = f"""
CREATE TABLE [{WH}].[{Config.SAVED_INSIGHTS_TABLE}] (
    INSIGHT_ID    INT          NOT NULL,
    CREATED_AT    VARCHAR(30)  NOT NULL,
    CREATED_BY    VARCHAR(200) NOT NULL,
    PAGE          VARCHAR(100) NULL,
    TITLE         VARCHAR(500) NULL,
    QUESTION      VARCHAR(4000) NOT NULL,
    ANALYSIS_TYPE VARCHAR(200) NULL
)
"""

_DDL_QUERY_CACHE = f"""
CREATE TABLE [{WH}].[{Config.CACHE_TABLE_NAME}] (
    CACHE_KEY     VARCHAR(64)   NOT NULL,
    QUESTION_HASH VARCHAR(64)   NOT NULL,
    QUESTION_TEXT VARCHAR(2000) NOT NULL,
    GENERATED_SQL VARCHAR(8000) NULL,
    RESULT_JSON   VARCHAR(8000) NULL,
    ROW_COUNT     INT           NULL,
    CREATED_AT    VARCHAR(30)   NOT NULL,
    EXPIRES_AT    VARCHAR(30)   NOT NULL,
    HIT_COUNT     INT           NOT NULL
)
"""

_DDL_VALIDATION = f"""
CREATE TABLE [{WH}].[DATA_VALIDATION_RESULTS] (
    VALIDATION_ID  INT          NOT NULL,
    TEST_NAME      VARCHAR(200) NOT NULL,
    TABLE_NAME     VARCHAR(200) NOT NULL,
    STATUS         VARCHAR(10)  NOT NULL,
    MESSAGE        VARCHAR(2000) NULL,
    ACTUAL_VALUE   FLOAT        NULL,
    EXPECTED_VALUE FLOAT        NULL,
    RUN_AT         VARCHAR(30)  NOT NULL
)
"""
_DDL_LONG_TERM_MEMORY = f"""
CREATE TABLE [{WH}].[{Config.GENIE_CONTEXT_MEMORY_TABLE}](
                    ChatId              BIGINT NOT NULL,
                    SessionId           VARCHAR(64)  NOT NULL,
                    Username            VARCHAR(100) NOT NULL,
                    user_id             VARCHAR(64)  NOT NULL,
                    Question            VARCHAR(MAX) NOT NULL,
                    AnswerSummary       VARCHAR(MAX) NULL,
                    PredictiveAnalysis      VARCHAR(MAX) NULL,
                    PrescriptiveAnalysis    VARCHAR(MAX) NULL,
                    DescriptiveAnalysis     VARCHAR(MAX) NULL,
                    Context_Hash        VARCHAR(64)  NOT NULL,
                    Sql_Query           VARCHAR(MAX) NULL,
                    Tables_Used         VARCHAR(1000) NULL,
                    Filters_Applied     VARCHAR(1000) NULL,
                    Relevance_Score     FLOAT NULL,
                    Usage_Count         INT NULL,
                    Last_Accessed_At    VARCHAR(30) NULL,
                    CacheKey            VARCHAR(128) NULL,
                    Frequency           INT NOT NULL,
                    Action_Type         VARCHAR(50) NOT NULL,
                    Action_Details      VARCHAR(MAX) NULL,
                    ChatDate            DATE NOT NULL,
                    CreatedAt           VARCHAR(30) NOT NULL,
                    UpdatedAt           VARCHAR(30) NOT NULL
)
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def _table_exists(table_name: str) -> bool:
    """Return True if the table already exists in the Warehouse schema."""
    try:
        df = run_warehouse_df(f"""
            SELECT COUNT(*) AS CNT
            FROM   INFORMATION_SCHEMA.TABLES
            WHERE  TABLE_SCHEMA = '{WH}'
              AND  TABLE_NAME   = '{table_name}'
        """)
        if df.empty:
            return False
        col = df.columns[0]
        return int(df.iloc[0][col] or 0) > 0
    except Exception:
        return False


def _create_table(table_name: str, ddl: str) -> str:
    """Create a single table. Returns 'ok', 'exists', or 'error: <msg>'."""
    if _table_exists(table_name):
        logger.info("Table [%s].[%s] already exists.", WH, table_name)
        return "exists"
    try:
        run_warehouse_non_query(ddl)
        if _table_exists(table_name):
            logger.info("Table [%s].[%s] created.", WH, table_name)
            return "ok"
        return "error: table not found after CREATE"
    except Exception as exc:
        msg = str(exc)
        if "already exists" in msg.lower():
            return "exists"
        logger.error("Failed to create [%s].[%s]: %s", WH, table_name, msg)
        return f"error: {msg}"


# ── Public API ────────────────────────────────────────────────────────────────

_SETUP_DONE = False


def ensure_warehouse_tables(force: bool = False) -> dict[str, str]:
    """
    Create all required Warehouse tables if they do not already exist.
    Safe to call on every startup - skips tables that already exist.
    """
    global _SETUP_DONE
    if _SETUP_DONE and not force:
        return {}

    tables = [
        (Config.HISTORY_TABLE_NAME,   _DDL_GENIE_HISTORY),
        (Config.SAVED_INSIGHTS_TABLE, _DDL_SAVED_INSIGHTS),
        (Config.CACHE_TABLE_NAME,     _DDL_QUERY_CACHE),
        ("DATA_VALIDATION_RESULTS",   _DDL_VALIDATION),
        (Config.GENIE_CONTEXT_MEMORY_TABLE, _DDL_LONG_TERM_MEMORY),
    ]

    results: dict[str, str] = {}
    for table_name, ddl in tables:
        results[table_name] = _create_table(table_name, ddl)

    _SETUP_DONE = True
    return results


def get_table_status() -> dict[str, bool]:
    """Return {table_name: exists} for all managed tables."""
    return {
        name: _table_exists(name)
        for name in [
            Config.HISTORY_TABLE_NAME,
            Config.SAVED_INSIGHTS_TABLE,
            Config.CACHE_TABLE_NAME,
            "DATA_VALIDATION_RESULTS",
            Config.GENIE_CONTEXT_MEMORY_TABLE,
        ]
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("Creating warehouse tables...")
    results = ensure_warehouse_tables(force=True)
    for name, status in results.items():
        marker = "OK" if status in ("ok", "exists") else "FAIL"
        print(f"  [{marker}] {name}: {status}")
