import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState, Dispatch, SetStateAction } from "react";
import ReactMarkdown from "react-markdown";
import { api, Analytics, ChatResult, Escalation, KnowledgeSource, sourceHref } from "./api";

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  result?: ChatResult;
  approvalRecorded?: boolean;
};
type Page = "chat" | "admin";
type AdminTab = "knowledge" | "analytics" | "escalations";

const suggestions = [
  "What is the cancellation policy?",
  "Money deducted but no ticket",
  "Check my booking status",
];

function makeId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function readMessages(): ChatMessage[] {
  try {
    const data = JSON.parse(localStorage.getItem("ticketbuddy-messages") || "[]");
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

function Brand() {
  return (
    <a className="brand" href="#chat" aria-label="TicketBuddy home">
      <svg className="ticket-mark" viewBox="0 0 34 25" aria-hidden="true">
        <path d="M4 1.5h26A3.5 3.5 0 0 1 33.5 5v3.1a4.2 4.2 0 0 0 0 8.8V20a3.5 3.5 0 0 1-3.5 3.5H4A3.5 3.5 0 0 1 .5 20v-3.1a4.2 4.2 0 0 0 0-8.8V5A3.5 3.5 0 0 1 4 1.5Z" fill="currentColor" />
      </svg>
      <span>TicketBuddy</span>
    </a>
  );
}

function App() {
  const [page, setPage] = useState<Page>(window.location.hash === "#admin" ? "admin" : "chat");
  const [sessionId, setSessionId] = useState(() => localStorage.getItem("ticketbuddy-session") || makeId());
  const [messages, setMessages] = useState<ChatMessage[]>(readMessages);
  const [customerId, setCustomerId] = useState(() => localStorage.getItem("ticketbuddy-customer") || "C001");
  const [language, setLanguage] = useState(() => localStorage.getItem("ticketbuddy-language") || "English");
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    localStorage.setItem("ticketbuddy-session", sessionId);
  }, [sessionId]);
  useEffect(() => {
    localStorage.setItem("ticketbuddy-messages", JSON.stringify(messages));
  }, [messages]);
  useEffect(() => localStorage.setItem("ticketbuddy-customer", customerId), [customerId]);
  useEffect(() => localStorage.setItem("ticketbuddy-language", language), [language]);
  useEffect(() => {
    api.health().then(() => setOnline(true)).catch(() => setOnline(false));
  }, []);

  const navigate = (next: Page) => {
    setPage(next);
    window.history.replaceState(null, "", next === "admin" ? "#admin" : "#chat");
  };
  const newChat = () => {
    setSessionId(makeId());
    setMessages([]);
    navigate("chat");
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <Brand />
        <nav className="main-nav" aria-label="Main navigation">
          <button className={page === "chat" ? "nav-link active" : "nav-link"} onClick={() => navigate("chat")}>Customer chat</button>
          <button className={page === "admin" ? "nav-link active" : "nav-link"} onClick={() => navigate("admin")}>Admin panel</button>
        </nav>
        <button className="new-chat-button" onClick={newChat}>New chat</button>
      </header>
      {page === "chat" ? (
        <ChatPage
          customerId={customerId}
          language={language}
          online={online}
          messages={messages}
          sessionId={sessionId}
          setCustomerId={setCustomerId}
          setLanguage={setLanguage}
          setMessages={setMessages}
        />
      ) : <AdminPage />}
    </div>
  );
}

type ChatPageProps = {
  customerId: string;
  language: string;
  online: boolean | null;
  messages: ChatMessage[];
  sessionId: string;
  setCustomerId: (value: string) => void;
  setLanguage: (value: string) => void;
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
};

