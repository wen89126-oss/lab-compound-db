# db.py
import os
import re
import streamlit as st
import psycopg
from psycopg.rows import tuple_row
from psycopg_pool import ConnectionPool

# -----------------------------
# Read DATABASE_URL
# -----------------------------
def _get_db_url() -> str:
    # 先讀 Streamlit secrets，再讀環境變數
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


# -----------------------------
# Connection pool (create once)
# -----------------------------
@st.cache_resource
def get_pool() -> ConnectionPool:
    db_url = _get_db_url()

    # ✅ 小型 app 建議 max_size 1~3，避免 Streamlit rerun 造成連線爆掉
    # ✅ timeout 控制拿連線的等待時間
    pool = ConnectionPool(
        conninfo=db_url,
        min_size=1,
        max_size=2,
        timeout=10,
        kwargs={
            "sslmode": "require",
            "connect_timeout": 10,
            "autocommit": False,
            "row_factory": tuple_row,
        },
    )
    return pool


def get_conn():
    # psycopg_pool 的 connection() 是 context manager
    return get_pool().connection()


# -----------------------------
# Init DB
# -----------------------------
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

            # 索引：查詢會快很多
            cur.execute("CREATE INDEX IF NOT EXISTS idx_compounds_english_name ON compounds (english_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_compounds_cas ON compounds (cas)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_compounds_location ON compounds (location)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_compounds_created_at ON compounds (created_at DESC)")

        conn.commit()


# -----------------------------
# Insert / Delete
# -----------------------------
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


# -----------------------------
# Search
# -----------------------------
_CAS_LIKE_RE = re.compile(r"^[0-9\-]+$")

def search_compounds(q: str = "", location: str = "All", lid_color: str = "All"):
    """
    查詢資料：
    - english_name / formula：模糊搜尋（contains）
    - cas：如果輸入看起來像 CAS（只含數字與 -），則改用「開頭匹配」(prefix)
      例：輸入 75 -> 只回傳 75-xx-x，不會回傳 2675-xx-x
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

        # 判斷是不是 CAS 查詢（只由數字與 - 組成）
        is_cas_query = bool(_CAS_LIKE_RE.match(q))

        if is_cas_query:
            # ✅ CAS：只做 prefix match（開頭比對）
            # ILIKE 讓大小寫不敏感（雖然 CAS 理論上只會是數字和 -）
            sql += " AND cas ILIKE %s"
            params.append(f"{q}%")
        else:
            # ✅ 一般查詢：english_name / formula / cas 模糊搜尋
            like = f"%{q}%"
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
