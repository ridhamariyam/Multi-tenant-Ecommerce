import { useEffect, useState } from "react";
import { aiCredits, cancelAiJob, createAiJob, listAiJobs, listVirtualModels, retryAiJob, reviewAiOutput } from "../../api/ai";
import type { AiJob } from "../../api/ai";
import { listProducts } from "../../api/products";
import Field from "../../components/common/Field";
import PageHeader from "../../components/common/PageHeader";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import "./ai.css";

const RUNNING = new Set(["queued", "starting", "processing"]);
const STATUS: Record<string, string> = {
  queued: "Queued", starting: "Starting", processing: "Generating", completed: "Ready", failed: "Failed", cancelled: "Cancelled",
};
const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);

/** Put products on CliQ's virtual models; results are reviewed before they reach the store. */
export default function AiStudioSection() {
  const credits = useApi(aiCredits, []);
  const jobs = useApi(listAiJobs, []);
  const running = (jobs.data ?? []).some((j) => RUNNING.has(j.status));

  // Generations take 20–90 s: refresh while any is running.
  const reloadJobs = jobs.reload;
  const reloadCredits = credits.reload;
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => { reloadJobs(); reloadCredits(); }, 5000);
    return () => window.clearInterval(timer);
  }, [running, reloadJobs, reloadCredits]);

  const c = credits.data;
  return (
    <div className="ai-page">
      <PageHeader title="AI studio" subtitle="Show your products on virtual models. Nothing is published until you approve it." />
      {credits.error && <div className="status status-error" role="alert">{credits.error}</div>}
      {c && !c.configured && (
        <div className="notice" role="status">AI generation isn't set up on the server yet (FASHN key needed). You can look around, but generating is off.</div>
      )}
      {c && <p className="ai-balance"><strong>{c.balance}</strong> AI credits left</p>}
      {c?.configured && <Generator balance={c.balance} prices={c.price_table} onQueued={() => { jobs.reload(); credits.reload(); }} />}
      <section className="panel" aria-label="Generations">
        <h3>Generations</h3>
        {jobs.error && <div className="status status-error" role="alert">{jobs.error}</div>}
        {jobs.data?.length === 0 && <p className="muted">Nothing generated yet.</p>}
        <ul className="ai-jobs">{(jobs.data ?? []).map((j) => <JobCard key={j.id} job={j} onChanged={() => { jobs.reload(); credits.reload(); }} />)}</ul>
      </section>
    </div>
  );
}

function Generator({ balance, prices, onQueued }: { balance: number; prices: Record<string, number>; onQueued: () => void }) {
  const products = useApi(() => listProducts({ page_size: 100, status: "ACTIVE" }), []);
  const models = useApi(listVirtualModels, []);
  const [form, setForm] = useState({ product_id: "", virtual_model_id: "", resolution: "1k", generation_mode: "balanced", num_images: 1 });
  const action = useAction();
  const cost = (prices[`${form.generation_mode}:${form.resolution}`] ?? 0) * form.num_images;

  return (
    <form
      className="panel form"
      aria-label="New generation"
      onSubmit={async (e) => {
        e.preventDefault();
        if (await action.run(() => createAiJob(form, newKey()), "Queued. Results appear below in about a minute.", "Could not start")) onQueued();
      }}
    >
      <h3>New generation</h3>
      <StatusMessage status={action.status} />
      <div className="form-grid">
        <Field label="Product">
          <select required value={form.product_id} onChange={(e) => setForm({ ...form, product_id: e.target.value })}>
            <option value="">Choose a product</option>
            {(products.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Model">
          <select required value={form.virtual_model_id} onChange={(e) => setForm({ ...form, virtual_model_id: e.target.value })}>
            <option value="">Choose a model</option>
            {(models.data ?? []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </Field>
        <Field label="Quality">
          <select value={form.generation_mode} onChange={(e) => setForm({ ...form, generation_mode: e.target.value })}>
            <option value="fast">Fast</option><option value="balanced">Balanced</option><option value="quality">Best quality</option>
          </select>
        </Field>
        <Field label="Resolution">
          <select value={form.resolution} onChange={(e) => setForm({ ...form, resolution: e.target.value })}>
            <option value="1k">1K</option><option value="2k">2K</option><option value="4k">4K</option>
          </select>
        </Field>
        <Field label="Images">
          <select value={form.num_images} onChange={(e) => setForm({ ...form, num_images: Number(e.target.value) })}>
            {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Field>
      </div>
      <p className="muted">Costs <strong>{cost}</strong> credits{cost > balance ? " — not enough credits" : ""}. Unused credits come back if a generation fails.</p>
      <button className="primary" disabled={action.busy || cost > balance}>Generate</button>
    </form>
  );
}

function JobCard({ job, onChanged }: { job: AiJob; onChanged: () => void }) {
  const action = useAction();
  return (
    <li className="ai-job">
      <div className="ai-job-head">
        <span className={`badge ${job.status === "completed" ? "badge-ok" : job.status === "failed" ? "badge-bad" : "badge-warn"}`}>{STATUS[job.status] ?? job.status}</span>
        <span className="muted">{new Date(job.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })} · {job.num_images} image{job.num_images === 1 ? "" : "s"} · {job.credits_charged ?? job.credits_reserved} credits</span>
        {job.status === "queued" && (
          <button type="button" className="btn btn-sm" onClick={async () => { if (await action.run(() => cancelAiJob(job.id), null, "Could not cancel")) onChanged(); }}>Cancel</button>
        )}
        {(job.status === "failed" || job.status === "completed") && (
          <button type="button" className="btn btn-sm" onClick={async () => { if (await action.run(() => retryAiJob(job.id), null, "Could not retry")) onChanged(); }}>
            {job.status === "failed" ? "Try again" : "Generate again"}
          </button>
        )}
      </div>
      {job.error_message && <p className="platform-reason">{job.error_message}</p>}
      <StatusMessage status={action.status} />
      <div className="ai-outputs">
        {job.outputs.map((o) => (
          <figure key={o.id} className="ai-output">
            {o.url && <img src={o.url} alt="Generated product photo" loading="lazy" />}
            <figcaption>
              {o.review_status === "PENDING" ? (
                <>
                  <button type="button" className="primary btn-sm" onClick={async () => { if (await action.run(() => reviewAiOutput(o.id, "APPROVED"), "Added to the product's photos.", "Could not save")) onChanged(); }}>Use on product</button>
                  <button type="button" className="btn btn-sm" onClick={async () => { if (await action.run(() => reviewAiOutput(o.id, "REJECTED"), null, "Could not save")) onChanged(); }}>Reject</button>
                </>
              ) : (
                <span className="muted">{o.review_status === "APPROVED" ? "On the product" : "Rejected"}</span>
              )}
            </figcaption>
          </figure>
        ))}
      </div>
    </li>
  );
}
