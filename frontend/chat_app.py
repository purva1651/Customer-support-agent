from __future__ import annotations

import json
import mimetypes
import os
import uuid
from typing import Any
from urllib.parse import urljoin, urlsplit

import streamlit as st

from frontend.api_client import APIError, SupportAPI

st.set_page_config(page_title="TicketBuddy Support", page_icon="🎟️", layout="wide")
st.markdown(
    """
    <style>
      .stApp { background:#f5f7fa; color:#1d2939; }
      [data-testid="stHeader"] { background:transparent; }
      .block-container { max-width:900px; padding-top:1.4rem; padding-bottom:2rem; }
      [data-testid="stSidebar"] { background:#fff; border-right:1px solid #e7eaf0; }
      .brand { display:flex; align-items:center; gap:10px; margin:0 0 20px; }
      .brand-icon { display:grid; place-items:center; width:38px; height:38px;
        border-radius:12px; background:#eaf1ff; font-size:20px; }
      .brand-name { font-size:17px; font-weight:800; color:#1d2939; }
      .brand-sub { color:#7a8495; font-size:11px; }
      .chat-head { display:flex; align-items:center; justify-content:space-between;
        border-bottom:1px solid #e7eaf0; padding:4px 0 16px; margin-bottom:16px; }
      .chat-head h1 { font-size:25px; margin:0; }
      .chat-head p { color:#667085; font-size:13px; margin:4px 0 0; }
      div[data-testid="stChatMessage"] { background:#fff; border:1px solid #e7eaf0;
        border-radius:14px; padding:12px 16px; }
      div[data-testid="stButton"] button { border-radius:9px; font-weight:600; }
      @media (max-width:700px) { .block-container { padding:1rem; }
        .chat-head h1 { font-size:21px; } }
    </style>
    """,
    unsafe_allow_html=True,
)

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="brand-icon">🎟️</div><div>'
        '<div class="brand-name">TicketBuddy</div><div class="brand-sub">Customer support</div>'
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("### Chat settings")
    customer_id = st.text_input(
        "Demo customer ID", value="C001", help="Try C001 or C002 from the seeded demo data."
    ).strip()
    language = st.selectbox("Reply language", ["English", "Hindi", "Gujarati"])
    api_url = st.text_input(
        "API base URL", value=os.getenv("API_BASE_URL", "http://localhost:8000")
    ).strip()
    st.caption("The support API must be running before you send a message.")
    if st.button("New conversation", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

st.markdown(
    '<div class="chat-head"><div><h1>TicketBuddy support</h1>'
    '<p>Ask about a booking, ticket policy, refund, or cancellation.</p></div></div>',
    unsafe_allow_html=True,
)
st.caption(f"Signed in as **{customer_id or '—'}** · {language}")


def _absolute_source_url(base_url: str, source_url: str) -> str:
    if urlsplit(source_url).scheme in {"http", "https"}:
        return source_url
    return urljoin(base_url.rstrip("/") + "/", source_url.lstrip("/"))


def _render_message(message: dict[str, Any], index: int) -> None:
    with st.chat_message(message["role"]):
        if message.get("escalated"):
            st.warning("Escalated to a support specialist")
        st.markdown(message.get("content", ""))
        if message.get("summary"):
            st.caption(f"Handoff summary: {message['summary']}")
        sources = message.get("sources", [])
        if sources:
            with st.expander("Sources"):
                for source in sources:
                    title = str(source.get("title", "Policy source"))
                    url = str(source.get("url", ""))
                    if url:
                        st.markdown(f"- [{title}]({_absolute_source_url(api_url, url)})")
                    else:
                        st.markdown(f"- {title}")
        calls = message.get("tool_calls", [])
        if calls:
            with st.expander("What the agent checked"):
                for call in calls:
                    st.write(f"**{call.get('name', 'Tool')}** — {call.get('summary', 'Completed')}")
        pending = message.get("pending_action")
        if pending and not message.get("approval_recorded"):
            st.warning(f"Please confirm: {pending.get('description', 'Approve this action?')}")
            left, right = st.columns(2)
            if left.button("Yes, go ahead", key=f"approve-{index}", use_container_width=True):
                _submit_approval(index, pending["action_id"], True)
            if right.button("No, keep it", key=f"decline-{index}", use_container_width=True):
                _submit_approval(index, pending["action_id"], False)


def _submit_approval(index: int, action_id: str, approved: bool) -> None:
    try:
        with SupportAPI(api_url) as api:
            result = api.approve(action_id, approved)
        st.session_state.messages[index]["approval_recorded"] = True
        st.session_state.messages.append(
            {"role": "assistant", "content": result.get("reply", "Your choice has been recorded.")}
        )
    except APIError as exc:
        st.error(f"Could not submit your choice: {exc}")
        return
    st.rerun()


for message_index, saved_message in enumerate(st.session_state.messages):
    _render_message(saved_message, message_index)

if not st.session_state.messages:
    with st.chat_message("assistant"):
        st.markdown(
            "Hi! I can check a booking, explain a ticket policy, help with a change, "
            "or read details from an invoice or warranty card."
        )

with st.expander("Upload an invoice or warranty card"):
    upload = st.file_uploader(
        "Choose a PDF, DOCX, JPG, or PNG", type=["pdf", "docx", "jpg", "jpeg", "png"]
    )
    document_type = st.selectbox("Document type", ["Auto-detect", "Invoice", "Warranty card"])
    if st.button("Extract document details", disabled=upload is None, use_container_width=True):
        assert upload is not None
        kinds = {"Auto-detect": None, "Invoice": "invoice", "Warranty card": "warranty_card"}
        kind = kinds[document_type]
        try:
            with SupportAPI(api_url) as api:
                extracted = api.extract_document(
                    customer_id,
                    upload.name,
                    upload.getvalue(),
                    kind,
                    mimetypes.guess_type(upload.name)[0] or "application/octet-stream",
                )
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": f"**Extracted details from {upload.name}**\n\n```json\n"
                    f"{json.dumps(extracted.get('fields', {}), ensure_ascii=False, indent=2)}\n```",
                }
            )
            st.rerun()
        except APIError as exc:
            st.error(f"Could not extract document details: {exc}")

prompt = st.chat_input("Type your message here…", disabled=not customer_id or not api_url)
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    try:
        with SupportAPI(api_url) as api:
            response = api.chat(
                customer_id=customer_id,
                session_id=st.session_state.session_id,
                message=prompt,
                language=language,
            )
        content = str(response.get("reply", ""))
        if response.get("escalated"):
            content = f"🚩 **Escalated to a support specialist**\n\n{content}"
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": content,
                "sources": response.get("sources", []),
                "tool_calls": response.get("tool_calls", []),
                "escalated": response.get("escalated", False),
                "summary": response.get("escalation_summary"),
                "pending_action": response.get("pending_action"),
            }
        )
    except APIError as exc:
        st.session_state.messages.append(
            {"role": "assistant", "content": f"I couldn't contact the support service: {exc}"}
        )
    st.rerun()
