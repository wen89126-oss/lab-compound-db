# db.py
import os
import psycopg

# 連線池（psycopg3 官方 pool 套件）
from psycopg_pool import ConnectionPool

# 先讀 Streamlit secrets（本機 .streamlit/secrets.toml）
try:
    import streamlit as st
    DATABASE_URL = st.secrets.get("DATABASE_URL", None)
except Exception:
    st = None
    DATABASE_URL = None

# 沒有 secrets 就讀環境變數（部署用）
if not DATABASE_URL:
    DATABASE_URL = os.environ.get("DATABASE_URL")


def _require_db_url() -> str:
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL not set. "
            "Local: put it in .streamlit/secrets.toml. "
            "Cloud: set it as a Secret named DATABASE_URL."
        )
    return DATABASE_URL


# ✅ 用 cache_resource：整個 app lifecycle 只建立一次 pool（超關鍵）
#    - Streamlit rerun 不會一直開新連線
#    - 大幅降低 OperationalError / too many connections / 偶發 timeout
if st is not None:
    @st.cache_resource
    def get_pool() -> ConnectionPool:
        db_url = _require_db_url()
        return ConnectionPool(
            conninfo=db_url,
            # 把 ssl / timeout 集中放這裡，避免跟 URL query 參數衝突
            kwargs={"sslmode": "require", "connect_timeout": 5},
            min_size=1,
            max_size=5,   # free tier DB 通常連線數很小，別設太大
            timeout=10,   # 借不到連線最多等 10 秒
        )
else:
    # 沒有 streamlit（例如純 python script 跑 init）就用全域 pool
    _GLOBAL_POOL = None

    def get_pool() -> ConnectionPool:
        global _GLOBAL_POOL
        if _GLOBAL_POOL is None:
            db_url = _require_db_url()
            _GLOBAL_POOL = ConnectionPool(
                conninfo=db_url,
                kwargs={"sslmode": "require", "connect_timeout": 5},
                min_size=1,
                max_size=5,
                timeout=10,
            )
        return _GLOBAL_POOL


def get_conn():
    """
    回傳一個可用在 `with get_conn() as conn:` 的連線 context manager
    會自動從 pool 借連線，用完歸還。
    """
    return get_pool().connection()


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
