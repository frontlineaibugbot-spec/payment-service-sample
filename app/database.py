import json

import psycopg2
import psycopg2.extras

from app.config import DATABASE_URL


def get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(DATABASE_URL)


def init_db() -> None:
    """Create the accounts table and seed it with valid and corrupted rows."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id VARCHAR PRIMARY KEY,
                    owner      VARCHAR  NOT NULL,
                    balance    NUMERIC  NOT NULL,
                    currency   VARCHAR  NOT NULL,
                    metadata   TEXT     NOT NULL,
                    status     VARCHAR  NOT NULL
                )
            """)
            seed_rows = [
                # ── valid rows ────────────────────────────────────────────────
                (
                    "ACC-001", "Alice Smith", 1500.00, "USD",
                    json.dumps({"tier": "premium",  "kyc_verified": True,  "last_login": "2025-01-10T08:30:00Z"}),
                    "active",
                ),
                (
                    "ACC-002", "Bob Johnson", 320.75, "EUR",
                    json.dumps({"tier": "standard", "kyc_verified": True,  "last_login": "2025-01-08T14:20:00Z"}),
                    "active",
                ),
                (
                    "ACC-004", "Dave Brown", 0.00, "USD",
                    json.dumps({"tier": "basic",    "kyc_verified": False, "last_login": "2024-12-01T09:00:00Z"}),
                    "suspended",
                ),
                # ── corrupted rows (invalid JSON written during a previous incident) ──
                (
                    "ACC-003", "Carol White", 9999.99, "GBP",
                    # unquoted keys + non-JSON boolean — simulates a partial ORM serialisation bug
                    "{tier: premium, kyc_verified: yes, last_login: 2025-01-09}",
                    "active",
                ),
                (
                    "ACC-005", "Eve Davis", 2750.50, "USD",
                    # truncated write — simulates a DB crash mid-INSERT
                    '{"tier": "gold", "kyc_verified": true, "last_login":',
                    "active",
                ),
            ]
            for row in seed_rows:
                cur.execute(
                    """
                    INSERT INTO accounts (account_id, owner, balance, currency, metadata, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (account_id) DO NOTHING
                    """,
                    row,
                )
        conn.commit()
    finally:
        conn.close()
