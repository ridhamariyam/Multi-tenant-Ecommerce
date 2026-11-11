import { createContext } from "react";

export interface ContextualGuidanceState {
  enabled: boolean;
  dismissed: string[];
  dismissPage: (key: string) => void;
}

export const GuidanceContext = createContext<ContextualGuidanceState | null>(null);
