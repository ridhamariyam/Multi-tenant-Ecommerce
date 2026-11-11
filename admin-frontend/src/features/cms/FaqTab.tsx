import { useState } from "react";
import {
  createFaq,
  createFaqCategory,
  deleteFaq,
  deleteFaqCategory,
  listFaqCategories,
  listFaqs,
  reorderFaqCategories,
  reorderFaqs,
  updateFaq,
  updateFaqCategory,
} from "../../api/cms";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import ConfirmButton from "../../components/common/ConfirmButton";
import Field from "../../components/common/Field";
import Modal from "../../components/common/Modal";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import { moveId, useDragSort } from "../../hooks/useDragSort";
import type { Faq, FaqCategory } from "../../types/cms";
import PublishControls from "./PublishControls";

function FaqTab() {
  const { can } = useAuth();
  const canEdit = can(P.cmsManage);
  const categories = useApi(() => listFaqCategories(), []);
  const faqs = useApi(() => listFaqs(), []);
  const action = useAction();
  const [newCategory, setNewCategory] = useState("");
  const [editing, setEditing] = useState<{ faq: Faq | null; categoryId: string } | null>(null);
  const reload = () => { categories.reload(); faqs.reload(); };

  const moveFaq = (cat: FaqCategory, list: Faq[], i: number, d: number) => {
    const ids = list.map((f) => f.id);
    const [x] = ids.splice(i, 1);
    ids.splice(i + d, 0, x);
    action.run(async () => { await reorderFaqs(cat.id, ids); faqs.reload(); }, null, "Could not reorder");
  };
  const sortedFaqs = (categoryId: string) =>
    (faqs.data ?? []).filter((f) => f.category_id === categoryId).sort((a, b) => a.position - b.position);

  // Questions are dragged within their category; categories by their title bar.
  const { dragProps: faqDrag } = useDragSort((moving, target) => {
    const all = faqs.data ?? [];
    const from = all.find((f) => f.id === moving);
    const to = all.find((f) => f.id === target);
    if (!from || !to || from.category_id !== to.category_id) {
      action.setStatus({ type: "error", text: "Drag questions within their category. To move one to another category, use Edit." });
      return;
    }
    const ids = moveId(sortedFaqs(from.category_id).map((f) => f.id), moving, target);
    action.run(async () => { await reorderFaqs(from.category_id, ids); faqs.reload(); }, null, "Could not reorder");
  }, canEdit);
  const { dragProps: categoryDrag } = useDragSort((moving, target) => {
    const ids = moveId((categories.data ?? []).map((c) => c.id), moving, target);
    action.run(async () => { await reorderFaqCategories(ids); categories.reload(); }, null, "Could not reorder");
  }, canEdit);

  return (
    <div className="panel">
      <StatusMessage status={action.status} />
      {(categories.error || faqs.error) && <div className="status status-error">{categories.error ?? faqs.error}</div>}
      {canEdit && (
        <form className="filters" onSubmit={(e) => { e.preventDefault(); if (!newCategory.trim()) return; action.run(async () => { await createFaqCategory({ name: newCategory.trim() }); setNewCategory(""); reload(); }, "Category added", "Could not add category"); }}>
          <input placeholder="New FAQ category (e.g. Shipping)" value={newCategory} onChange={(e) => setNewCategory(e.target.value)} />
          <button disabled={!newCategory.trim() || action.busy}>Add category</button>
        </form>
      )}
      {categories.data?.length === 0 && <p className="muted">No FAQ categories yet.</p>}
      {categories.data?.map((cat) => {
        const list = sortedFaqs(cat.id);
        return (
          <div key={cat.id} className="panel">
            <div className="panel-title" {...categoryDrag(cat.id)}>
              <h3>{canEdit && <span className="drag-handle" aria-hidden>⠿ </span>}{cat.name} {!cat.is_active && <Badge value="INACTIVE" />}</h3>
              <div className="toolbar">
                {canEdit && <button onClick={() => action.run(async () => { await updateFaqCategory(cat.id, { is_active: !cat.is_active }); reload(); }, "Category updated", "Could not update")}>{cat.is_active ? "Hide category" : "Show category"}</button>}
                {canEdit && <button onClick={() => setEditing({ faq: null, categoryId: cat.id })}>Add question</button>}
                {canEdit && <ConfirmButton message={`Delete ${cat.name} and all its questions?`} onConfirm={() => action.run(async () => { await deleteFaqCategory(cat.id); reload(); }, "Category deleted", "Could not delete")}>Delete</ConfirmButton>}
              </div>
            </div>
            {list.length === 0 && <p className="muted">No questions.</p>}
            <ul className="list-plain">
              {list.map((f, i) => (
                <li key={f.id} {...faqDrag(f.id)}>
                  <div className="panel-title">
                    <div>{canEdit && <span className="drag-handle" aria-hidden>⠿ </span>}<strong>{f.question}</strong><div className="muted" style={{ whiteSpace: "pre-wrap" }}>{f.answer}</div></div>
                    <div className="toolbar">
                      {canEdit && <button disabled={i === 0} onClick={() => moveFaq(cat, list, i, -1)} aria-label="Move up">↑</button>}
                      {canEdit && <button disabled={i === list.length - 1} onClick={() => moveFaq(cat, list, i, 1)} aria-label="Move down">↓</button>}
                      {canEdit && <button onClick={() => setEditing({ faq: f, categoryId: cat.id })}>Edit</button>}
                      {canEdit && <ConfirmButton message="Delete this question?" onConfirm={() => action.run(async () => { await deleteFaq(f.id); faqs.reload(); }, "Deleted", "Could not delete")}>Delete</ConfirmButton>}
                    </div>
                  </div>
                  <PublishControls kind="faqs" item={f} action={action} onDone={faqs.reload} />
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {editing && (
        <FaqModal
          faq={editing.faq}
          categories={categories.data ?? []}
          categoryId={editing.categoryId}
          busy={action.busy}
          onClose={() => setEditing(null)}
          onSave={async (data) => {
            const ok = await action.run(() => (editing.faq ? updateFaq(editing.faq.id, data) : createFaq(data)), "Question saved", "Could not save question");
            if (ok) { setEditing(null); faqs.reload(); }
          }}
        />
      )}
    </div>
  );
}

function FaqModal({ faq, categories, categoryId, busy, onClose, onSave }: { faq: Faq | null; categories: FaqCategory[]; categoryId: string; busy: boolean; onClose: () => void; onSave: (d: { category_id: string; question: string; answer: string }) => void }) {
  const [cat, setCat] = useState(faq?.category_id ?? categoryId);
  const [question, setQuestion] = useState(faq?.question ?? "");
  const [answer, setAnswer] = useState(faq?.answer ?? "");
  const [attempted, setAttempted] = useState(false);
  const categoryError = !cat ? "Choose a category." : null;
  const questionError = !question.trim() ? "Question is required." : null;
  const answerError = !answer.trim() ? "Answer is required." : null;
  return (
    <Modal title={faq ? "Edit question" : "New question"} onClose={onClose} showCloseButton={false}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); setAttempted(true); if (!categoryError && !questionError && !answerError) onSave({ category_id: cat, question: question.trim(), answer: answer.trim() }); }} noValidate>
        <Field label="Category" required error={attempted ? categoryError : null}>
          <select value={cat} onChange={(e) => setCat(e.target.value)}>{categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        </Field>
        <Field label="Question" required error={attempted ? questionError : null} guidance="Write the question as a customer would ask it." guidanceDismissible><input value={question} onChange={(e) => setQuestion(e.target.value)} /></Field>
        <Field label="Answer" required error={attempted ? answerError : null}><textarea value={answer} onChange={(e) => setAnswer(e.target.value)} /></Field>
        {attempted && (categoryError || questionError || answerError) && <div className="status status-error" role="alert">Please complete all required fields before continuing.</div>}
        <div className="form-actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" disabled={busy}>Save</button></div>
      </form>
    </Modal>
  );
}

export default FaqTab;
