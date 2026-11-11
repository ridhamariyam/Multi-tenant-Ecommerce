import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const MIN_PASSWORD = 10; // matches the API (app/merchants/constants.py)

/** Create a merchant account; brands are created right after, on the brand list. */
function Register() {
  const { merchant, merchantRegister } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", phone: "", password: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (merchant) return <Navigate to="/brands" replace />;

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [key]: e.target.value });

  async function submit(event: FormEvent) {
    event.preventDefault();
    const local: Record<string, string> = {};
    if (!form.name.trim()) local.name = "Enter your name.";
    if (!/^\S+@\S+\.\S+$/.test(form.email.trim())) local.email = "Enter a valid email.";
    if (form.password.length < MIN_PASSWORD) local.password = `Use at least ${MIN_PASSWORD} characters.`;
    setErrors(local);
    if (Object.keys(local).length) return;

    setBusy(true);
    setError(null);
    try {
      await merchantRegister({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        phone: form.phone.trim() || null,
      });
      navigate("/brands", { replace: true, state: { welcome: true } });
    } catch (e) {
      if (e instanceof ApiError && e.details.length) {
        setErrors(Object.fromEntries(e.details.filter((d) => d.field).map((d) => [String(d.field).split(".").pop(), (d.message ?? "").replace(/^Value error,\s*/i, "")])));
      }
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const field = (key: keyof typeof form, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label className="field">
      <span className="field-label">{label}</span>
      <input value={form[key]} onChange={set(key)} aria-invalid={!!errors[key]} {...props} />
      {errors[key] && <span className="field-error" role="alert">{errors[key]}</span>}
    </label>
  );

  return (
    <div className="login-page">
      <main className="login-brand">
        <form className="login-card form" onSubmit={submit} noValidate>
          <div className="login-wordmark"><span className="brand-name">CliQ.</span><span className="brand-caption">LIMITLESS STYLE</span></div>
          <div className="login-heading">
            <h2>Create your merchant account</h2>
            <p className="muted">Then create your first brand and its store.</p>
          </div>
          {field("name", "Your name", { autoComplete: "name" })}
          {field("email", "Email", { type: "email", autoComplete: "email" })}
          {field("phone", "Phone (optional)", { type: "tel", autoComplete: "tel" })}
          {field("password", "Password", { type: "password", autoComplete: "new-password", minLength: MIN_PASSWORD })}
          {error && <div className="status status-error" role="alert">{error}</div>}
          <button className="primary login-submit" type="submit" disabled={busy}>
            {busy ? "Creating account…" : "Create account"}
          </button>
          <p className="login-footnote muted">
            Already have an account? <Link to="/signin">Sign in</Link>
          </p>
        </form>
      </main>
    </div>
  );
}

export default Register;
