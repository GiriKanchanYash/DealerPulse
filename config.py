

import os
import yaml
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# ---------------------------------------------------------------------------
# Optional Azure Key Vault integration
# Set AZURE_KEY_VAULT_URL in the environment to enable Key Vault resolution.
# If the Key Vault is unreachable, the module falls back to environment
# variables so local development still works without a vault.
# ---------------------------------------------------------------------------

def _strip_quotes(value: str | None) -> str | None:
    """
    Strip surrounding double or single quotes that some .env editors add.
    e.g.  FABRIC_SQL_SERVER="server.com"  ->  server.com
    """
    if value and len(value) >= 2:
        if (value[0] == '"' and value[-1] == '"') or            (value[0] == "'" and value[-1] == "'"):
            return value[1:-1]
    return value


def _fetch_vault_secret(vault_url: str, secret_name: str) -> str | None:
    """Return a secret value from Azure Key Vault, or None on any error."""
    try:
        from azure.identity import DefaultAzureCredential, ClientSecretCredential
        from azure.keyvault.secrets import SecretClient

        tenant_id = os.getenv("AZURE_TENANT_ID")
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")

        if tenant_id and client_id and client_secret:
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )
        else:
            credential = DefaultAzureCredential()

        client = SecretClient(vault_url=vault_url, credential=credential)
        return client.get_secret(secret_name).value
    except Exception:
        return None


class _VaultResolver:
    """
    Thin wrapper that resolves a value first from Key Vault (when
    AZURE_KEY_VAULT_URL is set) and then from environment variables.

    Secret names in Key Vault must match the environment variable names
    but with underscores replaced by hyphens, e.g.
      AZURE_OPENAI_API_KEY  ->  azure-openai-api-key
    """

    def __init__(self):
        self._vault_url = os.getenv("AZURE_KEY_VAULT_URL")
        self._cache: dict[str, str | None] = {}

    def get(self, env_var: str, default: str = "") -> str:
        if env_var in self._cache:
            return self._cache[env_var] or default

        value = None
        if self._vault_url:
            secret_name = env_var.lower().replace("_", "-")
            value = _fetch_vault_secret(self._vault_url, secret_name)

        if not value:
            value = os.getenv(env_var)

        value = _strip_quotes(value)
        self._cache[env_var] = value
        return value or default


_vault = _VaultResolver()


# ---------------------------------------------------------------------------
# App settings loaded from YAML (requirement 10, 15)
# ---------------------------------------------------------------------------

