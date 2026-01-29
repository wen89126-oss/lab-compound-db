import streamlit as st
import pandas as pd
from db import init_db, insert_compound, search_compounds, delete_compound

# -----------------------------
# Page
# -----------------------------
st.set_page_config(page_title="Chemical Storage Database", layout="wide")
st.title("🧪 Chemical Storage Database")

# -----------------------------
# Init DB once (safe)
# -----------------------------
@st.cache_resource
def _init_db_once():
    init_db()
    return True

try:
    _init_db_once()
    st.caption("Database status: ready ✅")
except Exception:
    st.caption("Database status: connected on demand (init skipped)")

# -----------------------------
# Options
# -----------------------------
LOCATIONS = [
    "Normal",
    "Solvent",
    "Salt and acid",
    "Dry box",
    "Hood",
    "4℃ fridge",
    "-20℃ fridge",
    "Glovebox",
    "Outside",
    "Other",
]
APPEARANCE = ["Solid", "Liquid", "Gas", "Other"]

LID_COLOR_OPTIONS = {
    "White": "⚪ White",
    "Black": "⚫ Black",
    "Red": "🔴 Red",
    "Blue": "🔵 Blue",
    "Yellow": "🟡 Yellow",
    "Other": "❓ Other",
}

def label_to_key(mapping: dict, label: str) -> str:
    for k, v in mapping.items():
        if v == label:
            return k
    return "Other"

# -----------------------------
# NO cached search (fix PoolTimeout)
# -----------------------------
def run_search(q: str, location: str, lid_color: str):
    return search_compounds(q=q, location=location, lid_color=lid_color)

# Keep last search inputs
if "last_search" not in st.session_state:
    st.session_state["last_search"] = {"q": "", "location": "All", "lid_color": "All", "ran": False}

# Tabs
tab_add, tab_search = st.tabs(["➕ 新增 (Add)", "🔎 查詢 (Search)"])

# ======================================================
# Add
# ======================================================
with tab_add:
    st.subheader("新增化學品 (Add chemical)")

    with st.form("add_form"):
        english_name = st.text_input("英文名 (English name)")
        cas = st.text_input("CAS")

        col1, col2 = st.columns(2)
        with col1:
            formula = st.text_input("分子式 (Formula)", placeholder="e.g., C8H10N4O2")
        with col2:
            mw_text = st.text_input("分子量 (Molecular weight, MW)", placeholder="e.g., 312.45")

        package_size = st.text_input("包裝大小 (Package size)", placeholder="e.g., 25 g / 100 mL")

        st.markdown("### 位置 (Location)")
        c1, c2 = st.columns([1, 2])
        with c1:
            location = st.selectbox("位置 (Location)", LOCATIONS)
        with c2:
            location_detail = st.text_input(
                "詳細位置 (Location detail)",
                placeholder="e.g., Box 3 / Shelf 2 / Vial 12",
            )

        colA, colB = st.columns(2)
        with colA:
            lid_color_label = st.selectbox("蓋子顏色 (Lid color)", list(LID_COLOR_OPTIONS.values()))
            lid_color = label_to_key(LID_COLOR_OPTIONS, lid_color_label)
        with colB:
            appearance = st.selectbox("性狀 (Appearance)", APPEARANCE)

        submitted = st.form_submit_button("💾 儲存 (Save)")

    if submitted:
        if not english_name.strip():
            st.error("請輸入英文名 (Please enter English name)")
        else:
            mw_value = None
            if mw_text.strip():
                try:
                    mw_value = float(mw_text.strip())
                except ValueError:
                    st.error("MW 請輸入數字 (Please enter a number)")
                    st.stop()

            insert_compound(
                english_name=english_name.strip(),
                formula=formula.strip(),
                mw=mw_value,
                cas=cas.strip(),
                package_size=package_size.strip(),
                location=location,
                location_detail=location_detail.strip(),
                lid_color=lid_color,
                appearance=appearance,
            )

            st.success("✅ 已新增化學品 (Chemical added)")
            st.info("到「查詢」頁面按 🔄 Refresh 或再按一次 🔎 Search 以更新結果。")

