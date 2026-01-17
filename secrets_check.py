import streamlit as st

st.title("Secrets check")

st.write("Keys in st.secrets:", list(st.secrets.keys()))

if "DATABASE_URL" in st.secrets:
    st.success("DATABASE_URL exists ✅")
    st.write("DATABASE_URL length:", len(st.secrets["DATABASE_URL"]))
else:
    st.error("DATABASE_URL missing ❌")