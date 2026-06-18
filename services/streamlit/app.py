import streamlit as st
import requests

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="World Bank Economic Intelligence",
    page_icon="🌍",
    layout="centered",
)

API_URL = "http://api:8000"

st.title("🌍 World Bank Economic Intelligence Assistant")
st.caption("Ask natural language questions about global economic data (2000-2023)")

# ── Input form ────────────────────────────────────────────────────────────────
REGIONS = [
    "Any region",
    "Sub-Saharan Africa",
    "Europe & Central Asia",
    "Latin America & Caribbean",
    "Middle East & North Africa",
    "North America",
    "South Asia",
    "East Asia & Pacific",
]

question = st.text_input(
    "Ask a question about global economic data:",
    placeholder="e.g. Which countries had inflation above 10% in 2022?",
)

region = st.selectbox("Filter by region (optional):", REGIONS)

submit = st.button("Ask", type="primary")

if submit:
    if not question.strip():
        st.warning("Please enter a question.")
    else:
        with st.spinner("Thinking... (this can take 10-30 seconds)"):
            payload = {"question": question}
            if region != "Any region":
                payload["region"] = region

            try:
                response = requests.post(
                    f"{API_URL}/ask",
                    json=payload,
                    timeout=120,
                )
                response.raise_for_status()
                result = response.json()

                st.success("Answer:")
                st.write(result["answer"])

                route = result.get("route", "SEMANTIC")
                st.caption(f"Route used: **{route}** | Records retrieved: {result.get('context_records', 0)}")

                if result.get("sources"):
                    with st.expander("View sources"):
                        st.table(result["sources"])

            except requests.exceptions.Timeout:
                st.error("Request timed out. The model may be under heavy load — try again.")
            except requests.exceptions.RequestException as e:
                st.error(f"Something went wrong: {e}")
