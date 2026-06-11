"""
Microsoft Fabric T-SQL compatibility utilities.

Normalizes SQL written for Snowflake or generic ANSI dialects into
T-SQL that runs on Fabric Lakehouse and Warehouse SQL endpoints.
"""

from __future__ import annotations

import re


def normalize_sql(sql: str) -> str:
    """
    Convert Snowflake / ANSI SQL to Microsoft Fabric T-SQL.

    Handles:
      - LIMIT n           -> SELECT TOP n  (or OFFSET/FETCH when ORDER BY present)
      - LIMIT n OFFSET m  -> ORDER BY ... OFFSET m ROWS FETCH NEXT n ROWS ONLY
      - CURRENT_DATE()    -> GETDATE()
      - NULLS LAST/FIRST  -> removed (T-SQL has no direct equivalent)
      - ILIKE             -> LIKE (case sensitivity depends on collation)
    """
    if not sql or not str(sql).strip():
        return sql

    s = str(sql).strip()

    # Snowflake / ANSI date functions
    s = s.replace("CURRENT_DATE()", "GETDATE()")
    s = re.sub(r"\bCURRENT_TIMESTAMP\s*\(\s*\)", "GETDATE()", s, flags=re.IGNORECASE)
    s = re.sub(r"\bCURRENT_TIMESTAMP\b", "GETDATE()", s, flags=re.IGNORECASE)

    # Snowflake ordering modifiers
    s = re.sub(r"\bNULLS\s+LAST\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNULLS\s+FIRST\b", "", s, flags=re.IGNORECASE)

    # ILIKE -> LIKE (Fabric default collation is often case-insensitive)
    s = re.sub(r"\bILIKE\b", "LIKE", s, flags=re.IGNORECASE)

    # LIMIT n OFFSET m  (requires ORDER BY in T-SQL)
    offset_match = re.search(
        r"(\bORDER\s+BY\b.+?)\s+LIMIT\s+(\d+)\s+OFFSET\s+(\d+)\s*;?\s*$",
        s,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if offset_match:
        order_clause = offset_match.group(1).strip()
        limit_n = offset_match.group(2)
        offset_m = offset_match.group(3)
        s = re.sub(
            r"\bORDER\s+BY\b.+?\s+LIMIT\s+\d+\s+OFFSET\s+\d+\s*;?\s*$",
            f"{order_clause} OFFSET {offset_m} ROWS FETCH NEXT {limit_n} ROWS ONLY",
            s,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return s.rstrip(";")

    # LIMIT n at end of query
    limit_match = re.search(r"\bLIMIT\s+(\d+)\s*;?\s*$", s, flags=re.IGNORECASE)
    if limit_match:
        limit_n = limit_match.group(1)
        s = re.sub(r"\bLIMIT\s+\d+\s*;?\s*$", "", s, flags=re.IGNORECASE).rstrip()

        if re.search(r"\bORDER\s+BY\b", s, flags=re.IGNORECASE):
            s = f"{s} OFFSET 0 ROWS FETCH NEXT {limit_n} ROWS ONLY"
        else:
            s = re.sub(
                r"\bSELECT\b",
                f"SELECT TOP {limit_n}",
                s,
                count=1,
                flags=re.IGNORECASE,
            )

    return s.rstrip(";")


def ensure_top_limit(sql: str, default_limit: int = 500) -> str:
    """Append a row cap when the query has no LIMIT/TOP/OFFSET FETCH."""
    if not sql:
        return sql
    upper = sql.upper()
    if any(tok in upper for tok in (" TOP ", " LIMIT ", " OFFSET ", " FETCH NEXT ")):
        return sql
    base = sql.rstrip(";").strip()
    return f"{base}\nOFFSET 0 ROWS FETCH NEXT {default_limit} ROWS ONLY"