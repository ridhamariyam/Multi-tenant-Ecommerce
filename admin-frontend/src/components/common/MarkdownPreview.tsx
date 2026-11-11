import type { ReactNode } from "react";

// Shows text written in the CMS the way the storefront renders it: headings (#),
// paragraphs, bullet and numbered lists, **bold**, *italic* and [links](/path).
// Builds React elements only -- no HTML is injected.
function MarkdownPreview({ source }: { source: string }) {
  if (!source.trim()) return <p className="muted">Nothing written yet.</p>;
  return <div className="preview-box">{blocks(source)}</div>;
}

const LIST = /^\s*([-*]|\d+[.)])\s+/;

function blocks(source: string): ReactNode[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      const Tag = `h${Math.min(heading[1].length + 1, 5)}` as "h2" | "h3" | "h4" | "h5";
      out.push(<Tag key={i}>{inline(heading[2])}</Tag>);
      i += 1;
      continue;
    }
    if (LIST.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const items: ReactNode[] = [];
      while (i < lines.length && LIST.test(lines[i])) {
        items.push(<li key={i}>{inline(lines[i].replace(LIST, ""))}</li>);
        i += 1;
      }
      out.push(ordered ? <ol key={`l${i}`}>{items}</ol> : <ul key={`l${i}`}>{items}</ul>);
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^#{1,4}\s/.test(lines[i]) && !LIST.test(lines[i])) {
      para.push(lines[i].trim());
      i += 1;
    }
    out.push(<p key={`p${i}`}>{inline(para.join(" "))}</p>);
  }
  return out;
}

const TOKEN = /(\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)\s]+\))/g;

function inline(text: string): ReactNode[] {
  return text.split(TOKEN).filter(Boolean).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={i}>{part.slice(1, -1)}</em>;
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(part);
    if (link) {
      const safe = /^(\/(?!\/)|https?:\/\/)/.test(link[2]);
      return safe ? <a key={i} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</a> : <span key={i}>{link[1]}</span>;
    }
    return part;
  });
}

export default MarkdownPreview;
