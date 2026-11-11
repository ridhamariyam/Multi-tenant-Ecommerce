import { useCallback, useState } from "react";

export interface Status {
  type: "success" | "error";
  text: string;
}

// Wraps one API call with a loading flag and a readable success/error message.
//
//   const { busy, status, run } = useAction();
//   await run(() => createCategory(data), "Category created", "Failed to create category");
//
// `run` returns the call's result, or undefined if it failed.
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);

  const run = useCallback(
    async <T,>(action: () => Promise<T>, successText: string | null, failurePrefix: string) => {
      setBusy(true);
      setStatus(null);
      try {
        const result = await action();
        if (successText) setStatus({ type: "success", text: successText });
        return result;
      } catch (error) {
        const reason = error instanceof Error ? error.message : String(error);
        setStatus({ type: "error", text: `${failurePrefix}: ${reason}` });
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    []
  );

  return { busy, status, setStatus, run };
}
