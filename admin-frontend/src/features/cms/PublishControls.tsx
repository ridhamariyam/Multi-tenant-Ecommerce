import { useState } from "react";
import { publish, unpublish } from "../../api/cms";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import type { useAction } from "../../hooks/useAction";
import type { ContentStatus } from "../../types/cms";
import { formatDate, localInputToIso } from "../../utils/formatters";

interface Item {
  id: string;
  status: ContentStatus;
  published_at: string | null;
  is_live: boolean;
}

/** Status line plus publish-now / schedule / unpublish for pages, FAQs and articles. */
export function LiveState({ item }: { item: Item }) {
  // A draft that was published before has been unpublished (taken off the website).
  if (item.status === "DRAFT") return <Badge value={item.published_at ? "UNPUBLISHED" : "DRAFT"} />;
  if (item.is_live) return <Badge value="PUBLISHED" />;
  return <span className="badge badge-info">SCHEDULED {formatDate(item.published_at)}</span>;
}

function PublishControls({ kind, item, action, onDone }: { kind: "pages" | "faqs" | "blog"; item: Item; action: ReturnType<typeof useAction>; onDone: () => void }) {
  const { can } = useAuth();
  const [when, setWhen] = useState("");
  if (!can(P.cmsPublish)) return <LiveState item={item} />;
  return (
    <div className="toolbar">
      <LiveState item={item} />
      {item.status === "PUBLISHED" ? (
        <button onClick={() => action.run(async () => { await unpublish(kind, item.id); onDone(); }, "Unpublished", "Could not unpublish")} disabled={action.busy}>Unpublish</button>
      ) : (
        <>
          <button className="primary" onClick={() => action.run(async () => { await publish(kind, item.id, null); onDone(); }, "Published", "Could not publish")} disabled={action.busy}>Publish now</button>
          <input type="datetime-local" aria-label="Schedule for" value={when} onChange={(e) => setWhen(e.target.value)} style={{ width: 200 }} />
          <button disabled={!when || action.busy} onClick={() => action.run(async () => { await publish(kind, item.id, localInputToIso(when)); setWhen(""); onDone(); }, "Scheduled", "Could not schedule")}>Schedule</button>
        </>
      )}
    </div>
  );
}

export default PublishControls;
