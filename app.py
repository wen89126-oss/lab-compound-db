import streamlit as st
import pandas as pd
from db import init_db, insert_compound, search_compounds, delete_compound

# ======================================================
# Page config
# ======================================================
st.set_page_config(page_title="Chemical Storage Database", layout="wide")
st.title("🧪 Chemical Storage Database")

# ======================================================
# ✅ Center dataframe text (header + cells)
# ======================================================
st.markdown(
    """
    <style>
    [data-testid="stDataFrame"] thead th {
        text-align: center !important;
    }

    [data-testid="stDataFrame"] tbody td {
        text-align: center !important;
    }

    [data-testid="stDataFrame"] div[role="gridcell"] {
        justify-content: center !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ======================================================
# Init DB
# ======================================================
st.caption("Database status: connected on demand")
init_db()

# ======================================================
# Options
# ======================================================
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


# ======================================================
# Session state
# ======================================================
if "last_search" not in st.session_state:
    st.session_state["last_search"] = {
        "q": "",
        "location": "All",
        "lid_color": "All",
        "ran": False,
    }

# ======================================================
# Tabs
# ======================================================
tab_add, tab_search = st.tabs(["➕ 新增 (Add)", "🔎 查詢 (Search)"])

# ======================================================
# ➕ Add
# ======================================================
with tab_add:
    st.subheader("新增化學品 (Add chemical)")

    with st.form("add_form"):
        english_name = st.text_input("英文名 (English name)")
        cas = st.text_input("CAS")

        col1, col2 = st.columns(2)
        with col1:
            formula = st.text_input("分子式 (Formula)")
        with col2:
            mw_text = st.text_input("分子量 (MW)")

        package_size = st.text_input("包裝大小 (Package size)")

        st.markdown("### 位置 (Location)")
        c1, c2 = st.columns([1, 2])
        with c1:
            location = st.selectbox("位置", LOCATIONS)
        with c2:
            location_detail = st.text_input("詳細位置")

        colA, colB = st.columns(2)
        with colA:
            lid_color_label = st.selectbox(
                "蓋子顏色", list(LID_COLOR_OPTIONS.values())
            )
            lid_color = label_to_key(LID_COLOR_OPTIONS, lid_color_label)

        with colB:
            appearance = st.selectbox("性狀", APPEARANCE)

        submitted = st.form_submit_button("💾 儲存")

    if submitted:
        if not english_name.strip():
            st.error("請輸入英文名")
            st.stop()

        mw_value = None
        if mw_text.strip():
            try:
                mw_value = float(mw_text)
            except ValueError:
                st.error("MW 必須是數字")
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

        st.success("✅ 已新增")

# ======================================================
# 🔎 Search
# ======================================================
with tab_search:
    st.subheader("查詢化學品 (Search chemicals)")

    with st.form("search_form"):
        f1, f2, f3 = st.columns([2, 1, 1])

        with f1:
            q = st.text_input(
                "Keyword (Name / Formula / CAS)",
                value=st.session_state["last_search"]["q"],
            )

        with f2:
            loc_filter = st.selectbox(
                "Location",
                ["All"] + LOCATIONS,
                index=(["All"] + LOCATIONS).index(
                    st.session_state["last_search"]["location"]
                ),
            )

        with f3:
            lid_labels = ["All"] + list(LID_COLOR_OPTIONS.values())
            last = st.session_state["last_search"]["lid_color"]
            last_label = (
                "All" if last == "All" else LID_COLOR_OPTIONS.get(last, "❓ Other")
            )

            lid_filter_label = st.selectbox(
                "Lid color",
                lid_labels,
                index=lid_labels.index(last_label),
            )

            lid_filter = (
                "All"
                if lid_filter_label == "All"
                else label_to_key(LID_COLOR_OPTIONS, lid_filter_label)
            )

        do_search = st.form_submit_button("🔎 Search")

    if do_search:
        st.session_state["last_search"] = {
            "q": q,
            "location": loc_filter,
            "lid_color": lid_filter,
            "ran": True,
        }

    rows = []
    if st.session_state["last_search"]["ran"]:
        ls = st.session_state["last_search"]
        with st.spinner("Searching database..."):
            rows = search_compounds(
                q=ls["q"], location=ls["location"], lid_color=ls["lid_color"]
            )
    else:
        st.info("請先按 Search")

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

    if not df.empty:
        df_display = df.copy()
        df_display["lid_color"] = df_display["lid_color"].apply(
            lambda x: LID_COLOR_OPTIONS.get(x, "❓ Other")
        )
    else:
        df_display = df

    st.write(f"找到 {len(df_display)} 筆")
    st.data_editor(
    df_display,
    width="stretch",
    disabled=True,
    hide_index=True,
)


    st.download_button(
        "⬇️ Download CSV",
        data=df_display.to_csv(index=False).encode("utf-8-sig"),
        file_name="chemicals.csv",
        mime="text/csv",
        disabled=df_display.empty,
    )

    # ==================================================
    # Delete
    # ==================================================
    if not df.empty:
        st.markdown("---")
        st.subheader("🗑 刪除資料")

        if "delete_id" not in st.session_state:
            st.session_state["delete_id"] = None
            st.session_state["delete_name"] = None

        for _, row in df.iterrows():
            header = f"#{row['id']} | {row['english_name']} | {row['cas'] or ''}"

            with st.expander(header):
                st.write(
                    f"""
                    **Name:** {row['english_name']}  
                    **Formula:** {row['formula']}  
                    **MW:** {row['mw']}  
                    **CAS:** {row['cas']}  
                    **Package:** {row['package_size']}  
                    **Location:** {row['location']}  
                    **Detail:** {row['location_detail']}  
                    **Lid:** {LID_COLOR_OPTIONS.get(row['lid_color'], '❓ Other')}  
                    **Appearance:** {row['appearance']}  
                    """
                )

                col1, col2 = st.columns(2)

                with col1:
                    if st.button("🗑 Delete", key=f"d_{row['id']}"):
                        st.session_state["delete_id"] = row["id"]
                        st.session_state["delete_name"] = row["english_name"]

                if st.session_state["delete_id"] == row["id"]:
                    st.warning(
                        f"確定刪除 **{st.session_state['delete_name']}** ?"
                    )

                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Cancel", key=f"c_{row['id']}"):
                            st.session_state["delete_id"] = None
                            st.rerun()

                    with c2:
                        if st.button("Yes, delete", key=f"y_{row['id']}"):
                            delete_compound(row["id"])
                            st.success("Deleted")
                            st.session_state["delete_id"] = None
                            st.rerun()
