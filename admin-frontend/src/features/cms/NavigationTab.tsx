import { useState } from "react";
import type { FormEvent } from "react";
import { listCategories } from "../../api/categories";
import { createNavItem, deleteNavItem, listNavigation, listPages, listPosts, reorderNav, updateNavItem } from "../../api/cms";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import ConfirmButton from "../../components/common/ConfirmButton";
import Field from "../../components/common/Field";
import GuidedControl from "../../components/guidance/GuidedControl";
import Modal from "../../components/common/Modal";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { LinkType, NavItem } from "../../types/cms";
import { LINK_TYPES } from "../../types/cms";
import { label } from "../../utils/formatters";
import ProductPicker from "./ProductPicker";
import { useDragSort } from "../../hooks/useDragSort";
import { idsAfterDrop, reorderedIds } from "./navigation";

type Menu = "HEADER" | "FOOTER";
const NO_TARGET: LinkType[] = ["HOME", "BLOG_INDEX", "FAQ"];


function NavigationTab() {
  const { can } = useAuth();
  const canEdit = can(P.cmsManage);
  const canPublish = can(P.cmsPublish);
  const [menu, setMenu] = useState<Menu>("HEADER");
  const tree = useApi(() => listNavigation(menu), [menu]);
  const action = useAction();
  const [editing, setEditing] = useState<NavItem | "new" | null>(null);
  const items = tree.data ?? [];

  const saveOrder = (ids: string[]) => action.run(async () => { await reorderNav(menu, ids); tree.reload(); }, null, "Could not reorder");
  const move = (id: string, d: number) => saveOrder(reorderedIds(items, id, d));
  const { dragProps } = useDragSort((moving, target) => {
    const ids = idsAfterDrop(items, moving, target);
    if (ids) saveOrder(ids);
    else action.setStatus({ type: "error", text: "Drag within the same level. To move under another item, use Edit → Show under." });
  }, canEdit);

  const row = (n: NavItem, siblings: NavItem[], depth: number) => {
    const i = siblings.indexOf(n);
    return (
      <li key={n.id}>
        <div className="panel-title" style={{ paddingLeft: depth * 24 }} {...dragProps(n.id)}>
          <span>{canEdit && <span className="drag-handle" aria-hidden>⠿ </span>}{depth ? "↳ " : ""}<strong>{n.label}</strong> <span className="muted">{label(n.link_type)} → {n.href}</span> {!n.is_active && <Badge value="INACTIVE" />}</span>
          <div className="toolbar">
            {canEdit && <button disabled={i === 0} onClick={() => move(n.id, -1)} aria-label="Move up">↑</button>}
            {canEdit && <button disabled={i === siblings.length - 1} onClick={() => move(n.id, 1)} aria-label="Move down">↓</button>}
            {canPublish && <button onClick={() => action.run(async () => { await updateNavItem(n.id, { is_active: !n.is_active }); tree.reload(); }, "Updated", "Could not update")}>{n.is_active ? "Hide" : "Show"}</button>}
            {canEdit && <button onClick={() => setEditing(n)}>Edit</button>}
            {canEdit && <ConfirmButton message={`Remove "${n.label}"${n.children.length ? " and its sub-items" : ""}?`} onConfirm={() => action.run(async () => { await deleteNavItem(n.id); tree.reload(); }, "Removed", "Could not remove")}>Remove</ConfirmButton>}
          </div>
        </div>
        {n.children.length > 0 && <ul className="list-plain">{n.children.map((c) => row(c, n.children, depth + 1))}</ul>}
      </li>
    );
  };

  return (
    <div className="panel">
      <div className="filters">
        <GuidedControl hint="Choose whether these links appear in the header or footer." dismissible><select aria-label="Menu" value={menu} onChange={(e) => setMenu(e.target.value as Menu)}>
          <option value="HEADER">Header menu</option>
          <option value="FOOTER">Footer menu</option>
        </select></GuidedControl>
        {canEdit && <button className="primary" onClick={() => setEditing("new")}>Add menu item</button>}
      </div>
      <StatusMessage status={action.status} />
      {tree.error && <div className="status status-error">{tree.error}</div>}
      {items.length === 0 && !tree.loading && <p className="muted">This menu is empty.</p>}
      <ul className="list-plain">{items.map((n) => row(n, items, 0))}</ul>
      {editing && (
        <NavModal
          item={editing === "new" ? null : editing}
          menu={menu}
          parents={items.filter((n) => editing === "new" || n.id !== editing.id)}
          canPublish={canPublish}
          busy={action.busy}
          onClose={() => setEditing(null)}
          onSave={async (data) => {
            const ok = await action.run(() => (editing === "new" ? createNavItem({ ...data, menu }) : updateNavItem(editing.id, data)), "Menu item saved", "Could not save menu item");
            if (ok) { setEditing(null); tree.reload(); }
          }}
        />
      )}
    </div>
  );
}

