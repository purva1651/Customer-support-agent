import type { ChatResult } from "../api";

export type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  result?: ChatResult;
  approvalRecorded?: boolean;
  serverMessageId?: number;
  humanAgent?: boolean;
};
export type Role = "customer" | "admin";
export type AdminTab = "knowledge" | "playground" | "analytics" | "escalations" | "redteam";
