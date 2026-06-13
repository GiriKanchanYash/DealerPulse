from __future__ import annotations

import json
import logging
import re
import textwrap
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import yaml
from openai import AzureOpenAI

from config import Config
from db_service import (
    cache_get,
    cache_set,
    get_table_columns,
    get_primary_keys,
    list_tables_in_schema,
    run_df,
    sql_escape,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Azure OpenAI client
# ---------------------------------------------------------------------------

_client = AzureOpenAI(
    azure_endpoint=Config.AZURE_OPENAI_ENDPOINT,
    api_key=Config.AZURE_OPENAI_API_KEY,
    api_version=Config.AZURE_OPENAI_API_VERSION,
)


# ---------------------------------------------------------------------------
# Emoji removal (ISSUE #3 FIX)
# ---------------------------------------------------------------------------

def _remove_emojis(text: str) -> str:
    """Remove all emoji characters from text."""
    if not isinstance(text, str):
        return str(text)
    
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Symbols
        "\U0001F680-\U0001F6FF"  # Transport
        "\U0001F1E0-\U0001F1FF"  # Flags
        "\u2500-\u27FF"          # Dingbats
        "\u2300-\u23FF"          # Technical
        "\u2600-\u27BF"          # Symbols
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub('', text).strip()


# ---------------------------------------------------------------------------
# Schema prompt builder
# ---------------------------------------------------------------------------

def load_schema_from_yaml(yaml_path: str | None = None) -> str:
    """Build SQL-generation system prompt from schema_metadata.yaml."""
    path = yaml_path or Config.SCHEMA_METADATA_FILE
    try:
        with open(path, "r", encoding="utf-8") as fh:
            schema_data = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.warning("Schema metadata file not found: %s", path)
        return (
            f"You are a SQL expert for Microsoft Fabric SQL (T-SQL).\n"
            f"DATABASE: {Config.FABRIC_DATABASE}\nSCHEMA: {Config.SCHEMA}\n"
            "Generate T-SQL SELECT queries only."
        )

    prompt = textwrap.dedent(f"""
        You are a SQL expert for Microsoft Fabric SQL (T-SQL).
        DATABASE: {Config.FABRIC_DATABASE}
        SCHEMA: {Config.SCHEMA}
    """)

    if "custom_instructions" in schema_data:
        prompt += schema_data["custom_instructions"] + "\n\n"

    prompt += "AVAILABLE TABLES:\n\n"

    for table in schema_data.get("tables", []):
        base = table.get("base_table", {})
        actual_schema = base.get("schema", Config.SCHEMA)
        actual_table  = base.get("table", "")

        prompt += f"Table: {actual_schema}.{actual_table}\n"
        prompt += f"Description: {table.get('description', '')}\n"
        prompt += "Columns:\n"

        for dim in table.get("dimensions", []):
            col  = dim.get("expr", dim.get("name", ""))
            dtype = dim.get("data_type", "varchar")
            desc = dim.get("description", "")
            prompt += f"  - {col} ({dtype}): {desc}\n"

        for measure in table.get("measures", []):
            col  = measure.get("expr", measure.get("name", ""))
            dtype = measure.get("data_type", "number")
            desc = measure.get("description", "")
            prompt += f"  - {col} ({dtype}): {desc}\n"

        prompt += "\n"

    if "verified_queries" in schema_data:
        prompt += "VERIFIED QUERIES:\n\n"
        for vq in schema_data.get("verified_queries", []):
            q   = vq.get("question", "")
            sql = vq.get("sql", "").strip()
            if q and sql:
                prompt += f"Q: {q}\nSQL: {sql}\n\n"

    prompt += textwrap.dedent("""
        RULES:
        1. Use fully qualified names: schema.table AND table.column
        2. ALWAYS qualify ALL columns with table alias (e.g., f.VENDOR_ID, v.VENDOR_NAME)
        3. In GROUP BY, HAVING, WHERE: ALWAYS use table.column format
        4. Only SELECT queries
        5. T-SQL: TOP N, DATETRUNC, GETDATE
        6. Return ONLY SQL
        7. CRITICAL: Never use unqualified column names when multiple tables are joined
    """)

    return prompt.replace("{schema}", Config.SCHEMA)


SYSTEM_PROMPT = load_schema_from_yaml()


# ---------------------------------------------------------------------------
# SQL generation
# ---------------------------------------------------------------------------

def _clean_sql(raw: str) -> str:
    """Clean SQL output."""
    sql = raw.replace("```sql", "").replace("```", "").strip()
    sql = sql.replace("CURRENT_DATE()", "GETDATE()")

    m = re.search(r"\bLIMIT\s+(\d+)", sql, re.IGNORECASE)
    if m:
        limit_n = m.group(1)
        sql = re.sub(r"\bLIMIT\s+\d+\b", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\bSELECT\b", f"SELECT TOP {limit_n}", sql, count=1, flags=re.IGNORECASE)

    sql = re.sub(r"\bCOUNT\s*\(\s*\)", "COUNT(*)", sql, flags=re.IGNORECASE)
    return sql


def generate_sql(user_question: str, temperature: float | None = None) -> str:
    """Convert natural language to T-SQL query (cache-first)."""
    cache_key = f"sql_cache:{user_question}"
    _cached = cache_get(cache_key)
    if _cached:
        logger.info("SQL cache hit")
        # db_service.cache_get returns a dict; the SQL is stored in the 'sql' key.
        # Guard against the old plain-string format for backwards compatibility.
        if isinstance(_cached, dict):
            return _cached.get("sql") or ""
        return str(_cached)

    temp = temperature or Config.SQL_GENERATION_TEMPERATURE
    try:
        response = _client.chat.completions.create(
            model=Config.SQL_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_question},
            ],
            temperature=temp,
            max_tokens=2000,
        )
        raw_sql = response.choices[0].message.content.strip()
    except Exception as exc:
        raise RuntimeError(f"Azure OpenAI API failed: {exc}") from exc

    sql = _clean_sql(raw_sql)

    if not re.match(r"^\s*(SELECT|WITH)\s+", sql, re.IGNORECASE):
        sql = "SELECT 'Please ask a specific question.' AS MESSAGE"

    # db_service.cache_set requires (question, sql, result_df).
    # For SQL-string caching there is no result DataFrame, so pass an empty one.
    cache_set(cache_key, sql, pd.DataFrame())
    return sql


