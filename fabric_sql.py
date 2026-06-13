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
      - CURRENT_DATE()    -> CAST(GETDATE() AS DATE)
      - CURRENT_TIMESTAMP -> GETDATE()
      - NULLS LAST/FIRST  -> removed (T-SQL has no direct equivalent)
      - ILIKE             -> LIKE (NOTE: Fabric Warehouse default collation
                              is case-SENSITIVE (Latin1_General_100_BIN2_UTF8),
                              so ILIKE -> LIKE changes matching behavior.
                              Wrap both sides in UPPER()/LOWER() if
                              case-insensitive matching is required.)
    """
    if not sql or not str(sql).strip():
        return sql

    s = str(sql).strip()

    # Snowflake / ANSI date functions
    s = re.sub(r"\bCURRENT_DATE\s*\(\s*\)", "CAST(GETDATE() AS DATE)", s, flags=re.IGNORECASE)
    s = re.sub(r"\bCURRENT_TIMESTAMP\s*\(\s*\)", "GETDATE()", s, flags=re.IGNORECASE)
    s = re.sub(r"\bCURRENT_TIMESTAMP\b", "GETDATE()", s, flags=re.IGNORECASE)

    # Snowflake ordering modifiers (no direct T-SQL equivalent)
    s = re.sub(r"\bNULLS\s+LAST\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNULLS\s+FIRST\b", "", s, flags=re.IGNORECASE)

    # ILIKE -> LIKE
    # Caution: Fabric Warehouse default collation is case-sensitive,
    # so this is NOT a behavior-preserving conversion. Caller should
    # apply UPPER()/LOWER() on both operands if needed.
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
            s = _inject_top(s, limit_n)

    return s.rstrip(";")


def _inject_top(sql: str, limit_n: str) -> str:
    """
    Insert TOP (n) right after the SELECT keyword that starts the
    OUTERMOST query, not the first SELECT encountered (which may
    belong to a leading CTE, e.g. `WITH cte AS (SELECT ...) SELECT ...`).
    """
    # If the query starts with a CTE (WITH ... AS (...)), find the
    # SELECT that follows the matching closing paren of the CTE block(s).
    stripped = sql.lstrip()
    if re.match(r"^\bWITH\b", stripped, flags=re.IGNORECASE):
        # Walk past balanced parens for each CTE definition until we
        # reach the final top-level SELECT.
        idx = 0
        depth = 0
        in_parens_started = False
        for m in re.finditer(r"[()]", stripped):
            ch = m.group()
            if ch == "(":
                depth += 1
                in_parens_started = True
            else:
                depth -= 1
            idx = m.end()
            if in_parens_started and depth == 0:
                # Check if the next non-comma/whitespace token starts
                # another CTE (", name AS (") or the final SELECT.
                rest = stripped[idx:].lstrip()
                if re.match(r"^,", rest):
                    in_parens_started = False
                    continue
                break

        head, tail = stripped[:idx], stripped[idx:]
        tail = re.sub(r"\bSELECT\b", f"SELECT TOP {limit_n}", tail, count=1, flags=re.IGNORECASE)
        return head + tail

    return re.sub(r"\bSELECT\b", f"SELECT TOP {limit_n}", sql, count=1, flags=re.IGNORECASE)


def ensure_top_limit(sql: str, default_limit: int = 500) -> str:
    """
    Append a row cap when the query has no TOP / LIMIT / OFFSET..FETCH.

    - If the query has an ORDER BY, OFFSET/FETCH is valid -> append it.
    - If there's no ORDER BY, OFFSET/FETCH is NOT valid in T-SQL,
      so inject TOP (n) into the SELECT instead.
    """
    if not sql:
        return sql

    upper = sql.upper()
    has_top = re.search(r"\bTOP\s*\(", upper) is not None or " TOP " in upper
    has_limit_or_fetch = any(
        tok in upper for tok in ("LIMIT ", " OFFSET ", "FETCH NEXT", "FETCH FIRST")
    )
    if has_top or has_limit_or_fetch:
        return sql

    base = sql.rstrip(";").strip()

    if re.search(r"\bORDER\s+BY\b", base, flags=re.IGNORECASE):
        return f"{base}\nOFFSET 0 ROWS FETCH NEXT {default_limit} ROWS ONLY"

    return _inject_top(base, str(default_limit))