def _load_app_settings(path: str = "app_settings.yaml") -> dict:
    """Load app_settings.yaml; return empty dict if missing."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}


_settings = _load_app_settings()


class Config:
    """
    Central application configuration.

    Resolution priority for secrets:
      1. Azure Key Vault  (if AZURE_KEY_VAULT_URL is set)
      2. Environment variables  (.env or OS env)
      3. Hard-coded defaults  (non-sensitive values only)

    All user-visible strings and tunables come from app_settings.yaml.
    """

    # ------------------------------------------------------------------
    # Microsoft Fabric - Lakehouse (read-only analytics endpoint)
    # ------------------------------------------------------------------
    FABRIC_SQL_SERVER: str = _vault.get(
        "FABRIC_SQL_SERVER",
        _settings.get("fabric", {}).get("sql_server", ""),
    )
    FABRIC_DATABASE: str = _vault.get(
        "FABRIC_DATABASE",
        _settings.get("fabric", {}).get("database", "LH_PROCURE_SPEND_IQ"),
    )

    # Warehouse (read + write: history, insights, cache)
    FABRIC_WAREHOUSE_SERVER: str = _vault.get(
        "FABRIC_WAREHOUSE_SERVER",
        # Fall back to the Lakehouse server if warehouse server not separately configured
        _vault.get("FABRIC_SQL_SERVER",
                   _settings.get("fabric", {}).get("sql_server", "")),
    )
    FABRIC_WAREHOUSE_DATABASE: str = _vault.get(
        "FABRIC_WAREHOUSE_DATABASE",
        _settings.get("fabric", {}).get("warehouse_database", "WH_PROCURE_SPEND_IQ"),
    )

    # Schema names
    SCHEMA: str = _settings.get("fabric", {}).get("schema", "INFORMATION_MART")
    WAREHOUSE_SCHEMA: str = _settings.get("fabric", {}).get("warehouse_schema", "dbo")

    # ------------------------------------------------------------------
    # Azure OpenAI
    # ------------------------------------------------------------------
    AZURE_OPENAI_ENDPOINT: str = _vault.get("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_KEY: str = _vault.get("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_DEPLOYMENT: str = _vault.get(
        "AZURE_OPENAI_DEPLOYMENT",
        _settings.get("ai", {}).get("deployment", "gpt-4.1"),
    )
    AZURE_OPENAI_API_VERSION: str = _vault.get(
        "AZURE_OPENAI_API_VERSION",
        _settings.get("ai", {}).get("api_version", "2024-08-01-preview"),
    )

    # ------------------------------------------------------------------
    # Azure AD / Entra ID - Service Principal
    # ------------------------------------------------------------------
    AZURE_TENANT_ID: str = _vault.get("AZURE_TENANT_ID", "")
    AZURE_CLIENT_ID: str = _vault.get("AZURE_CLIENT_ID", "")
    AZURE_CLIENT_SECRET: str = _vault.get("AZURE_CLIENT_SECRET", "")

    # ------------------------------------------------------------------
    # Azure Key Vault URL (optional - enables vault-first secret lookup)
    # ------------------------------------------------------------------
    AZURE_KEY_VAULT_URL: str = os.getenv("AZURE_KEY_VAULT_URL", "")

    # ------------------------------------------------------------------
    # AI model aliases and generation settings
    # ------------------------------------------------------------------
    # Model used for natural-language → SQL generation
    SQL_MODEL: str = _vault.get(
        "SQL_MODEL",
        _settings.get("ai", {}).get("sql_model", AZURE_OPENAI_DEPLOYMENT),
    ) or AZURE_OPENAI_DEPLOYMENT

    # Model used for prescriptive / narrative completions
    PRESCRIPTIVE_MODEL: str = _vault.get(
        "PRESCRIPTIVE_MODEL",
        _settings.get("ai", {}).get("prescriptive_model", AZURE_OPENAI_DEPLOYMENT),
    ) or AZURE_OPENAI_DEPLOYMENT

    # Temperature for SQL generation — 0.0 keeps queries deterministic
    SQL_GENERATION_TEMPERATURE: float = float(
        _vault.get(
            "SQL_GENERATION_TEMPERATURE",
            str(_settings.get("ai", {}).get("sql_generation_temperature", 0.0)),
        )
        or 0.0
    )

    # ------------------------------------------------------------------
    # Application UI strings loaded from app_settings.yaml (req 10, 12)
    # ------------------------------------------------------------------
    _ui = _settings.get("ui", {})

    APP_TITLE: str        = _ui.get("app_title", "ProcureIQ Analytics")
    PAGE_ICON_URL: str    = _ui.get("page_icon_url", "")
    DEFAULT_BG_COLOR: str = _ui.get("default_bg_color", "#FBF9F4")
    BRAND_NAME: str       = _ui.get("brand_name", "ProcureIQ")
    SUPPORT_EMAIL: str    = _ui.get("support_email", "")
    APP_REGION: str       = _ui.get("region", "eastus")

    # ------------------------------------------------------------------
    # Metadata / schema file (req 15 - configurable)
    # ------------------------------------------------------------------
    SCHEMA_METADATA_FILE: str = _settings.get(
        "metadata", {}
    ).get("schema_file", "schema_metadata.yaml")

    # Data Vault layer names used in YAML generation (req 5, 7)
    DATA_VAULT_HUB_PREFIX: str    = _settings.get("data_vault", {}).get("hub_prefix", "HUB_")
    DATA_VAULT_SAT_PREFIX: str    = _settings.get("data_vault", {}).get("sat_prefix", "SAT_")
    DATA_VAULT_LINK_PREFIX: str   = _settings.get("data_vault", {}).get("link_prefix", "LNK_")
    DATA_VAULT_BRIDGE_PREFIX: str = _settings.get("data_vault", {}).get("bridge_prefix", "BRG_")

    # ------------------------------------------------------------------
    # Caching (req 3, 8)
    # ------------------------------------------------------------------
    _cache = _settings.get("cache", {})
    CACHE_ENABLED: bool       = _cache.get("enabled", True)
    CACHE_TTL_SECONDS: int    = _cache.get("ttl_seconds", 3600)
    CACHE_MAX_ROWS: int       = _cache.get("max_result_rows", 5000)
    SESSION_CACHE_TABLE: str  = _cache.get(
        "session_cache_table", "dbo.query_result_cache"
    )

    # ------------------------------------------------------------------
    # Feature flags
    # ------------------------------------------------------------------
    _features = _settings.get("features", {})
    ENABLE_GENIE_HISTORY: bool = _features.get("genie_history", True)
    ENABLE_INSIGHTS_SAVE: bool = _features.get("insights_save", True)
    ENABLE_DATA_VAULT_AI: bool = _features.get("data_vault_ai", True)
    ENABLE_AUTO_YAML: bool     = _features.get("auto_yaml_update", True)

    # ------------------------------------------------------------------
    # Auto-suspend (req 14)
    # ------------------------------------------------------------------
    IDLE_TIMEOUT_SECONDS: int = _settings.get("session", {}).get(
        "idle_timeout_seconds", 300
    )

    # ------------------------------------------------------------------
    # Naming conventions (req 11) - shared across all environments
    # ------------------------------------------------------------------
    _naming = _settings.get("naming_conventions", {})
    TABLE_PREFIX_FACT: str     = _naming.get("fact_prefix", "FACT_")
    TABLE_PREFIX_DIM: str      = _naming.get("dim_prefix", "DIM_")
    TABLE_SUFFIX_VIEW: str     = _naming.get("view_suffix", "_VW")
    HISTORY_TABLE_NAME: str    = _naming.get("history_table", "GENIE_QUESTION_HISTORY")
    SAVED_INSIGHTS_TABLE: str  = _naming.get("saved_insights_table", "SAVED_INSIGHTS")
    CACHE_TABLE_NAME: str      = _naming.get("cache_table", "QUERY_RESULT_CACHE")
    GENIE_CONTEXT_MEMORY_TABLE: str = _naming.get("genie_context_memory_table", "GENIE_CONTEXT_MEMORY")

    # ------------------------------------------------------------------
    # Genie Contextual Memory Configuration
    # ------------------------------------------------------------------

    _memory = _settings.get("memory", {})

    SHORT_TERM_MEMORY_ENABLED: bool = (
        _memory.get("short_term", {}).get("enabled", True)
    )

    SHORT_TERM_MEMORY_MAX_MESSAGES: int = (
        _memory.get("short_term", {}).get("max_messages", 10)
    )

    SHORT_TERM_MEMORY_WINDOW_MINUTES: int = (
        _memory.get("short_term", {}).get("window_minutes", 15)
    )

    LONG_TERM_MEMORY_ENABLED: bool = (
        _memory.get("long_term", {}).get("enabled", True)
    )

    LONG_TERM_MEMORY_MAX_CONTEXTS: int = (
        _memory.get("long_term", {}).get("max_contexts", 5000)
    )

    LONG_TERM_MEMORY_TABLE: str = (
        _memory.get("long_term", {}).get(
            "table", "genie_context_memory"
        )
    )

    GENIE_CONTEXT_WINDOW_SIZE: int = (
        _memory.get("genie", {}).get("context_window_size", 5)
    )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @classmethod
    def validate(cls) -> bool:
        errors = []
        for attr, label in [
            ("FABRIC_SQL_SERVER",      "FABRIC_SQL_SERVER"),
            ("FABRIC_DATABASE",        "FABRIC_DATABASE"),
            ("AZURE_TENANT_ID",        "AZURE_TENANT_ID"),
            ("AZURE_CLIENT_ID",        "AZURE_CLIENT_ID"),
            ("AZURE_CLIENT_SECRET",    "AZURE_CLIENT_SECRET"),
            ("AZURE_OPENAI_ENDPOINT",  "AZURE_OPENAI_ENDPOINT"),
            ("AZURE_OPENAI_API_KEY",   "AZURE_OPENAI_API_KEY"),
        ]:
            if not getattr(cls, attr):
                errors.append(f"{label} is not configured")

        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
        return True

    @classmethod
    def validate_connection_values(cls) -> list[str]:
        """
        Return a list of human-readable diagnostics about the current
        connection configuration.  Useful for the VS Code terminal check:
            python -c "from config import Config; Config.print_diagnostics()"
        """
        lines = []
        def mask(v: str) -> str:
            if not v:
                return "(NOT SET)"
            if len(v) <= 8:
                return "*" * len(v)
            return v[:4] + "*" * (len(v) - 8) + v[-4:]

        lines.append(f"FABRIC_SQL_SERVER        : {mask(cls.FABRIC_SQL_SERVER)}")
        lines.append(f"FABRIC_DATABASE          : {cls.FABRIC_DATABASE or '(NOT SET)'}")
        lines.append(f"FABRIC_WAREHOUSE_SERVER  : {mask(cls.FABRIC_WAREHOUSE_SERVER)}")
        lines.append(f"FABRIC_WAREHOUSE_DATABASE: {cls.FABRIC_WAREHOUSE_DATABASE or '(NOT SET)'}")
        lines.append(f"AZURE_TENANT_ID          : {mask(cls.AZURE_TENANT_ID)}")
        lines.append(f"AZURE_CLIENT_ID          : {mask(cls.AZURE_CLIENT_ID)}")
        lines.append(f"AZURE_CLIENT_SECRET      : {mask(cls.AZURE_CLIENT_SECRET)}")
        lines.append(f"AZURE_OPENAI_ENDPOINT    : {cls.AZURE_OPENAI_ENDPOINT or '(NOT SET)'}")
        lines.append(f"AZURE_OPENAI_DEPLOYMENT  : {cls.AZURE_OPENAI_DEPLOYMENT or '(NOT SET)'}")
        return lines

    @classmethod
    def print_diagnostics(cls) -> None:
        """Print masked config values to the terminal for quick troubleshooting."""
        print("\n=== ProcureIQ Configuration Diagnostics ===")
        for line in cls.validate_connection_values():
            print(" ", line)
        missing = [
            name for name, attr in [
                ("FABRIC_SQL_SERVER",   cls.FABRIC_SQL_SERVER),
                ("FABRIC_DATABASE",     cls.FABRIC_DATABASE),
                ("AZURE_TENANT_ID",     cls.AZURE_TENANT_ID),
                ("AZURE_CLIENT_ID",     cls.AZURE_CLIENT_ID),
                ("AZURE_CLIENT_SECRET", cls.AZURE_CLIENT_SECRET),
                ("AZURE_OPENAI_ENDPOINT", cls.AZURE_OPENAI_ENDPOINT),
                ("AZURE_OPENAI_API_KEY",  cls.AZURE_OPENAI_API_KEY),
            ] if not attr
        ]
        if missing:
            print("\n  MISSING VALUES:", ", ".join(missing))
            print("  Check your .env file - values must NOT have surrounding quotes on Windows.")
            print('  Correct:   FABRIC_SQL_SERVER=server.fabric.microsoft.com')
            print('  Wrong:     FABRIC_SQL_SERVER="server.fabric.microsoft.com"')
        else:
            print("\n  All required values are present.")
        print("=================================================\n")

    # ------------------------------------------------------------------
    # Connection strings
    # ------------------------------------------------------------------
    @classmethod
    def get_connection_string(cls) -> str:
        return (
            f"Driver={{ODBC Driver 18 for SQL Server}};"
            f"Server={cls.FABRIC_SQL_SERVER};"
            f"Database={cls.FABRIC_DATABASE};"
            f"Authentication=ActiveDirectoryServicePrincipal;"
            f"UID={cls.AZURE_CLIENT_ID};"
            f"PWD={cls.AZURE_CLIENT_SECRET};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
            f"Connection Timeout=30;"
        )

    @classmethod
    def get_warehouse_connection_string(cls) -> str:
        return (
            f"Driver={{ODBC Driver 18 for SQL Server}};"
            f"Server={cls.FABRIC_WAREHOUSE_SERVER};"
            f"Database={cls.FABRIC_WAREHOUSE_DATABASE};"
            f"Authentication=ActiveDirectoryServicePrincipal;"
            f"UID={cls.AZURE_CLIENT_ID};"
            f"PWD={cls.AZURE_CLIENT_SECRET};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
            f"Connection Timeout=30;"
        )


# Validate on import (warn only; do not crash on partial config)
if __name__ != "__main__":
    try:
        Config.validate()
    except ValueError as e:
        print(f"Configuration warning: {e}")
        print("Ensure environment variables or Azure Key Vault secrets are set.")
