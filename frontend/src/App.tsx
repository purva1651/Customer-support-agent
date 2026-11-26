import { useEffect, useState } from "react";
import { api } from "./api";
import { Brand } from "./components/Brand";
import { LoginPage } from "./features/auth/LoginPage";
import { AdminPage } from "./features/admin/AdminPage";
import { ChatPage } from "./features/chat/ChatPage";
import { makeId, readSavedMessages, sessionStorageKey } from "./shared/data";
import type { AdminTab, ChatMessage, Role } from "./shared/types";

function App() {
  const [role, setRole] = useState<Role | null>(null);
  const [adminKey, setAdminKey] = useState("");
  const [adminTab, setAdminTab] = useState<AdminTab>("knowledge");
  const [sessionId, setSessionId] = useState(makeId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [customerId, setCustomerId] = useState(() => localStorage.getItem("ticketbuddy-customer") || "C001");
  const [language, setLanguage] = useState(() => localStorage.getItem("ticketbuddy-language") || "English");
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => localStorage.setItem("ticketbuddy-customer", customerId), [customerId]);
  useEffect(() => localStorage.setItem("ticketbuddy-language", language), [language]);
  useEffect(() => {
    let cancelled = false;
    const checkHealth = async () => {
      try {
        await api.health();
        if (!cancelled) setOnline(true);
      } catch {
        if (!cancelled) setOnline(false);
      }
    };
    void checkHealth();
    const timer = window.setInterval(() => void checkHealth(), 10_000);
    window.addEventListener("focus", checkHealth);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("focus", checkHealth);
    };
  }, []);

  const customerLogin = (id: string, replyLanguage: string) => {
    const key = sessionStorageKey(id);
    const savedSessionId = localStorage.getItem(key) || makeId();
    localStorage.setItem(key, savedSessionId);
    setCustomerId(id);
    setLanguage(replyLanguage);
    setSessionId(savedSessionId);
    setMessages(readSavedMessages(id, savedSessionId));
    setRole("customer");
    window.history.replaceState(null, "", "#chat");
  };
  const adminLogin = (key: string) => {
    setAdminKey(key);
    setAdminTab("knowledge");
    setRole("admin");
    window.history.replaceState(null, "", "#admin");
  };
  const newChat = () => {
    const nextSessionId = makeId();
    localStorage.setItem(sessionStorageKey(customerId), nextSessionId);
    setSessionId(nextSessionId);
    setMessages([]);
  };
  const signOut = () => {
    setRole(null);
    setAdminKey("");
    setMessages([]);
    setSessionId(makeId());
    window.history.replaceState(null, "", "#login");
  };

  return (
    <div className="app-shell">
      {role ? <header className="topbar">
        <Brand />
        <span className="console-badge">agent console</span>
        <div className="topbar-spacer" />
        <div className="account-pill">{role === "customer" ? `${customerId} · ${customerId === "C001" ? "Aarav Patel" : "Maya Shah"}` : "Admin · Workspace"}</div>
        <button className="sign-out-button" onClick={signOut}>Log out</button>
      </header> : null}
      {!role ? (
        <LoginPage
          initialCustomerId={customerId}
          initialLanguage={language}
          onCustomerLogin={customerLogin}
          onAdminLogin={adminLogin}
        />
      ) : (
        <div className="workspace-shell">
          <aside className="app-rail" aria-label="Workspace navigation">
            {role === "customer" ? (
              <button className="rail-item active" aria-current="page"><span>▢</span>Chat</button>
            ) : <>
              <button className={adminTab === "knowledge" || adminTab === "playground" || adminTab === "analytics" || adminTab === "escalations" ? "rail-item active" : "rail-item"} onClick={() => setAdminTab("knowledge")}><span>▦</span>Admin</button>
              <button className={adminTab === "redteam" ? "rail-item active" : "rail-item"} onClick={() => setAdminTab("redteam")}><span>♢</span>Red team</button>
            </>}
          </aside>
          <div className="workspace-main">
            {role === "customer" ? (
              <ChatPage
                customerId={customerId}
                language={language}
                online={online}
                messages={messages}
                sessionId={sessionId}
                onNewChat={newChat}
                setCustomerId={setCustomerId}
                setLanguage={setLanguage}
                setMessages={setMessages}
                setOnline={setOnline}
              />
            ) : <AdminPage adminKey={adminKey} tab={adminTab} setTab={setAdminTab} />}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