# ---------------------------------------------------------------------------
# Generic AI completion (ISSUE #1 & #2 FIX)
# ---------------------------------------------------------------------------

def cortex_complete(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.3,
    include_memory: bool = False,
) -> str:
    """
    Azure OpenAI completion with optional memory context.
    
    FIXES:
      Issue #1: Proper session state handling (no Bad message format)
      Issue #2: Optional memory context injection from app.py session state
      Issue #3: All emojis removed from output
    """
    try:
        full_prompt = prompt

        # Optional memory context (Issue #2)
        if include_memory:
            try:
                import streamlit as st
                memory_text = ""
                
                if hasattr(st, 'session_state'):
                    # Safe access to session variables
                    if "genie_previous_sessions" in st.session_state:
                        sessions = st.session_state.genie_previous_sessions
                        if sessions:
                            memory_text = "PREVIOUS SESSIONS:\n"
                            for s in sessions[-2:]:
                                memory_text += f"- {s.get('query_count', 0)} queries\n"
                    
                    if "genie_queries" in st.session_state:
                        queries = st.session_state.genie_queries
                        if queries:
                            if memory_text:
                                memory_text += "\n"
                            memory_text += "RECENT QUESTIONS:\n"
                            for q in queries[-3:]:
                                memory_text += f"- {q.get('question', '')}\n"
                
                if memory_text:
                    # Single f-string, no adjacent strings (Issue #1)
                    full_prompt = f"{memory_text}\n---\n\n{prompt}"
            except Exception:
                # Fall back to original prompt if memory fails
                pass

        response = _client.chat.completions.create(
            model=model or Config.PRESCRIPTIVE_MODEL,
            messages=[{"role": "user", "content": full_prompt}],
            temperature=temperature,
        )

        result = response.choices[0].message.content.strip()
        
        # Issue #3: Remove emojis
        result = _remove_emojis(result)

        return result

    except Exception as exc:
        logger.error("AI completion failed: %s", exc)
        return ""

# ---------------------------------------------------------------------------
# Invoice AI suggestion (No emojis)
# ---------------------------------------------------------------------------

def generate_ai_invoice_suggestion(
    invoice_number: str,
    invoice_data: Dict,
    status_history: str = "",
) -> str:
    """Return actionable invoice suggestion."""
    prompt = textwrap.dedent(f"""
        Review this invoice and provide a 2-3 sentence recommendation.

        INVOICE: {invoice_number}
        STATUS: {invoice_data.get('INVOICE_STATUS', 'Unknown')}
        AMOUNT: {invoice_data.get('INVOICE_AMOUNT_LOCAL', 0):,.2f}
        VENDOR: {invoice_data.get('VENDOR_ID', 'Unknown')}
        DUE DATE: {invoice_data.get('DUE_DATE', 'Unknown')}
    """).strip()

    if status_history:
        prompt += f"\nHISTORY:\n{status_history}"

    return cortex_complete(prompt, temperature=0.5, include_memory=False)


