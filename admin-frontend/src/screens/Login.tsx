import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import type { LoginRole } from "../api/auth";
import { STOREFRONT_ORIGIN } from "../api/client";
import { useAuth } from "../auth/AuthContext";

type Mode = "merchant" | LoginRole;

const MODES: { key: Mode; label: string }[] = [
  { key: "merchant", label: "Merchant" },
  { key: "admin", label: "Store admin" },
  { key: "staff", label: "Staff" },
];

function Login() {
  const { user, merchant, login, merchantLogin, notice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState<Mode>("merchant");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? "/";
  if (user) return <Navigate to={from} replace />;
  if (merchant) return <Navigate to="/brands" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!identifier.trim() || !password) {
      setError(mode === "merchant" ? "Enter your email and password." : "Enter your email or phone and password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (mode === "merchant") {
        await merchantLogin(identifier.trim(), password);
        navigate("/brands", { replace: true });
      } else {
        await login(mode, identifier.trim(), password);
        navigate(from, { replace: true });
      }
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
            <p className="muted">
              {mode === "merchant"
                ? "One account for every brand you run on CliQ."
                : "Use the email or phone and password your store gave you."}
            </p>
          </div>
          {notice && <div className="notice">{notice}</div>}
          <div className="tabs login-tabs" role="tablist" aria-label="Account type">
            {MODES.map((m) => (
              <button type="button" key={m.key} role="tab" aria-selected={mode === m.key} className={mode === m.key ? "active" : ""} onClick={() => { setMode(m.key); setError(null); }}>
                {m.label}
              </button>
            ))}
          </div>
          <label className="field">
            <span className="field-label">{mode === "merchant" ? "Email" : "Email or phone"}</span>
            <input
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              autoComplete="username"
              type={mode === "merchant" ? "email" : "text"}
              placeholder="you@yourbrand.com"
            />
          </label>
          <label className="field">
            <span className="field-label">Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </label>
          {error && <div className="status status-error" role="alert">{error}</div>}
          <button className="primary login-submit" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          {mode === "merchant" && (
            <p className="login-footnote muted">
              New to CliQ? <Link to="/register">Create a merchant account</Link>
            </p>
          )}
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