function NavModal({ item, menu, parents, canPublish, busy, onClose, onSave }: { item: NavItem | null; menu: Menu; parents: NavItem[]; canPublish: boolean; busy: boolean; onClose: () => void; onSave: (d: object) => void }) {
  const [text, setText] = useState(item?.label ?? "");
  const [linkType, setLinkType] = useState<LinkType>(item?.link_type ?? "CATEGORY");
  const [target, setTarget] = useState(item?.target ?? "");
  const [parentId, setParentId] = useState(item?.parent_id ?? "");
  const [active, setActive] = useState(item?.is_active ?? false);
  const [newTab, setNewTab] = useState(item?.open_in_new_tab ?? false);
  const [attempted, setAttempted] = useState(false);
  const categories = useApi(() => listCategories(), []);
  const pages = useApi(() => listPages({ page_size: 100 }), []);
  const posts = useApi(() => listPosts({ page_size: 100 }), []);
  const labelError = !text.trim() ? "Label is required." : null;
  const targetError = !NO_TARGET.includes(linkType) && !target.trim() ? "Choose where the link goes." : linkType === "URL" && !/^(\/|https?:\/\/)/.test(target.trim()) ? "URL must start with / or https://" : null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (labelError || targetError) return;
    setAttempted(false);
    onSave({ label: text.trim(), link_type: linkType, target: NO_TARGET.includes(linkType) ? null : target.trim(), parent_id: parentId || null, open_in_new_tab: newTab, ...(canPublish ? { is_active: active } : {}) });
  };

  return (
    <Modal title={item ? "Edit menu item" : `Add to ${menu.toLowerCase()} menu`} onClose={onClose} showCloseButton={false}>
      <form className="form" onSubmit={submit} noValidate>
        <Field label="Label" required error={attempted ? labelError : null} guidance="Enter the text customers will see in the menu." guidanceDismissible><input value={text} onChange={(e) => setText(e.target.value)} maxLength={100} /></Field>
        <Field label="Links to" required>
          <select value={linkType} onChange={(e) => { setLinkType(e.target.value as LinkType); setTarget(""); }}>
            {LINK_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
          </select>
        </Field>
        {linkType === "URL" && <Field label="URL" required error={attempted ? targetError : null}><input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="/sale or https://…" /></Field>}
        {linkType === "CATEGORY" && (
          <Field label="Category" required error={attempted ? targetError : null}>
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Choose…</option>
              {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
        )}
        {linkType === "PAGE" && (
          <Field label="Page" required error={attempted ? targetError : null}>
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Choose…</option>
              {pages.data?.map((p) => <option key={p.id} value={p.slug}>{p.title}</option>)}
            </select>
          </Field>
        )}
        {linkType === "BLOG_POST" && (
          <Field label="Article" required error={attempted ? targetError : null}>
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Choose…</option>
              {posts.data?.map((p) => <option key={p.id} value={p.slug}>{p.title}</option>)}
            </select>
          </Field>
        )}
        {linkType === "PRODUCT" && <div className="field"><span className="field-label">Product<span className="field-required" aria-hidden="true"> *</span></span><ProductPicker value={target ? [target] : []} onChange={(ids) => setTarget(ids[ids.length - 1] ?? "")} max={1} />{attempted && targetError && <span className="field-error" role="alert">{targetError}</span>}</div>}
        <Field label="Show under" hint="Menus nest one level deep">
          <select value={parentId} onChange={(e) => setParentId(e.target.value)}>
            <option value="">Top level</option>
            {parents.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </Field>
        <label className="check"><input type="checkbox" checked={newTab} onChange={(e) => setNewTab(e.target.checked)} /> Open in a new tab</label>
        {canPublish ? <label className="check"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Visible on the storefront</label> : <p className="muted">Saved hidden — someone with publish rights makes it visible.</p>}
        {attempted && (labelError || targetError) && <div className="status status-error" role="alert">Please complete all required fields before continuing.</div>}
        <div className="form-actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" disabled={busy}>Save</button></div>
      </form>
    </Modal>
  );
}

export default NavigationTab;
