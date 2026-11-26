import ReactMarkdown from "react-markdown";
import { sourceHref } from "../../api";
import type { ChatMessage } from "../../shared/types";

export function MessageView({ message, busy, onApprove }: {
  message: ChatMessage;
  busy: boolean;
  onApprove: (id: string, actionId: string, accepted: boolean) => Promise<void>;
}) {
  const result = message.result;
  return (
    <article className={`message-row ${message.role}`}>
          {message.role === "assistant" && <div className="assistant-avatar">{message.humanAgent ? "AG" : "TB"}</div>}
      <div className="message-content">
        {result && <div className="message-chips"><span>Intent: {result.intent}</span>{result.tool_calls.map((call, index) => <span key={`${call.name}-${index}`}>Used {call.name}</span>)}{result.pending_action && <span>Approval required</span>}</div>}
        <div className={`${message.role === "user" ? "bubble user-bubble" : "bubble assistant-bubble"}${message.humanAgent ? " human-agent-bubble" : ""}`}>
          {message.humanAgent && <strong className="human-agent-label">Support agent</strong>}
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
