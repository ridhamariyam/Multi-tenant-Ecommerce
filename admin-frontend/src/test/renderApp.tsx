import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import { saveTokens } from "../utils/storage";

/** Render the signed-in admin app at `path` (mock /auth/me with mockFetch first). */
export function renderApp(path: string) {
  saveTokens("a", "r");
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthProvider>
  );
}
