import { createContext, useContext } from "react";

export interface AdminRefreshState {
  version: number;
  busy: boolean;
  refresh: () => void;
  begin: () => void;
  end: () => void;
}
export const AdminRefreshContext = createContext<AdminRefreshState | null>(null);
export const useAdminRefresh = () => useContext(AdminRefreshContext);
