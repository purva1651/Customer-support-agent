import type { ChatMessage } from "./types";

export const suggestions = [
  "What is the cancellation policy?",
  "Money deducted but no ticket",
  "Cancel my booking",
  "Show booking B001",
];

export const DEMO_BOOKINGS = {
  C001: [
    { id: "B001", route: "Ahmedabad to Mumbai (bus)", date: "1 Dec 2026 · 9:30 AM", status: "Confirmed" },
    { id: "B002", route: "Mumbai to Pune (bus)", date: "5 Dec 2026 · 2:00 PM", status: "Confirmed" },
  ],
  C002: [
    { id: "B003", route: "Delhi to Jaipur (bus)", date: "3 Dec 2026 · 8:00 AM", status: "Confirmed" },
  ],
};

export const starterCards = [
  { icon: "⊗", title: "Cancel a booking", text: "Cancel my booking", prompt: "I want to cancel my booking B001" },
  { icon: "▣", title: "Payment problem", text: "Money deducted but no ticket", prompt: "Money deducted but no ticket" },
  { icon: "▤", title: "Policies", text: "What is the cancellation policy?", prompt: "What is the cancellation policy?" },
  { icon: "♙", title: "Talk to a person", text: "Connect me to human support", prompt: "Please connect me to a support agent" },
];

export function makeId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function sessionStorageKey(customerId: string): string {
  return `ticketbuddy-session-${customerId}`;
}

export function messagesStorageKey(customerId: string, sessionId: string): string {
  return `ticketbuddy-messages-${customerId}-${sessionId}`;
}

export function readSavedMessages(customerId: string, sessionId: string): ChatMessage[] {
  try {
    const saved = localStorage.getItem(messagesStorageKey(customerId, sessionId));
    if (!saved) return [];
    const parsed: unknown = JSON.parse(saved);
    return Array.isArray(parsed) ? parsed as ChatMessage[] : [];
  } catch {
    return [];
  }
}
