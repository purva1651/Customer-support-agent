import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, FormEvent, KeyboardEvent, SetStateAction } from "react";
import type { ChatResult } from "../../api";
import { api } from "../../api";
import { makeId, messagesStorageKey, DEMO_BOOKINGS, starterCards, suggestions } from "../../shared/data";
import type { ChatMessage } from "../../shared/types";
import { MessageView } from "./MessageView";

type ChatPageProps = {
  customerId: string;
  language: string;
  online: boolean | null;
  messages: ChatMessage[];
  sessionId: string;
  onNewChat: () => void;
  setCustomerId: (value: string) => void;
  setLanguage: (value: string) => void;
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  setOnline: (value: boolean) => void;
};

export function ChatPage(props: ChatPageProps) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [escalationStatus, setEscalationStatus] = useState<ChatResult["escalation_status"]>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const bookings = DEMO_BOOKINGS[props.customerId as keyof typeof DEMO_BOOKINGS] || [];
  const customerName = props.customerId === "C001" ? "Aarav Patel" : "Maya Shah";
  const hasEscalatedChat = escalationStatus !== null;

  useEffect(() => {
    setEscalationStatus(null);
  }, [props.sessionId]);

  useEffect(() => {
    let cancelled = false;
    void api.customerMessages(props.customerId, props.sessionId).then((thread) => {
      if (cancelled) return;
      setEscalationStatus(thread.status);
      const restored = thread.messages.map((message) => ({
        id: `server-${message.id}`,
        serverMessageId: message.id,
        role: message.sender === "customer" ? "user" as const : "assistant" as const,
        content: message.content,
        humanAgent: message.sender === "admin",
      }));
      props.setMessages((current) => {
        const existingCounts = new Map<string, number>();
        for (const message of current) {
          const sender = message.role === "user" ? "customer" : message.humanAgent ? "admin" : "assistant";
          const content = message.content.replace(/^🚩 \*\*Escalated to a support specialist\*\*\s*/, "").trim();
          const key = `${sender}:${content}`;
          existingCounts.set(key, (existingCounts.get(key) ?? 0) + 1);
        }
        const missing = restored.filter((message) => {
          const sender = message.role === "user" ? "customer" : message.humanAgent ? "admin" : "assistant";
          const key = `${sender}:${message.content.trim()}`;
          const count = existingCounts.get(key) ?? 0;
          if (count > 0) {
            existingCounts.set(key, count - 1);
            return false;
          }
          return true;
        });
        return [...current, ...missing];
      });
    }).catch(() => {
      // New chats have no saved server transcript yet.
    });
    return () => { cancelled = true; };
  }, [props.customerId, props.sessionId, props.setMessages]);

  useEffect(() => {
    try {
      localStorage.setItem(
        messagesStorageKey(props.customerId, props.sessionId),
        JSON.stringify(props.messages),
      );
    } catch {
      // Keep chat usable if local storage is unavailable or full.
    }
  }, [props.customerId, props.messages, props.sessionId]);

  useEffect(() => {
    if (!hasEscalatedChat || escalationStatus === "closed" || escalationStatus === "rejected") return;
    let cancelled = false;
    const loadAgentReplies = async () => {
      try {
        const thread = await api.customerMessages(props.customerId, props.sessionId);
        if (cancelled) return;
        setEscalationStatus(thread.status);
        if (thread.status === "accepted" && escalationStatus !== "accepted") {
          props.setMessages((current) => [
            ...current,
            { id: makeId(), role: "assistant", content: "A support agent accepted your case. You can continue messaging here." },
          ]);
        }
        const replies = thread.messages.filter((message) => message.sender === "admin");
        props.setMessages((current) => {
          const knownIds = new Set(
            current.map((message) => message.serverMessageId).filter((id): id is number => id !== undefined),
          );
          const unseen = replies.filter((message) => !knownIds.has(message.id));
          return [
            ...current,
            ...unseen.map((message) => ({
              id: `server-${message.id}`,
              serverMessageId: message.id,
              humanAgent: true,
              role: "assistant" as const,
              content: message.content,
            })),
          ];
        });
      } catch {
        // Keep chat usable during short API restarts; the next poll will retry.
      }
    };
    void loadAgentReplies();
    const timer = window.setInterval(() => void loadAgentReplies(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [escalationStatus, hasEscalatedChat, props.customerId, props.sessionId, props.setMessages]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [props.messages, busy]);

  const send = useCallback(async (raw: string) => {
    const message = raw.trim();
    if (!message || busy) return;
    if (
      message.toLocaleLowerCase() !== "close"
      && (escalationStatus === "closed" || escalationStatus === "rejected")
    ) {
      setEscalationStatus(null);
    }
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
      props.setOnline(true);
      if (result.escalation_status) setEscalationStatus(result.escalation_status);
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
  }, [busy, escalationStatus, props]);

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
      props.setOnline(true);
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
        <div className="chat-title-actions">
          <button className="settings-toggle" onClick={() => setSettingsOpen((open) => !open)} aria-expanded={settingsOpen}>
            <span aria-hidden="true">⚙</span> Chat settings
          </button>
          <button className="new-chat-inline" onClick={props.onNewChat}>＋ New chat</button>
        </div>
      </div>
      {settingsOpen && (
        <div className="settings-panel">
          <label>Customer ID<input value={props.customerId} onChange={(event) => props.setCustomerId(event.target.value)} placeholder="C001" /></label>
          <label>Reply language<select value={props.language} onChange={(event) => props.setLanguage(event.target.value)}><option>English</option><option>Hindi</option><option>Gujarati</option></select></label>
          <span className="setting-hint">Demo customers: C001 and C002</span>
        </div>
      )}

      {!!bookings.length && <div className="booking-strip" aria-label="Your recent bookings">
        {bookings.map((booking) => <button className="booking-chip" key={booking.id} onClick={() => void send(`Show booking ${booking.id}`)}>
          <strong>{booking.route}</strong><span>{booking.id} · {booking.date}</span><i>{booking.status}</i>
        </button>)}
      </div>}

      <section className="conversation" aria-label="Conversation">
        {props.messages.length === 0 ? (
          <div className="chat-welcome">
            <div className="assistant-avatar welcome-avatar">TB</div>
            <div className="welcome-content"><span>ASSISTANT</span><p>Welcome back, {customerName.split(" ")[0]}. I can answer policy questions, check or cancel bookings, raise tickets, and connect you to a human.</p></div>
            <div className="starter-card-grid">{starterCards.map((card) => <button className="starter-card" key={card.title} onClick={() => void send(card.prompt)}><span className="starter-icon">{card.icon}</span><strong>{card.title}</strong><small>{card.text}</small></button>)}</div>
          </div>
        ) : props.messages.map((message) => (
          <MessageView key={message.id} message={message} busy={busy} onApprove={approve} />
        ))}
        {busy && <div className="typing"><span /><span /><span /> TicketBuddy is checking…</div>}
        <div ref={bottom} />
      </section>

      <div className="suggestion-row">
        {suggestions.map((suggestion) => <button key={suggestion} onClick={() => void send(suggestion)}>{suggestion}<span>↗</span></button>)}
      </div>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {hasEscalatedChat && escalationStatus && <div className={`customer-escalation-status ${escalationStatus}`} role="status">
        {escalationStatus === "pending" ? "Your support case is waiting for an agent. Messages you send here are saved to the case." :
          escalationStatus === "accepted" ? "A support agent is handling this case. Replies will appear here." :
            escalationStatus === "closed" ? "This support conversation is closed." : "This support case was not accepted."}
      </div>}
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
