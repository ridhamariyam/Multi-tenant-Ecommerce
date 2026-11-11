import type { OrderSummary } from "../types/order";
import type { CustomerDetail, CustomerNote, CustomerSummary } from "../types/user";
import { request } from "./client";

export const listCustomers = (query: object) => request<CustomerSummary[]>("/admin/customers", { query });
export const getCustomer = (id: string) => request<CustomerDetail>(`/admin/customers/${id}`);
export const getCustomerOrders = (id: string, page = 1) =>
  request<OrderSummary[]>(`/admin/customers/${id}/orders`, { query: { page } });
export const setCustomerTags = (id: string, tags: string[]) =>
  request<string[]>(`/admin/customers/${id}/tags`, { method: "PUT", body: { tags } });
export const addCustomerNote = (id: string, body: string) =>
  request<CustomerNote>(`/admin/customers/${id}/notes`, { method: "POST", body: { body } });
export const setOrderBlock = (id: string, blocked: boolean, reason: string | null) =>
  request<CustomerSummary>(`/admin/customers/${id}/order-block`, { method: "PUT", body: { blocked, reason } });
export const deleteCustomerNote = (id: string, noteId: string) =>
  request<null>(`/admin/customers/${id}/notes/${noteId}`, { method: "DELETE" });