# ======================================================
# Search + Delete
# ======================================================
with tab_search:
    st.subheader("查詢化學品 (Search chemicals)")

    # Extra buttons
    cbtn1, cbtn2 = st.columns([1, 5])
    with cbtn1:
        if st.button("🔄 Refresh", help="重新查詢（不使用 cache）"):
            st.session_state["last_search"]["ran"] = True
            st.rerun()
    with cbtn2:
        st.caption("提示：為了避免資料庫連線被塞爆（PoolTimeout），此版本不使用 cache。")

    # Search form
    with st.form("search_form"):
        f1, f2, f3 = st.columns([2, 1, 1])
        with f1:
            q = st.text_input(
                "關鍵字 (Keyword: English / Formula / CAS)",
                value=st.session_state["last_search"]["q"],
            )
        with f2:
            loc_filter = st.selectbox(
                "位置 (Location)",
                ["All"] + LOCATIONS,
                index=(["All"] + LOCATIONS).index(st.session_state["last_search"]["location"])
            )
        with f3:
            lid_all_labels = ["All"] + list(LID_COLOR_OPTIONS.values())
            last_lid = st.session_state["last_search"]["lid_color"]
            last_lid_label = "All" if last_lid == "All" else LID_COLOR_OPTIONS.get(last_lid, "❓ Other")
            lid_filter_label = st.selectbox(
                "蓋子顏色 (Lid color)",
                lid_all_labels,
                index=lid_all_labels.index(last_lid_label)
            )
            lid_filter = "All" if lid_filter_label == "All" else label_to_key(LID_COLOR_OPTIONS, lid_filter_label)

        do_search = st.form_submit_button("🔎 Search")

    if do_search:
        st.session_state["last_search"] = {"q": q, "location": loc_filter, "lid_color": lid_filter, "ran": True}

    rows = []
    if st.session_state["last_search"]["ran"]:
        ls = st.session_state["last_search"]
        with st.spinner("Searching database..."):
            rows = run_search(ls["q"], ls["location"], ls["lid_color"])
    else:
        st.info("請先按 🔎 Search (Click Search to query)")

    df = pd.DataFrame(
        rows,
        columns=[
            "id",
            "english_name",
            "formula",
            "mw",
            "cas",
            "package_size",
            "location",
            "location_detail",
            "lid_color",
            "appearance",
            "created_at",
        ],
    )

    # Display dataframe with emoji lid color
    if not df.empty:
        df_display = df.copy()
        df_display["lid_color"] = df_display["lid_color"].apply(lambda x: LID_COLOR_OPTIONS.get(x, "❓ Other"))
    else:
        df_display = df

    st.write(f"找到 {len(df_display)} 筆 (Found {len(df_display)} records)")
    st.dataframe(df_display, use_container_width=True)

    st.download_button(
        "⬇️ 下載 CSV (Download CSV)",
        data=df_display.to_csv(index=False).encode("utf-8-sig"),
        file_name="chemicals.csv",
        mime="text/csv",
        disabled=df_display.empty,
    )

    # -----------------------------
    # Delete section (safe confirm)
    # -----------------------------
    if not df.empty:
        st.markdown("---")
        st.subheader("🗑 刪除資料 (Delete records)")

        if "delete_id" not in st.session_state:
            st.session_state["delete_id"] = None
            st.session_state["delete_name"] = None

        for _, row in df.iterrows():
            header = f"#{row['id']} | {row['english_name']} | {row['formula'] or ''} | {row['cas'] or ''}"

            with st.expander(header):
                st.write(
                    f"""
                    **English name:** {row['english_name']}  
                    **Formula:** {row['formula']}  
                    **MW:** {row['mw']}  
                    **CAS:** {row['cas']}  
                    **Package size:** {row['package_size']}  
                    **Location:** {row['location']}  
                    **Location detail:** {row['location_detail']}  
                    **Lid color:** {LID_COLOR_OPTIONS.get(row['lid_color'], '❓ Other')}  
                    **Appearance:** {row['appearance']}  
                    **Created at:** {row['created_at']}
                    """
                )

                col1, col2 = st.columns([1, 3])
                with col1:
                    if st.button("🗑 Delete", key=f"del_{row['id']}"):
                        st.session_state["delete_id"] = int(row["id"])
                        st.session_state["delete_name"] = row["english_name"]

                if st.session_state["delete_id"] == int(row["id"]):
                    st.warning(
                        f"Are you sure you want to delete **{st.session_state['delete_name']}** (id={st.session_state['delete_id']}) ?"
                    )
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("❌ Cancel", key=f"cancel_{row['id']}"):
                            st.session_state["delete_id"] = None
                            st.session_state["delete_name"] = None
                            st.rerun()
                    with c2:
                        if st.button("✅ Yes, delete", key=f"confirm_{row['id']}"):
                            delete_compound(int(row["id"]))
                            st.success("Deleted")
                            st.session_state["delete_id"] = None
                            st.session_state["delete_name"] = None
                            st.rerun()
