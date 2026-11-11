import type { Status } from "../../hooks/useAction";

interface StatusMessageProps {
  status: Status | null;
}

// Green success / red error banner. Renders nothing when there is no message.
function StatusMessage({ status }: StatusMessageProps) {
  if (!status) return null;
  return <div className={`status status-${status.type}`}>{status.text}</div>;
}

export default StatusMessage;
