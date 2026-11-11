import { useState } from "react";
import type { FormEvent } from "react";
import { createPost, deletePost, getPost, listPosts, updatePost } from "../../api/cms";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import DataTable from "../../components/common/DataTable";
import Field from "../../components/common/Field";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { BlogPost } from "../../types/cms";
import { slugProblem } from "../../utils/slug";
import { emptyToNull, formatDate } from "../../utils/formatters";
import MediaPicker from "./MediaPicker";
import ContentEditor from "./ContentEditor";
import type { ContentFormProps } from "./ContentEditor";
import ContentRowActions from "./ContentRowActions";
import MarkdownField from "./MarkdownField";
import { LiveState } from "./PublishControls";

function BlogTab() {
  const { can } = useAuth();
  const canEdit = can(P.cmsManage);
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const posts = useApi(() => listPosts({ status, page }), [status, page]);
  const [editingId, setEditingId] = useState<string | "new" | null>(null);
  const action = useAction();

  return (
    <div className="panel">
      <div className="filters">
        <select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All articles</option>
          <option value="DRAFT">Drafts</option>
          <option value="PUBLISHED">Published / scheduled</option>
        </select>
        {canEdit && <button className="primary" onClick={() => setEditingId("new")}>New article</button>}
      </div>
      <StatusMessage status={action.status} />
      <DataTable
        rows={posts.data as unknown as BlogPost[] | null}
        loading={posts.loading}
        error={posts.error}
        empty="No articles yet — click “New article” to write one."
        rowKey={(p) => p.id}
        onRowClick={(p) => setEditingId(p.id)}
        columns={[
          { key: "title", header: "Title" },
          { key: "author_name", header: "Author", render: (p) => p.author_name ?? "-" },
          { key: "tags", header: "Tags", render: (p) => p.tags.join(", ") || "-" },
          { key: "state", header: "State", render: (p) => <LiveState item={p} /> },
          { key: "published_at", header: "Publish date", render: (p) => formatDate(p.published_at) },
          {
            key: "actions",
            header: "",
            render: (p) => (
              <ContentRowActions
                kind="blog"
                row={p}
                path={`/blog/${p.slug}`}
                action={action}
                onEdit={() => setEditingId(p.id)}
                onDelete={() => deletePost(p.id)}
                onChanged={posts.reload}
              />
            ),
          },
        ]}
      />
      <Pagination meta={posts.meta} onPageChange={setPage} />
      {editingId && (
        <ContentEditor
          kind="blog"
          itemId={editingId === "new" ? null : editingId}
          canEdit={canEdit}
          load={getPost}
          create={createPost}
          update={updatePost}
          remove={deletePost}
          onClose={() => { setEditingId(null); posts.reload(); }}
          onCreated={setEditingId}
          renderForm={(form) => <PostForm {...form} canEdit={canEdit} />}
        />
      )}
    </div>
  );
}

function PostForm({ item: post, busy, onSubmit, canEdit }: ContentFormProps<BlogPost> & { canEdit: boolean }) {
  const [f, setF] = useState({
    title: post?.title ?? "",
    slug: post?.slug ?? "",
    excerpt: post?.excerpt ?? "",
    content: post?.content ?? "",
    featured_image_url: post?.featured_image_url ?? "",
    author_name: post?.author_name ?? "",
    category: post?.category ?? "",
    tags: post?.tags.join(", ") ?? "",
    seo_title: post?.seo_title ?? "",
    seo_description: post?.seo_description ?? "",
  });
  const [attempted, setAttempted] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((prev) => ({ ...prev, [k]: e.target.value }));
  const [uploading, setUploading] = useState(false);
  const titleError = !f.title.trim() ? "Article title is required." : null;
  const slugError = slugProblem(f.slug);
  const imageError = f.featured_image_url && !/^(\/|https?:\/\/)/.test(f.featured_image_url) ? "Featured image must start with / or https://" : null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (titleError || slugError || imageError) return;
    setAttempted(false);
    onSubmit({
      title: f.title.trim(),
      slug: emptyToNull(f.slug),
      excerpt: emptyToNull(f.excerpt),
      content: f.content,
      featured_image_url: emptyToNull(f.featured_image_url),
      author_name: emptyToNull(f.author_name),
      category: emptyToNull(f.category),
      tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean),
      seo_title: emptyToNull(f.seo_title),
      seo_description: emptyToNull(f.seo_description),
    });
  };

  return (
    <form className="form" onSubmit={submit} noValidate style={{ marginTop: 12 }}>
      <fieldset disabled={!canEdit} className="form" style={{ border: 0, padding: 0, margin: 0 }}>
        <div className="form-grid">
          <Field label="Title" required error={attempted ? titleError : null} guidance="Enter the title customers will see for this article." guidanceDismissible><input value={f.title} onChange={set("title")} /></Field>
          <Field label="URL slug" error={attempted ? slugError : null} hint="Blank = made from the title"><input value={f.slug} onChange={set("slug")} /></Field>
          <Field label="Author"><input value={f.author_name} onChange={set("author_name")} /></Field>
          <Field label="Category"><input value={f.category} onChange={set("category")} /></Field>
          <Field label="Tags" hint="Comma separated"><input value={f.tags} onChange={set("tags")} /></Field>
          <MediaPicker label="Featured image" hint="Shown at the top of the article and in the article list" value={f.featured_image_url} onChange={(v) => setF((prev) => ({ ...prev, featured_image_url: v }))} onUploadingChange={setUploading} />
          <Field label="Excerpt" wide><textarea value={f.excerpt} onChange={set("excerpt")} /></Field>
        </div>
        <MarkdownField label="Article text" value={f.content} onChange={(content) => setF((prev) => ({ ...prev, content }))} rows={16} />
        <div className="form-grid">
          <Field label="SEO title"><input value={f.seo_title} onChange={set("seo_title")} /></Field>
          <Field label="SEO description" wide><textarea value={f.seo_description} onChange={set("seo_description")} /></Field>
        </div>
      </fieldset>
      {attempted && (titleError || slugError || imageError) && <div className="status status-error" role="alert">{imageError || "Please complete all required fields before continuing."}</div>}
      {canEdit && <div className="form-actions"><button className="primary" disabled={busy || uploading}>{uploading ? "Waiting for the picture to finish uploading…" : "Save"}</button></div>}
    </form>
  );
}

export default BlogTab;