function ChatPage(props: ChatPageProps) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [props.messages, busy]);

  const send = useCallback(async (raw: string) => {
    const message = raw.trim();
    if (!message || busy) return;
    setError("");
    setBusy(true);
    setDraft("");
    props.setMessages((current) => [...current, { id: makeId(), role: "user", content: message }]);
    try {
      const result = await api.chat({
        customer_id: props.customerId,
        session_id: props.sessionId,
        message,
        language: props.language,
      });
      const content = result.escalated ? `🚩 **Escalated to a support specialist**\n\n${result.reply}` : result.reply;
      props.setMessages((current) => [...current, {
        id: makeId(), role: "assistant", content,
        result: { ...result, reply: content },
      }]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The message could not be sent.");
      props.setMessages((current) => [
        ...current,
        { id: makeId(), role: "assistant", content: "I couldn't reach the support service. Please try again." },
      ]);
    } finally {
      setBusy(false);
    }
  }, [busy, props]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (file) {
      await extractFile();
      return;
    }
    await send(draft);
  };

  const extractFile = async () => {
    if (!file || busy) return;
    setBusy(true);
    setError("");
    try {
      const documentType = /invoice/i.test(file.name) ? "invoice" : /warranty/i.test(file.name) ? "warranty_card" : undefined;
      const extracted = await api.extractDocument(props.customerId, file, documentType);
      const details = Object.entries(extracted.fields).map(([key, value]) => `**${key.replaceAll("_", " ")}:** ${typeof value === "string" ? value : JSON.stringify(value)}`).join("\n\n");
      props.setMessages((current) => [...current, {
        id: makeId(), role: "assistant",
        content: `**Extracted details from ${extracted.filename}**\n\n${details || "No fields were returned."}\n\n_Source: ${extracted.source}_`,
      }]);
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Document extraction failed.");
    } finally {
      setBusy(false);
    }
  };

  const approve = async (messageId: string, actionId: string, accepted: boolean) => {
    setBusy(true);
    setError("");
    try {
      const response = await api.approve(actionId, accepted);
      props.setMessages((current) => [
        ...current.map((message) => message.id === messageId ? { ...message, approvalRecorded: true } : message),
        { id: makeId(), role: "assistant", content: response.reply },
      ]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not submit your choice.");
    } finally {
      setBusy(false);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit(event);
    }
  };

  return (
    <main className="chat-page">
      <div className="chat-title-row">
        <div>
          <h1>Support chat</h1>
          <span className="online-status"><i className={props.online ? "online-dot" : "online-dot offline"} />{props.online ? "Assistant online" : props.online === false ? "API not connected" : "Connecting…"}</span>
        </div>
        <button className="settings-toggle" onClick={() => setSettingsOpen((open) => !open)} aria-expanded={settingsOpen}>
          <span aria-hidden="true">⚙</span> Chat settings
        </button>
      </div>
      {settingsOpen && (
        <div className="settings-panel">
          <label>Customer ID<input value={props.customerId} onChange={(event) => props.setCustomerId(event.target.value)} placeholder="C001" /></label>
          <label>Reply language<select value={props.language} onChange={(event) => props.setLanguage(event.target.value)}><option>English</option><option>Hindi</option><option>Gujarati</option></select></label>
          <span className="setting-hint">Demo customers: C001 and C002</span>
        </div>
      )}

      <section className="conversation" aria-label="Conversation">
        {props.messages.length === 0 ? (
          <div className="welcome-state">
            <div className="welcome-mark">✦</div>
            <h2>Hi, how can we help?</h2>
            <p>Ask about a booking, ticket policy, refund, or cancellation.</p>
          </div>
        ) : props.messages.map((message) => (
          <MessageView key={message.id} message={message} busy={busy} onApprove={approve} />
        ))}
        {busy && <div className="typing"><span /><span /><span /> TicketBuddy is checking…</div>}
        <div ref={bottom} />
      </section>

      {props.messages.length === 0 && (
        <div className="suggestion-row">
          {suggestions.map((suggestion) => <button key={suggestion} onClick={() => void send(suggestion)}>{suggestion}<span>↗</span></button>)}
        </div>
      )}
      {error && <div className="error-banner" role="alert">{error}</div>}
      {file && <div className="file-chip">📎 {file.name}<button onClick={() => { setFile(null); if (fileInput.current) fileInput.current.value = ""; }} aria-label="Remove attachment">×</button></div>}
      <form className="composer" onSubmit={(event) => void submit(event)}>
        <input ref={fileInput} className="visually-hidden" type="file" accept=".pdf,.docx,.jpg,.jpeg,.png" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        <button className="attach-button" type="button" onClick={() => fileInput.current?.click()} aria-label="Attach a document" title="Attach invoice or warranty card">＋</button>
        <textarea
          rows={1}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={file ? "Press send to extract this document…" : "Type your message here…"}
          aria-label="Message"
          disabled={busy}
        />
        <button className="send-button" type="submit" disabled={busy || (!draft.trim() && !file)}>{busy ? "…" : file ? "Extract" : "Send"}<span aria-hidden="true">➤</span></button>
      </form>
      <p className="composer-note">TicketBuddy can make mistakes. Check important booking details before confirming an action.</p>
    </main>
  );
}

function MessageView({ message, busy, onApprove }: {
  message: ChatMessage;
  busy: boolean;
  onApprove: (id: string, actionId: string, accepted: boolean) => Promise<void>;
}) {
  const result = message.result;
  return (
    <article className={`message-row ${message.role}`}>
      {message.role === "assistant" && <div className="assistant-avatar">TB</div>}
      <div className="message-content">
        {result && <div className="message-chips"><span>Intent: {result.intent}</span>{result.tool_calls.map((call, index) => <span key={`${call.name}-${index}`}>Used {call.name}</span>)}{result.pending_action && <span>Approval required</span>}</div>}
        <div className={message.role === "user" ? "bubble user-bubble" : "bubble assistant-bubble"}>
          <ReactMarkdown>{message.content}</ReactMarkdown>
          {result?.tool_calls.map((call, index) => <BookingCard key={`${call.name}-${index}`} call={call} />)}
          {result?.pending_action && !message.approvalRecorded && (
            <div className="approval-card">
              <p><strong>Please confirm:</strong> {result.pending_action.description}</p>
              <div className="approval-actions">
                <button className="approve-button" disabled={busy} onClick={() => void onApprove(message.id, result.pending_action!.action_id, true)}>Yes, go ahead</button>
                <button className="decline-button" disabled={busy} onClick={() => void onApprove(message.id, result.pending_action!.action_id, false)}>No, keep it</button>
              </div>
              <small>Only continue if you want the CRM to process this change.</small>
            </div>
          )}
        </div>
        {result?.escalation_summary && <div className="handoff-summary"><strong>Handoff summary</strong><p>{result.escalation_summary}</p></div>}
        {!!result?.sources.length && <div className="source-links"><span>Sources</span>{result.sources.map((source, index) => <a key={`${source.url}-${index}`} href={sourceHref(source.url)} target="_blank" rel="noreferrer">{source.title}<span>↗</span></a>)}</div>}
      </div>
      {message.role === "user" && <div className="user-avatar">{message.content.trim().slice(0, 1).toUpperCase() || "U"}</div>}
    </article>
  );
}

function BookingCard({ call }: { call: { name: string; summary: string } }) {
  if (!call.name.includes("booking")) return null;
  let booking: Record<string, unknown> | null = null;
  try {
    const parsed: unknown = JSON.parse(call.summary);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) booking = parsed as Record<string, unknown>;
  } catch {
    return null;
  }
  if (!booking || !("route" in booking || "booking_id" in booking)) return null;
  const amount = Number(booking.amount);
  return (
    <div className="booking-card">
      <div className="booking-main">
        <strong>{String(booking.route || `Booking ${booking.booking_id}`)}</strong>
        <span>{booking.departs_at ? new Date(String(booking.departs_at)).toLocaleString() : "Booking details"}{booking.seat ? ` · Seat ${booking.seat}` : ""}</span>
        <small>{booking.booking_id ? `Booking ${booking.booking_id}` : ""}</small>
      </div>
      <div className="booking-side">
        {Number.isFinite(amount) && <strong>₹{amount.toLocaleString("en-IN")}</strong>}
        <span className={`booking-status ${String(booking.status || "confirmed").toLowerCase()}`}>{String(booking.status || "confirmed")}</span>
        <div className="barcode" aria-hidden="true" />
      </div>
    </div>
  );
}

