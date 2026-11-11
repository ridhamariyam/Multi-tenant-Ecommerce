import type { TokenPair, UserProfile } from "../types/user";
import { request } from "./client";

export type LoginRole = "admin" | "staff";

export function login(role: LoginRole, identifier: string, password: string) {
  return request<TokenPair>(`/${role}/auth/login`, {
    method: "POST",
    body: { identifier, password },
    auth: false,
  });
}

export function getMe() {
  return request<UserProfile>("/auth/me");
}

export function logout(refreshToken: string) {
  return request<null>("/auth/logout", { method: "POST", body: { refresh_token: refreshToken }, auth: false });
}
