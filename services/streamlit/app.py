import streamlit as st
import requests
import uuid

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="World Bank Economic Intelligence",
    page_icon="🌍",
    layout="centered",
)

API_URL = "http://api:8000"

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "display_history" not in st.session_state:
    st.session_state.display_history = []

st.title("🌍 World Bank Economic Intelligence Assistant")
st.caption("Ask natural language questions about global economic data (2000-2023)")


# ── Render existing conversation, oldest to newest ────────────────────────────
for turn in st.session_state.display_history:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        st.write(turn["answer"])
        st.caption(f"Route used: **{turn['route']}** | Records retrieved: {turn['context_records']}")
        if turn["sources"]:
            with st.expander("View sources"):
                st.table(turn["sources"])

# ── Chat input — pinned to the bottom of the page ─────────────────────────────
question = st.chat_input("Ask a question about global economic data...")

if question:
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking... (this can take 10-30 seconds)"):
            payload = {"question": question, "session_id": st.session_state.session_id}
        

            try:
                response = requests.post(
                    f"{API_URL}/ask",
                    json=payload,
                    timeout=120,
                )
                response.raise_for_status()
                result = response.json()

                st.write(result["answer"])

                route = result.get("route", "SEMANTIC")
                context_records = result.get("context_records", 0)
                sources = result.get("sources", [])

                st.caption(f"Route used: **{route}** | Records retrieved: {context_records}")
                if sources:
                    with st.expander("View sources"):
                        st.table(sources)

                st.session_state.display_history.append({
                    "question": question,
                    "answer": result["answer"],
                    "route": route,
                    "context_records": context_records,
                    "sources": sources,
                })

            except requests.exceptions.Timeout:
                st.error("Request timed out. The model may be under heavy load — try again.")
            except requests.exceptions.RequestException as e:
                st.error(f"Something went wrong: {e}")
