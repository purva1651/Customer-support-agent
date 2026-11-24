import streamlit as st

from frontend.api_client import APIError, SupportAPI

st.set_page_config(page_title="Ticket Support Admin", page_icon="🎫", layout="wide")
st.title("Ticket Support Agent · Admin")
st.caption("Manage the knowledge base and review support activity through the REST API.")

with st.sidebar:
    st.header("API connection")
    api_url = st.text_input("API base URL", value="http://localhost:8000")
    admin_key = st.text_input("Admin API key", type="password")
    if st.button("Check API"):
        try:
            with SupportAPI(api_url, admin_key) as api:
                st.success(f"API status: {api.health().get('status', 'unknown')}")
        except (APIError, AttributeError) as exc:
            st.error(str(exc))

api = SupportAPI(api_url, admin_key)
knowledge_tab, analytics_tab, escalations_tab = st.tabs(
    ["Knowledge base", "Analytics", "Escalations"]
)

with knowledge_tab:
    st.subheader("Knowledge sources")
    if st.button("Refresh sources", key="refresh_knowledge"):
        st.rerun()
    try:
        sources = api.knowledge().get("sources", [])
        st.dataframe(sources, use_container_width=True, hide_index=True)
        title_counts = {
            title: sum(source["title"] == title for source in sources)
            for title in {source["title"] for source in sources}
        }
        deletable_titles = sorted(title for title, count in title_counts.items() if count == 1)
        duplicate_titles = sorted(title for title, count in title_counts.items() if count > 1)
        if duplicate_titles:
            st.warning(
                "Sources with duplicate titles cannot be removed by title: "
                + ", ".join(duplicate_titles)
            )
        if deletable_titles:
            selected_title = st.selectbox("Source to remove", deletable_titles)
            if st.button("Remove source"):
                st.success(api.delete_knowledge(selected_title).get("title", "Removed"))
                st.rerun()
    except APIError as exc:
        st.error(str(exc))

    st.divider()
    upload_col, url_col = st.columns(2)
    with upload_col:
        st.markdown("#### Upload a policy file")
        uploaded = st.file_uploader(
            "Markdown, PDF, DOCX, or TXT", type=["md", "pdf", "docx", "txt"]
        )
        if st.button("Upload and index", disabled=uploaded is None):
            try:
                result = api.upload_knowledge(uploaded.name, uploaded.getvalue())
                st.success(f"Indexed {result['title']} ({result['indexed_chunks']} chunks).")
                st.rerun()
            except APIError as exc:
                st.error(str(exc))
    with url_col:
        st.markdown("#### Add a policy URL")
        source_url = st.text_input("Public HTTP(S) URL", key="knowledge_url")
        if st.button("Load and index URL", disabled=not source_url.strip()):
            try:
                result = api.add_knowledge_url(source_url.strip())
                st.success(f"Indexed {result['title']} ({result['indexed_chunks']} chunks).")
                st.rerun()
            except APIError as exc:
                st.error(str(exc))

    if st.button("Reindex all sources"):
        try:
            result = api.reindex()
            st.success(
                f"Updated {result['updated']}; removed {result['removed']}; "
                f"indexed {result['indexed_chunks']} chunks."
            )
        except APIError as exc:
            st.error(str(exc))

with analytics_tab:
    st.subheader("Support analytics")
    try:
        analytics = api.analytics()
        chats, resolved, escalated = st.columns(3)
        chats.metric("Chats", analytics.get("chats", 0))
        resolved.metric("Resolved", analytics.get("resolved", 0))
        escalated.metric("Escalated", analytics.get("escalated", 0))
        top_questions = analytics.get("top_questions", [])
        st.markdown("#### Top questions")
        if top_questions:
            st.bar_chart({item["question"]: item["count"] for item in top_questions})
        else:
            st.info("No questions have been recorded yet.")
        st.markdown("#### Unresolved queries")
        unresolved = analytics.get("unresolved", [])
        st.dataframe(unresolved, use_container_width=True, hide_index=True)
    except APIError as exc:
        st.error(str(exc))

with escalations_tab:
    st.subheader("Human handoffs")
    try:
        escalations = api.escalations().get("escalations", [])
        if not escalations:
            st.info("There are no escalations yet.")
        for entry in escalations:
            with st.expander(
                f"{entry['customer_id']} · session {entry['session_id']} · {entry['created_at']}"
            ):
                st.write(entry["summary"])
                if entry.get("ticket_id"):
                    st.caption(f"Ticket: {entry['ticket_id']}")
    except APIError as exc:
        st.error(str(exc))

api.close()