function AdminPage() {
  const [tab, setTab] = useState<AdminTab>("knowledge");
  const [adminKey, setAdminKey] = useState(() => sessionStorage.getItem("ticketbuddy-admin-key") || "");
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [url, setUrl] = useState("");
  const [upload, setUpload] = useState<File | null>(null);
  const [working, setWorking] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    if (!adminKey.trim()) return;
    setLoading(true);
    setError("");
    const results = await Promise.allSettled([
      api.knowledge(adminKey), api.analytics(adminKey), api.escalations(adminKey),
    ]);
    const failed = results.find((result) => result.status === "rejected");
    if (failed?.status === "rejected") setError(failed.reason instanceof Error ? failed.reason.message : "Could not load admin data.");
    if (results[0].status === "fulfilled") setSources(results[0].value.sources);
    if (results[1].status === "fulfilled") setAnalytics(results[1].value);
    if (results[2].status === "fulfilled") setEscalations(results[2].value.escalations);
    setLoading(false);
  }, [adminKey]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { sessionStorage.setItem("ticketbuddy-admin-key", adminKey); }, [adminKey]);

  const withAction = async (action: () => Promise<unknown>, success: string) => {
    setWorking(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "That action could not be completed.");
    } finally {
      setWorking(false);
    }
  };

  const uploadDocument = async () => {
    if (!upload) return;
    await withAction(() => api.uploadKnowledge(adminKey, upload), `Added ${upload.name} to the knowledge base.`);
    setUpload(null);
    if (uploadRef.current) uploadRef.current.value = "";
  };
  const addUrl = async (event: FormEvent) => {
    event.preventDefault();
    if (!url.trim()) return;
    await withAction(() => api.addKnowledgeUrl(adminKey, url.trim()), "Added the web page to the knowledge base.");
    setUrl("");
  };
  const deleteSource = async (source: KnowledgeSource) => {
    if (!window.confirm(`Remove “${source.title}” from the knowledge base?`)) return;
    await withAction(() => api.removeKnowledge(adminKey, source.title), `Removed ${source.title}.`);
  };

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    sources.forEach((source) => map.set(source.title, (map.get(source.title) || 0) + 1));
    return map;
  }, [sources]);

  return (
    <main className="admin-page">
      <div className="admin-tabs" role="tablist" aria-label="Admin sections">
        {(["knowledge", "analytics", "escalations"] as AdminTab[]).map((item) => (
          <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? "admin-tab selected" : "admin-tab"} onClick={() => setTab(item)}>
            {item === "knowledge" ? "Knowledge base" : item === "analytics" ? "Analytics" : `Escalations${escalations.length ? ` (${escalations.length})` : ""}`}
          </button>
        ))}
      </div>

      <div className="admin-keybar">
        <label htmlFor="admin-key">Admin API key</label>
        <input id="admin-key" type="password" value={adminKey} onChange={(event) => setAdminKey(event.target.value)} placeholder="Enter ADMIN_API_KEY" autoComplete="current-password" />
        <button className="button secondary small" onClick={() => void refresh()} disabled={!adminKey || loading}>{loading ? "Loading…" : "Refresh"}</button>
      </div>
      {error && <div className="error-banner" role="alert">{error}{error.includes("403") ? " Check the admin key in your .env file." : ""}</div>}
      {notice && <div className="success-banner">{notice}</div>}

      {tab === "knowledge" && (
        <section className="admin-section">
          <h1>Knowledge base</h1>
          <p className="section-intro">The assistant answers from indexed documents. Add a policy or FAQ, then ask about it in chat.</p>
          {analytics && <MetricStrip analytics={analytics} />}
          <div className="knowledge-actions">
            <div className="upload-area">
              <input ref={uploadRef} id="knowledge-upload" className="visually-hidden" type="file" accept=".md,.pdf,.docx,.txt" onChange={(event) => setUpload(event.target.files?.[0] ?? null)} />
              <label className="button secondary" htmlFor="knowledge-upload">↥ &nbsp;{upload ? upload.name : "Upload document"}</label>
              <button className="button secondary" disabled={!upload || working || !adminKey} onClick={() => void uploadDocument()}>Add file</button>
            </div>
            <form className="url-form" onSubmit={(event) => void addUrl(event)}>
              <input value={url} onChange={(event) => setUrl(event.target.value)} type="url" placeholder="Paste a public policy URL" aria-label="Policy URL" />
              <button className="button secondary" disabled={!url.trim() || working || !adminKey}>Add URL</button>
            </form>
            <button className="button secondary reindex-button" disabled={working || !adminKey} onClick={() => void withAction(() => api.reindex(adminKey), "Knowledge base re-indexed.")}>⟳ &nbsp;Re-index all</button>
          </div>

          <div className="table-wrap">
            <table className="knowledge-table">
              <thead><tr><th>Title</th><th>Type</th><th>Status</th><th>Chunks</th><th>Source</th><th /></tr></thead>
              <tbody>
                {sources.map((source, index) => (
                  <tr key={`${source.title}-${source.url}-${index}`}>
                    <td className="policy-title">{source.title}</td>
                    <td><span className="type-pill">{source.kind === "url" ? "URL" : source.url.split(".").pop()?.toUpperCase() || "FILE"}</span></td>
                    <td><span className={source.status === "indexed" ? "status-pill indexed" : "status-pill empty"}>{source.status}</span></td>
                    <td>{source.indexed_chunks}</td>
                    <td>{source.kind === "url" ? <a href={source.url} target="_blank" rel="noreferrer" className="table-link">Open ↗</a> : <span className="muted">Local file</span>}</td>
                    <td><button className="remove-button" disabled={!adminKey || working || counts.get(source.title) !== 1} title={counts.get(source.title) !== 1 ? "A duplicate title cannot be removed by title" : "Remove document"} onClick={() => void deleteSource(source)}>Remove</button></td>
                  </tr>
                ))}
                {!sources.length && <tr><td colSpan={6} className="empty-row">{adminKey ? loading ? "Loading documents…" : "No documents indexed yet. Add one above." : "Enter the admin API key to manage indexed documents."}</td></tr>}
              </tbody>
            </table>
          </div>
          <p className="table-footnote">Supported files: Markdown, PDF, DOCX, and TXT. Changes are indexed for retrieval.</p>
        </section>
      )}

      {tab === "analytics" && <AnalyticsPanel analytics={analytics} loading={loading} />}
      {tab === "escalations" && <EscalationsPanel entries={escalations} loading={loading} />}
    </main>
  );
}

