import { useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import type { LoginRole } from "../api/auth";
import { STOREFRONT_ORIGIN } from "../api/client";
import { useAuth } from "../auth/AuthContext";

function Login() {
  const { user, login, notice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [role, setRole] = useState<LoginRole>("admin");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? "/";
  if (user) return <Navigate to={from} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!identifier.trim() || !password) {
      setError("Enter your email or phone and password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(role, identifier.trim(), password);
      navigate(from, { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <main className="login-brand">
        <form className="login-card form" onSubmit={submit} noValidate>
          <div className="login-wordmark"><span className="brand-name">CliQ.</span><span className="brand-caption">LIMITLESS STYLE</span></div>
          <div className="login-heading">
            <h2>Sign in</h2>
            <p className="muted">Use the email or phone and password your store gave you.</p>
          </div>
          {notice && <div className="notice">{notice}</div>}
          <div className="tabs login-tabs" role="tablist">
            {(["admin", "staff"] as LoginRole[]).map((r) => (
              <button type="button" key={r} role="tab" aria-selected={role === r} className={role === r ? "active" : ""} onClick={() => setRole(r)}>
                {r === "admin" ? "Admin" : "Staff"}
              </button>
            ))}
          </div>
          <label className="field">
            <span className="field-label">Email or phone</span>
            <input value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" placeholder="you@cliq.example" />
          </label>
          <label className="field">
            <span className="field-label">Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </label>
          {error && <div className="status status-error" role="alert">{error}</div>}
          <button className="primary login-submit" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          {STOREFRONT_ORIGIN && (
            <p className="login-footnote muted">
              Shopping with us? <a href={STOREFRONT_ORIGIN}>Sign in on the store</a>
            </p>
          )}
        </form>
      </main>
    </div>
  );
}

export default Login;
