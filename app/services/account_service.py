import json

import psycopg2.extras

from app.database import get_connection


def fetch_account(account_id: str) -> dict | None:
    """Fetch an account row from the DB and parse its metadata JSON.

    CODE IS CORRECT — json.loads is the right call here.
    JSONDecodeError is raised only because ACC-003 and ACC-005 have
    corrupted metadata stored in the database (bad ORM serialisation on
    ACC-003, truncated write on ACC-005).
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT account_id, owner, balance, currency, metadata, status "
                "FROM accounts WHERE account_id = %s",
                (account_id,),
            )
            row = cur.fetchone()

        if row is None:
            return None

        # Correct code: TEXT column must be deserialised before returning.
        # Corrupted rows make json.loads raise JSONDecodeError here.
        parsed_metadata = json.loads(row["metadata"])

        return {
            "account_id": row["account_id"],
            "owner":      row["owner"],
            "balance":    float(row["balance"]),  # NUMERIC comes back as Decimal
            "currency":   row["currency"],
            "metadata":   parsed_metadata,
            "status":     row["status"],
        }
    finally:
        conn.close()
