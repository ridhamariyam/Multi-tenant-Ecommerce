import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { request } from "../api/client";

const MIN_PASSWORD = 10; // matches the API (app/merchants/constants.py)

function Shell({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="login-page">
      <main className="login-brand">
        <div className="login-card form">
          <div className="login-wordmark"><span className="brand-name">CliQ.</span><span className="brand-caption">LIMITLESS STYLE</span></div>
          <div className="login-heading">
            <h2>{title}</h2>
            {subtitle && <p className="muted">{subtitle}</p>}
          </div>
          {children}
          <p className="login-footnote muted"><Link to="/signin">Back to sign in</Link></p>
        </div>
      </main>
    </div>
  );
}

/** Ask for a reset link. The answer is the same whether or not the account exists. */
export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) return setError("Enter a valid email.");
    setBusy(true);
    setError(null);
    try {
      await request<null>("/platform/auth/password/forgot", { method: "POST", body: { email: email.trim() }, auth: false });
      setDone("If an account uses that email, a reset link is on its way. It works once, for one hour.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Forgot your password?" subtitle="We'll email you a link to choose a new one.">
      {done ? (
        <div className="status status-success" role="status">{done}</div>
      ) : (
        <form className="form" onSubmit={submit} noValidate>
          <label className="field">
            <span className="field-label">Email</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          </label>
          {error && <div className="status status-error" role="alert">{error}</div>}
          <button className="primary login-submit" type="submit" disabled={busy}>{busy ? "Sending…" : "Send reset link"}</button>
        </form>
      )}
    </Shell>
  );
}

/** Choose a new password from the emailed link (?token=…). */
export function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password.length < MIN_PASSWORD) return setError(`Use at least ${MIN_PASSWORD} characters.`);
    setBusy(true);
    setError(null);
    try {
      await request<null>("/platform/auth/password/reset", { method: "POST", body: { token, password }, auth: false });
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <Shell title="Reset link incomplete">
        <p>Open the link from the email again, or <Link to="/forgot-password">ask for a new one</Link>.</p>
      </Shell>
    );
  }
  return (
    <Shell title="Choose a new password" subtitle="You'll be signed out everywhere else.">
      {done ? (
        <div className="status status-success" role="status">Password changed. <Link to="/signin">Sign in</Link> with your new password.</div>
      ) : (
        <form className="form" onSubmit={submit} noValidate>
          <label className="field">
            <span className="field-label">New password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" minLength={MIN_PASSWORD} />
          </label>
          {error && <div className="status status-error" role="alert">{error}</div>}
          <button className="primary login-submit" type="submit" disabled={busy}>{busy ? "Saving…" : "Set new password"}</button>
        </form>
      )}
    </Shell>
  );
}