function MetricStrip({ analytics }: { analytics: Analytics }) {
  return (
    <div className="metric-strip">
      <div><span>Chats this week</span><strong>{analytics.daily_chats.reduce((sum, row) => sum + row.chats, 0)}</strong></div>
      <div><span>Resolved by agent</span><strong>{analytics.resolved}</strong></div>
      <div><span>Sent to humans</span><strong>{analytics.escalated}</strong></div>
    </div>
  );
}

function AnalyticsPanel({ analytics, loading }: { analytics: Analytics | null; loading: boolean }) {
  if (!analytics) return <section className="admin-section"><h1>Analytics</h1><p className="section-intro">{loading ? "Loading support activity…" : "Enter a valid admin API key to view analytics."}</p></section>;
  const maxQuestion = Math.max(1, ...analytics.top_questions.map((item) => item.count));
  const maxDay = Math.max(1, ...analytics.daily_chats.map((item) => item.chats));
  return (
    <section className="admin-section">
      <h1>Analytics</h1><p className="section-intro">A quick view of customer support activity.</p>
      <div className="metric-strip large-metrics"><div><span>Total chats</span><strong>{analytics.chats}</strong></div><div><span>Resolved by agent</span><strong>{analytics.resolved}</strong></div><div><span>Sent to humans</span><strong>{analytics.escalated}</strong></div></div>
      <div className="analytics-grid">
        <div className="panel-card"><h2>Top questions</h2>{analytics.top_questions.length ? analytics.top_questions.slice(0, 8).map((item) => <div className="bar-row" key={item.question}><span>{item.question}</span><div className="bar-track"><i style={{ width: `${(item.count / maxQuestion) * 100}%` }} /></div><b>{item.count}</b></div>) : <p className="muted">No questions recorded yet.</p>}</div>
        <div className="panel-card"><h2>Intent breakdown</h2>{analytics.intent_counts.length ? <div className="intent-list">{analytics.intent_counts.map((item) => <div key={item.intent}><span className="intent-dot" />{item.intent.replaceAll("_", " ")}<strong>{item.count}</strong></div>)}</div> : <p className="muted">No intent data yet.</p>}</div>
        <div className="panel-card daily-panel"><h2>Daily chat volume</h2>{analytics.daily_chats.length ? <div className="daily-bars">{analytics.daily_chats.slice(-14).map((item) => <div className="daily-column" key={item.date} title={`${item.date}: ${item.chats} chats`}><span style={{ height: `${Math.max(4, (item.chats / maxDay) * 100)}%` }} /><small>{item.date.slice(5)}</small></div>)}</div> : <p className="muted">No daily activity yet.</p>}</div>
      </div>
      <div className="panel-card unresolved-panel"><h2>Unresolved queries</h2>{analytics.unresolved.length ? <div className="table-wrap"><table><thead><tr><th>Question</th><th>Intent</th><th>Session</th><th>Created</th></tr></thead><tbody>{analytics.unresolved.map((item, index) => <tr key={`${item.session_id}-${index}`}><td>{item.question}</td><td>{item.intent}</td><td className="muted">{item.session_id}</td><td>{formatDate(item.created_at)}</td></tr>)}</tbody></table></div> : <p className="muted">No unresolved questions recorded.</p>}</div>
    </section>
  );
}

function EscalationsPanel({ entries, loading }: { entries: Escalation[]; loading: boolean }) {
  return (
    <section className="admin-section">
      <h1>Escalations</h1><p className="section-intro">Cases handed to a human support specialist.</p>
      {!entries.length ? <div className="empty-card">{loading ? "Loading handoffs…" : "There are no escalations yet."}</div> : <div className="escalation-list">{entries.map((entry) => <article className="escalation-card" key={`${entry.session_id}-${entry.created_at}`}><div className="escalation-meta"><span className="escalation-id">{entry.ticket_id || "Support case"}</span><span>{entry.customer_id}</span><time>{formatDate(entry.created_at)}</time></div><p>{entry.summary}</p><small>Session {entry.session_id}</small></article>)}</div>}
    </section>
  );
}

function formatDate(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString();
}

export default App;