# ---------------------------------------------------------------------------
# Data Vault enrichment
# ---------------------------------------------------------------------------

def _infer_data_vault_objects(
    table_name: str,
    columns: List[Dict],
    primary_keys: List[str],
) -> Dict:
    """Infer Data Vault structures."""
    col_descriptions = "\n".join(
        f"  - {col['COLUMN_NAME']}: {col.get('DATA_TYPE', 'unknown')}"
        for col in columns
    )
    pk_list = ", ".join(primary_keys) if primary_keys else "unknown"

    prompt = textwrap.dedent(f"""
        Data Vault architect. Given this schema, produce JSON.

        TABLE: {table_name}
        PRIMARY KEYS: {pk_list}
        COLUMNS:
        {col_descriptions}

        Return valid JSON only.
    """).strip()

    try:
        raw = cortex_complete(prompt, temperature=0.2, include_memory=False)
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Data Vault inference failed: %s", exc)
        return {}


def enrich_yaml_for_table(
    table_name: str,
    schema: str = "INFORMATION_MART",
    yaml_path: str | None = None,
) -> bool:
    """AI-driven YAML enrichment."""
    if not Config.ENABLE_DATA_VAULT_AI:
        return False

    yaml_path = yaml_path or Config.SCHEMA_METADATA_FILE

    try:
        with open(yaml_path, "r", encoding="utf-8") as fh:
            schema_data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        schema_data = {"tables": []}

    tables = schema_data.get("tables", [])
    existing = next(
        (t for t in tables if t.get("base_table", {}).get("table", "").upper() == table_name.upper()),
        None,
    )

    if existing and existing.get("data_vault"):
        return True

    cols_df = get_table_columns(table_name, schema)
    if cols_df.empty:
        return False

    pks = get_primary_keys(table_name, schema)
    columns = cols_df.to_dict("records")

    enrichment = _infer_data_vault_objects(table_name, columns, pks)
    if not enrichment:
        return False

    if not existing:
        new_entry = {
            "name": table_name.lower(),
            "description": f"Table: {schema}.{table_name}",
            "base_table": {"database": Config.FABRIC_DATABASE, "schema": schema, "table": table_name},
        }
        dims, measures = [], []
        for col in columns:
            col_name = col["COLUMN_NAME"]
            col_type = col["DATA_TYPE"].lower()
            if any(t in col_type for t in ("int", "float", "decimal", "numeric")):
                measures.append({"name": col_name.lower(), "expr": col_name, "data_type": "number"})
            else:
                dims.append({"name": col_name.lower(), "expr": col_name, "data_type": col_type})
        if dims:
            new_entry["dimensions"] = dims
        if measures:
            new_entry["measures"] = measures
        tables.append(new_entry)
        existing = tables[-1]

    if "data_vault" in enrichment:
        existing["data_vault"] = enrichment["data_vault"]

    schema_data["tables"] = tables

    try:
        with open(yaml_path, "w", encoding="utf-8") as fh:
            yaml.dump(schema_data, fh, default_flow_style=False, sort_keys=False)
        return True
    except Exception as exc:
        logger.error("Failed to write YAML: %s", exc)
        return False


def auto_discover_and_enrich_yaml(
    schema: str = "INFORMATION_MART",
    yaml_path: str | None = None,
) -> List[str]:
    """Auto-discover and enrich new tables."""
    yaml_path = yaml_path or Config.SCHEMA_METADATA_FILE
    processed = []

    try:
        with open(yaml_path, "r", encoding="utf-8") as fh:
            schema_data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        schema_data = {"tables": []}

    known_tables = {
        t.get("base_table", {}).get("table", "").upper()
        for t in schema_data.get("tables", [])
    }

    try:
        all_tables_df = list_tables_in_schema(schema)
    except Exception as exc:
        logger.error("Could not list tables: %s", exc)
        return processed

    for _, row in all_tables_df.iterrows():
        tname = str(row.get("TABLE_NAME", "")).strip().upper()
        if tname and tname not in known_tables:
            ok = enrich_yaml_for_table(tname, schema, yaml_path)
            if ok:
                processed.append(tname)

    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("LLM Service Module Ready")