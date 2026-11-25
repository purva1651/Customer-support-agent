const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export type Source = { title: string; url: string };
export type ToolCall = { name: string; summary: string };
export type PendingAction = { action_id: string; description: string };
export type ChatResult = {
  reply: string;
  intent: string;
  sources: Source[];
  tool_calls: ToolCall[];
  pending_action: PendingAction | null;
  escalated: boolean;
  escalation_summary: string | null;
};
export type KnowledgeSource = {
  title: string;
  url: string;
  kind: "file" | "url";
  indexed_chunks: number;
  status: "indexed" | "empty";
};
export type Analytics = {
  chats: number;
  resolved: number;
  escalated: number;
  top_questions: { question: string; count: number }[];
  unresolved: { question: string; intent: string; session_id: string; created_at: string }[];
  intent_counts: { intent: string; count: number }[];
  daily_chats: { date: string; chats: number }[];
};
export type Escalation = {
  session_id: string;
  customer_id: string;
  summary: string;
  ticket_id: string | null;
  created_at: string;
};

async function request<T>(path: string, init?: RequestInit, adminKey?: string): Promise<T> {
  const headers = new Headers(init?.headers);
  if (adminKey) headers.set("X-Admin-Key", adminKey);
  if (init?.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new Error(`Could not reach the support API at ${API_BASE}. Is the API running?`);
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // Keep the HTTP status as the message when the response isn't JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  baseUrl: API_BASE,
  health: () => request<{ status: string }>("/health"),
  chat: (payload: {
    customer_id: string;
    session_id: string;
    message: string;
    language: string;
  }) => request<ChatResult>("/chat", { method: "POST", body: JSON.stringify(payload) }),
  approve: (action_id: string, approved: boolean) =>
    request<{ reply: string }>("/approve", { method: "POST", body: JSON.stringify({ action_id, approved }) }),
  extractDocument: (customerId: string, file: File, documentType?: string) => {
    const form = new FormData();
    form.append("customer_id", customerId);
    form.append("file", file);
    if (documentType) form.append("document_type", documentType);
    return request<{ filename: string; document_type: string | null; fields: Record<string, unknown>; source: string }>(
      "/documents/extract",
      { method: "POST", body: form },
    );
  },
  knowledge: (key: string) => request<{ sources: KnowledgeSource[] }>("/admin/knowledge", undefined, key),
  uploadKnowledge: (key: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ title: string; url: string; indexed_chunks: number }>(
      "/admin/knowledge/upload",
      { method: "POST", body: form },
      key,
    );
  },
  addKnowledgeUrl: (key: string, url: string) =>
    request<{ title: string; url: string; indexed_chunks: number }>(
      "/admin/knowledge/url",
      { method: "POST", body: JSON.stringify({ url }) },
      key,
    ),
  reindex: (key: string) => request<{ updated: number; removed: number; indexed_sources: number; indexed_chunks: number }>(
    "/admin/knowledge/reindex", { method: "POST" }, key,
  ),
  removeKnowledge: (key: string, title: string) =>
    request<{ deleted: boolean; title: string }>(
      `/admin/knowledge?title=${encodeURIComponent(title)}`, { method: "DELETE" }, key,
    ),
  analytics: (key: string) => request<Analytics>("/admin/analytics", undefined, key),
  escalations: (key: string) => request<{ escalations: Escalation[] }>("/admin/escalations", undefined, key),
};

export function sourceHref(url: string): string {
  return new URL(url, `${API_BASE}/`).toString();
}
