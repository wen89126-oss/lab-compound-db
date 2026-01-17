import os
import psycopg

# 先讀 Streamlit secrets（本機 .streamlit/secrets.toml）
try:
    import streamlit as st
    DATABASE_URL = st.secrets.get("DATABASE_URL", None)
except Exception:
    DATABASE_URL = None

# 沒有 secrets 就讀環境變數（部署用）
if not DATABASE_URL:
    DATABASE_URL = os.environ.get("DATABASE_URL")


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL not set. "
            "Local: put it in .streamlit/secrets.toml. "
            "Cloud: set it as an environment variable/secret named DATABASE_URL."
        )
    # ✅ 防止卡住：5 秒內連不上就報錯
    return psycopg.connect(
        DATABASE_URL,
        sslmode="require",
        connect_timeout=5,
    )


def init_db():
    """建立資料表與索引（若不存在）"""
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

            # ✅ Index：資料變多後查詢差超多
            cur.execute("CREATE INDEX IF NOT EXISTS idx_compounds_english_name ON compounds (english_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_compounds_cas ON compounds (cas)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_compounds_location ON compounds (location)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_compounds_created_at ON compounds (created_at DESC)")

        conn.commit()


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
    """新增一筆化學品資料（mw 可為 None）"""
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
    """用 id 刪除一筆資料（最安全）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM compounds WHERE id = %s", (compound_id,))
        conn.commit()


def search_compounds(q: str = "", location: str = "All", lid_color: str = "All"):
    """查詢資料（不分大小寫）"""
    sql = """
    SELECT id, english_name, formula, mw, cas,
           package_size, location, location_detail,
           lid_color, appearance, created_at
    FROM compounds
    WHERE 1=1
    """
    params = []

    if q.strip():
        like = f"%{q.strip()}%"
        sql += " AND (english_name ILIKE %s OR formula ILIKE %s OR cas ILIKE %s)"
        params += [like, like, like]

    if location != "All":
        sql += " AND location = %s"
        params.append(location)

    if lid_color != "All":
        sql += " AND lid_color = %s"
        params.append(lid_color)

    sql += " ORDER BY created_at DESC"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
