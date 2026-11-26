import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../../api";
import { Brand } from "../../components/Brand";
import type { Role } from "../../shared/types";

export function LoginPage({
  initialCustomerId,
  initialLanguage,
  onCustomerLogin,
  onAdminLogin,
}: {
  initialCustomerId: string;
  initialLanguage: string;
  onCustomerLogin: (customerId: string, language: string) => void;
  onAdminLogin: (adminKey: string) => void;
}) {
  const [loginType, setLoginType] = useState<Role>("customer");
  const [customerId, setCustomerId] = useState(initialCustomerId);
  const [language, setLanguage] = useState(initialLanguage);
  const [adminKey, setAdminKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (loginType === "customer") {
      onCustomerLogin(customerId, language);
      return;
    }
    if (!adminKey.trim()) {
      setError("Enter the admin API key to continue.");
      return;
    }
    setBusy(true);
    try {
      await api.knowledge(adminKey.trim());
      onAdminLogin(adminKey.trim());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Admin sign-in failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login-page">
      <div className="login-top"><Brand /><span>Support that keeps every trip moving</span></div>
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-art">
          <div className="login-art-icon">✦</div>
          <p className="login-kicker">TICKETBUDDY SUPPORT</p>
          <h1>Welcome back.</h1>
          <p>Get help with bookings, tickets, refunds, and more.</p>
          <div className="login-art-foot"><span className="online-dot" /> Your support assistant is ready</div>
        </div>
        <div className="login-form-side">
          <div className="login-heading">
            <span>Sign in to continue</span>
            <h2 id="login-title">Choose your account</h2>
          </div>
          <div className="login-type-switch" role="tablist" aria-label="Account type">
            <button type="button" role="tab" aria-selected={loginType === "customer"} className={loginType === "customer" ? "login-type active" : "login-type"} onClick={() => { setLoginType("customer"); setError(""); }}>Customer</button>
            <button type="button" role="tab" aria-selected={loginType === "admin"} className={loginType === "admin" ? "login-type active" : "login-type"} onClick={() => { setLoginType("admin"); setError(""); }}>Admin</button>
          </div>
          <form className="login-form" onSubmit={(event) => void submit(event)}>
            {loginType === "customer" ? <>
              <label htmlFor="customer-login-id">Customer ID</label>
              <select id="customer-login-id" value={customerId} onChange={(event) => setCustomerId(event.target.value)}>
                <option value="C001">C001 · Demo customer 1</option>
                <option value="C002">C002 · Demo customer 2</option>
              </select>
              <label htmlFor="customer-login-language">Reply language</label>
              <select id="customer-login-language" value={language} onChange={(event) => setLanguage(event.target.value)}>
                <option>English</option><option>Hindi</option><option>Gujarati</option>
              </select>
              <p className="login-help">This demo uses customer IDs only. Customer passwords are not configured.</p>
              <button className="login-submit" type="submit">Continue to customer chat <span>→</span></button>
            </> : <>
              <label htmlFor="admin-login-key">Admin API key</label>
              <input id="admin-login-key" type="password" value={adminKey} onChange={(event) => setAdminKey(event.target.value)} placeholder="Enter the key from your .env file" autoComplete="current-password" />
              <p className="login-help">Your key is checked by the support API and stays in memory for this session.</p>
              <button className="login-submit" type="submit" disabled={busy}>{busy ? "Checking access…" : "Continue to admin panel"}<span>→</span></button>
            </>}
          </form>
          {error && <div className="error-banner login-error" role="alert">{error}</div>}
        </div>
      </section>
      <p className="login-footer">By continuing, you’ll open the TicketBuddy demo support workspace.</p>
    </main>
  );
}
