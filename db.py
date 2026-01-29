# db.py
import os
import re
import streamlit as st
import psycopg
from psycopg.rows import tuple_row
from psycopg_pool import ConnectionPool

# =====================================================
# DB URL
# =====================================================
def _get_db_url() -> str:
    """Read DATABASE_URL from Streamlit secrets first, then environment variable."""
    db_url = None
    try:
        db_url = st.secrets.get("DATABASE_URL", None)
    except Exception:
        db_url = None

    if not db_url:
        db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        raise RuntimeError(
            "DATABASE_URL not set. "
            "Local: put it in .streamlit/secrets.toml. "
            "Cloud: set it as a secret named DATABASE_URL."
        )
    return str(db_url).strip()


# =====================================================
# Connection Pool (create once per app lifecycle)
# =====================================================
@st.cache_resource
def get_pool() -> ConnectionPool:
    db_url = _get_db_url()

    # Keep pool small to avoid exhausting Supabase connections on Streamlit reruns
    pool = ConnectionPool(
        conninfo=db_url,
        min_size=1,
        max_size=2,
        timeout=10,  # seconds to wait for a free connection
        kwargs={
            "sslmode": "require",
            "connect_timeout": 10,
            "autocommit": False,
            "row_factory": tuple_row,
        },
    )
    return pool


def get_conn():
    """Return a pooled connection context manager."""
    return get_pool().connection()


# =====================================================
# Init DB
# =====================================================
def init_db():
    """Create table and indexes if not exists."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS compounds (
                    id SERIAL PRIMARY KEY,
                    english_name TEXT NOT NULL,
                    formula TEXT,
                    mw DOUBLE PRECISION,
                    cas TEXT,
                    package_size TEXT,
                    location TEXT,
                    location_detail TEXT,
                    lid_color TEXT,
                    appearance TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )

            # Indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_compounds_english_name ON compounds (english_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_compounds_cas ON compounds (cas)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_compounds_location ON compounds (location)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_compounds_created_at ON compounds (created_at DESC)")

        conn.commit()


# =====================================================
# Insert / Delete
# =====================================================
def insert_compound(
    english_name: str,
    formula: str,
    mw,
    cas: str,
    package_size: str,
    location: str,
    location_detail: str,
    lid_color: str,
    appearance: str,
):
    """Insert a compound row (mw can be None)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO compounds (
                    english_name, formula, mw, cas,
                    package_size, location, location_detail,
                    lid_color, appearance
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    english_name,
                    formula,
                    mw,
                    cas,
                    package_size,
                    location,
                    location_detail,
                    lid_color,
                    appearance,
                ),
            )
        conn.commit()


def delete_compound(compound_id: int):
    """Delete by id (safest)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM compounds WHERE id = %s", (compound_id,))
        conn.commit()


# =====================================================
# Search
# =====================================================
# Treat query as CAS-like only if it's digits and hyphens (e.g. "75", "75-", "75-07", "75-07-0")
_CAS_QUERY_RE = re.compile(r"^[0-9\-]+$")


def search_compounds(q: str = "", location: str = "All", lid_color: str = "All"):
    """
    Search logic:
    - If q looks like a CAS query (only digits and '-'):
        cas must START WITH q (prefix match)
        e.g. q="75" -> matches "75-59-2" and "7598-35-8"
                    -> NOT match "7789-75-5"
    - Otherwise: contains search across english_name/formula/cas.
    - Result ordering: sort by CAS numerically (NULL/empty CAS goes last).
    """
    sql = """
    SELECT id, english_name, formula, mw, cas,
           package_size, location, location_detail,
           lid_color, appearance, created_at
    FROM compounds
    WHERE 1=1
    """
    params = []

    if q and q.strip():
        q = q.strip()
        is_cas_query = bool(_CAS_QUERY_RE.match(q))

        if is_cas_query:
            # ✅ CAS prefix match ONLY (no contains)
            sql += " AND cas ILIKE %s"
            params.append(f"{q}%")
        else:
            # ✅ General contains match
            like = f"%{q}%"
            sql += " AND (english_name ILIKE %s OR formula ILIKE %s OR cas ILIKE %s)"
            params += [like, like, like]

    if location != "All":
        sql += " AND location = %s"
        params.append(location)

    if lid_color != "All":
        sql += " AND lid_color = %s"
        params.append(lid_color)

    # ✅ Sort by CAS numerically; put NULL/empty CAS last
    sql += """
    ORDER BY
      CASE WHEN cas IS NULL OR cas = '' THEN 1 ELSE 0 END,
      split_part(cas, '-', 1)::int,
      split_part(cas, '-', 2)::int,
      split_part(cas, '-', 3)::int
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
