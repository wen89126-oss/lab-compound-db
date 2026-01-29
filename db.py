import os
import psycopg
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


def test_db_connection():
    """
    直接用 psycopg.connect 測一次，目的就是把「真正錯誤」抓出來，
    不要被 pool 的 PoolTimeout 蓋住。
    """
    db_url = _require_db_url()
    try:
        with psycopg.connect(db_url, sslmode="require", connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        return True
    except Exception as e:
        # 這邊會在 Logs 顯示真正原因（例如 password failed / timeout / host 解析不到）
        raise RuntimeError(f"Direct DB connect test failed: {type(e).__name__}: {e}") from e


# ✅ 用 cache_resource：整個 app lifecycle 只建立一次 pool
if st is not None:
    @st.cache_resource
    def get_pool() -> ConnectionPool:
        # 先測一次真連線（抓真錯）
        test_db_connection()

        db_url = _require_db_url()
        pool = ConnectionPool(
            conninfo=db_url,
            kwargs={"sslmode": "require", "connect_timeout": 5},
            min_size=1,
            max_size=3,     # 先小一點，避免 free tier DB 連線數爆掉
            timeout=10,
            max_waiting=10,
        )

        # 等待 pool 真的建立出至少 min_size 的連線
        try:
            pool.wait(timeout=10)
        except Exception:
            # 再測一次 direct connect 把真錯抓出來
            test_db_connection()
            # 如果 direct connect OK，但 pool still fail，才丟 pool 的錯
            raise

        return pool
else:
    _GLOBAL_POOL = None

    def get_pool() -> ConnectionPool:
        global _GLOBAL_POOL
        if _GLOBAL_POOL is None:
            test_db_connection()
            db_url = _require_db_url()
            _GLOBAL_POOL = ConnectionPool(
                conninfo=db_url,
                kwargs={"sslmode": "require", "connect_timeout": 5},
                min_size=1,
                max_size=3,
                timeout=10,
                max_waiting=10,
            )
            _GLOBAL_POOL.wait(timeout=10)
        return _GLOBAL_POOL


def get_conn():
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
