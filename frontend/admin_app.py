from __future__ import annotations

import hashlib
import html
import os
from datetime import date, timedelta

import streamlit as st

from frontend.api_client import APIError, SupportAPI

st.set_page_config(page_title="TicketBuddy Support", page_icon="🎟️", layout="wide")

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
      :root { --ink:#1d2939; --muted:#667085; --line:#e7eaf0; --canvas:#f5f7fa;
              --blue:#2563eb; --green:#16844a; }
      .stApp { background:var(--canvas); color:var(--ink); font-family:'DM Sans',sans-serif; }
      [data-testid="stHeader"] { background:transparent; }
      .block-container { max-width:1160px; padding-top:1.5rem; padding-bottom:3rem; }
      [data-testid="stSidebar"] { background:#fff; border-right:1px solid var(--line); }
      h1,h2,h3 { font-family:'Manrope','DM Sans',sans-serif !important; color:var(--ink); }
      .brand-mark { display:flex; align-items:center; gap:10px; margin:0 0 24px; }
      .brand-icon { display:grid; place-items:center; width:38px; height:38px; border-radius:12px;
                    background:#eaf1ff; color:#2459bd; font-size:20px; }
      .brand-name { font:800 17px 'Manrope',sans-serif; color:#1d2939; }
      .brand-sub { color:#7a8495; font-size:11px; margin-top:2px; }
      .page-head { display:flex; justify-content:space-between; align-items:center; gap:20px;
                   padding:4px 0 20px; border-bottom:1px solid var(--line); margin-bottom:20px; }
      .eyebrow { color:#667085; font-size:11px; font-weight:700; letter-spacing:.12em;
                 text-transform:uppercase; margin:0 0 5px; }
      .page-head h1 { font-size:27px; letter-spacing:-.04em; margin:0; }
      .page-sub { color:var(--muted); font-size:13px; margin:5px 0 0; }
      .live-pill { background:#e8f7ee; color:#16844a; border-radius:999px; padding:7px 12px;
                   font-size:12px; font-weight:700; white-space:nowrap; }
      .metric-card { background:#fff; border:1px solid var(--line); border-radius:13px;
                     padding:15px 17px; min-height:88px; box-shadow:0 2px 8px #1d293908; }
      .metric-label { color:#667085; font-size:12px; font-weight:600; }
      .metric-value { color:#182230; font:800 25px 'Manrope',sans-serif; margin-top:6px; }
      .section-title { font:700 16px 'Manrope',sans-serif; color:#243247; margin:3px 0 12px; }
      .source-row { display:flex; align-items:center; justify-content:space-between; gap:12px;
                    padding:12px 14px; background:#fff; border:1px solid var(--line);
                    border-radius:10px; margin:7px 0; }
      .source-title { color:#344054; font-size:13px; font-weight:600; }
      .source-meta { color:#8992a2; font-size:11px; margin-top:3px; }
      .status-pill { background:#e8f7ee; color:#16844a; border-radius:999px; padding:4px 9px;
                     font-size:10px; font-weight:700; }
      .status-empty { background:#fff4df; color:#9a6200; }
      div[data-testid="stTabs"] button { font-weight:600; }
      div[data-testid="stButton"] button { border-radius:9px; font-weight:600; }
      div[data-testid="stTextInput"] input, div[data-testid="stFileUploader"] section {
        border-radius:9px;
      }
      div[data-testid="stAlert"] { border-radius:10px; }
      @media (max-width:700px) { .block-container { padding:1rem; }
        .page-head h1 { font-size:22px; } }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        '<div class="brand-mark"><div class="brand-icon">🎟️</div>'
        '<div><div class="brand-name">TicketBuddy</div>'
        '<div class="brand-sub">Support workspace</div></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown("### API connection")
    api_url = st.text_input("API base URL", value="http://localhost:8000")
    admin_key = st.text_input(
        "Admin API key", value=os.getenv("ADMIN_API_KEY", ""), type="password"
    )
    if st.button("Check connection", use_container_width=True):
        try:
            with SupportAPI(api_url, admin_key) as check_api:
                check_api.health()
            st.success("Support API is online")
        except (APIError, AttributeError) as exc:
            st.error(str(exc))

api = SupportAPI(api_url, admin_key)
st.markdown(
    '<div class="page-head"><div><p class="eyebrow">Support workspace</p>'
    '<h1>Good support starts here</h1>'
    '<p class="page-sub">Manage help content and follow every customer handoff.</p></div>'
    '<div class="live-pill">● &nbsp;Agent workspace</div></div>',
    unsafe_allow_html=True,
)

knowledge_tab, analytics_tab, escalations_tab = st.tabs(
    ["Knowledge base", "Analytics", "Escalations"]
)

with knowledge_tab:
    try:
        analytics = api.analytics()
    except APIError as exc:
        analytics = None
        st.warning(f"Analytics are unavailable: {exc}")

    if analytics is not None:
        week_start = date.today() - timedelta(days=6)
        chats_this_week = sum(
            int(row.get("chats", 0))
            for row in analytics.get("daily_chats", [])
            if row.get("date", "") >= week_start.isoformat()
        )
        metrics = [
            ("Chats this week", chats_this_week),
            ("Resolved by agent", analytics.get("resolved", 0)),
            ("Sent to humans", analytics.get("escalated", 0)),
        ]
        cards = st.columns(3)
        for column, (label, value) in zip(cards, metrics, strict=True):
            with column:
                st.markdown(
                    f'<div class="metric-card"><div class="metric-label">{label}</div>'
                    f'<div class="metric-value">{value}</div></div>',
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    upload_col, url_col, reindex_col = st.columns([1.3, 1.3, 0.8])
    with upload_col:
        uploaded = st.file_uploader(
            "Upload a policy", type=["md", "pdf", "docx", "txt"], label_visibility="collapsed"
        )
        if st.button("↥  Upload document", use_container_width=True, disabled=uploaded is None):
            try:
                result = api.upload_knowledge(uploaded.name, uploaded.getvalue())
                st.success(f"Indexed {result['title']} ({result['indexed_chunks']} chunks).")
                st.rerun()
            except APIError as exc:
                st.error(str(exc))
    with url_col:
        source_url = st.text_input(
            "Policy URL", placeholder="Paste a public policy URL", label_visibility="collapsed"
        )
        if st.button("＋  Add URL", use_container_width=True, disabled=not source_url.strip()):
            try:
                result = api.add_knowledge_url(source_url.strip())
                st.success(f"Indexed {result['title']} ({result['indexed_chunks']} chunks).")
                st.rerun()
            except APIError as exc:
                st.error(str(exc))
    with reindex_col:
        st.write("")
        if st.button("Re-index all", use_container_width=True):
            try:
                result = api.reindex()
                st.success(
                    f"Updated {result['updated']}; removed {result['removed']}; "
                    f"indexed {result['indexed_chunks']} chunks."
                )
                st.rerun()
            except APIError as exc:
                st.error(str(exc))

    st.markdown('<div class="section-title">Policy documents</div>', unsafe_allow_html=True)
    try:
        sources = api.knowledge().get("sources", [])
        title_counts = {
            title: sum(source["title"] == title for source in sources)
            for title in {source["title"] for source in sources}
        }
        if not sources:
            st.info("No policy documents are indexed yet.")
        for source in sources:
            title = str(source.get("title", "Untitled policy"))
            status = str(source.get("status", "empty"))
            left, details, remove = st.columns([5, 1.5, 1])
            with left:
                safe_title = html.escape(title)
                safe_status = html.escape(status)
                status_class = "status-pill" if status == "indexed" else "status-pill status-empty"
                st.markdown(
                    f'<div class="source-row"><div><div class="source-title">{safe_title}</div>'
                    f'<div class="source-meta">{source.get("indexed_chunks", 0)} indexed chunks'
                    f' · {html.escape(str(source.get("kind", "file")))}</div></div>'
                    f'<span class="{status_class}">{safe_status}</span></div>',
                    unsafe_allow_html=True,
                )
            with details:
                if source.get("url"):
                    st.link_button("Open source", source["url"], use_container_width=True)
            with remove:
                unique_title = title_counts[title] == 1
                key = hashlib.sha1(title.encode("utf-8")).hexdigest()[:10]
                if st.button("Remove", key=f"remove_{key}", disabled=not unique_title):
                    try:
                        api.delete_knowledge(title)
                        st.success(f"Removed {title}.")
                        st.rerun()
                    except APIError as exc:
                        st.error(str(exc))
        if any(count > 1 for count in title_counts.values()):
            st.caption("A source with a duplicate title can’t be removed by title.")
    except APIError as exc:
        st.error(str(exc))

with analytics_tab:
    st.markdown('<div class="section-title">Support activity</div>', unsafe_allow_html=True)
    try:
        analytics = api.analytics()
        chats, resolved, escalated = st.columns(3)
        chats.metric("Total chats", analytics.get("chats", 0))
        resolved.metric("Resolved", analytics.get("resolved", 0))
        escalated.metric("Escalated", analytics.get("escalated", 0))

        top_questions = analytics.get("top_questions", [])
        if top_questions:
            st.markdown("#### Top questions")
            st.bar_chart(top_questions, x="question", y="count", horizontal=True)
        intent_counts = analytics.get("intent_counts", [])
        if intent_counts:
            st.markdown("#### Intent breakdown")
            st.bar_chart(intent_counts, x="intent", y="count")
        daily_chats = analytics.get("daily_chats", [])
        if daily_chats:
            st.markdown("#### Daily chat volume")
            st.line_chart(daily_chats, x="date", y="chats")
        st.markdown("#### Unresolved queries")
        unresolved = analytics.get("unresolved", [])
        if unresolved:
            st.dataframe(unresolved, use_container_width=True, hide_index=True)
        else:
            st.info("No unresolved questions recorded.")
    except APIError as exc:
        st.error(str(exc))

with escalations_tab:
    st.markdown('<div class="section-title">Human handoffs</div>', unsafe_allow_html=True)
    try:
        entries = api.escalations().get("escalations", [])
        if not entries:
            st.info("There are no escalations yet.")
        for entry in entries:
            with st.expander(
                f"{entry['customer_id']} · {entry.get('ticket_id') or 'Support case'} · "
                f"{entry['created_at']}"
            ):
                st.write(entry["summary"])
    except APIError as exc:
        st.error(str(exc))

api.close()
