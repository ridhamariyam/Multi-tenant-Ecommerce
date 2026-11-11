import type { DeliveryAddress, Invoice, Order, OrderStatus, OrderSummary, OrderTracking, ReturnReason } from "../types/order";
import { download, request } from "./client";

export const listOrders = (query: object) => request<OrderSummary[]>("/admin/orders", { query });
export const getOrder = (id: string) => request<Order>(`/admin/orders/${id}`);
export const updateStatus = (
  id: string,
  status: OrderStatus,
  extra: {
    note?: string | null;
    courier_name?: string | null;
    tracking_number?: string | null;
    tracking_url?: string | null;
    return_reason_id?: string | null;
    return_note?: string | null;
  } = {}
) => request<Order>(`/admin/orders/${id}/status`, { method: "PATCH", body: { status, ...extra } });
export const updateShipment = (id: string, data: { courier_name?: string | null; tracking_number?: string | null; tracking_url?: string | null }) =>
  request<Order>(`/admin/orders/${id}/shipment`, { method: "PATCH", body: data });
export const updateAddress = (id: string, data: DeliveryAddress & { reason?: string | null }) =>
  request<Order>(`/admin/orders/${id}/address`, { method: "PATCH", body: data });
export const getTracking = (id: string) => request<OrderTracking>(`/admin/orders/${id}/tracking`);
export const addTrackingEvent = (id: string, data: { description: string; location: string | null }) =>
  request<OrderTracking>(`/admin/orders/${id}/tracking-events`, { method: "POST", body: data });
export const getInvoice = (id: string) => request<Invoice>(`/admin/orders/${id}/invoice`);
export const downloadInvoicePdf = (id: string) => download(`/admin/orders/${id}/invoice/pdf`, undefined, "invoice.pdf");
export const downloadPackingSlip = (id: string) => download(`/admin/orders/${id}/packing-slip/pdf`, undefined, "packing-slip.pdf");
export const downloadShippingLabel = (id: string) => download(`/admin/orders/${id}/shipping-label/pdf`, undefined, "label.pdf");
export const downloadShippingLabels = (orderIds: string[]) =>
  download("/admin/orders/shipping-labels/pdf", undefined, "labels.pdf", { method: "POST", body: { order_ids: orderIds } });
export const listReturnReasons = (activeOnly = false) =>
  request<ReturnReason[]>("/admin/return-reasons", { query: { active_only: activeOnly } });
export const createReturnReason = (label: string) =>
  request<ReturnReason>("/admin/return-reasons", { method: "POST", body: { label } });
export const updateReturnReason = (id: string, data: Partial<Omit<ReturnReason, "id">>) =>
  request<ReturnReason>(`/admin/return-reasons/${id}`, { method: "PATCH", body: data });
