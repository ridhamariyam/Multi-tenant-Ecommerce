import { request } from './client';
import type { CourierRate, CourierShipment, OrderShipments, Parcel, PickupLocation, ProviderSettings, ProviderSettingsInput } from '../types/shipment';

const root = (orderId: string) => `/admin/orders/${encodeURIComponent(orderId)}/shipments`;
export const getShipments = (orderId: string) => request<OrderShipments>(root(orderId));
export const getCourierRates = (orderId: string, parcel?: Parcel) =>
  request<{ couriers: CourierRate[] }>(`${root(orderId)}/rates`, { query: parcel });
export const createShipment = (orderId: string, parcel: Parcel | null, courierId: string | null) =>
  request<CourierShipment>(root(orderId), { method: 'POST', body: { package: parcel, courier_id: courierId } });
export const shipmentAction = (orderId: string, shipmentId: string, step: string, body = {}) =>
  request<CourierShipment>(`${root(orderId)}/${encodeURIComponent(shipmentId)}/${step}`, { method: 'POST', body });
export const getProviderSettings = () => request<ProviderSettings>('/admin/shipping/provider');
export const saveProviderSettings = (body: ProviderSettingsInput) =>
  request<ProviderSettings>('/admin/shipping/provider', { method: 'PUT', body });
export const getPickupLocations = () => request<PickupLocation[]>('/admin/shipping/provider/pickup-locations');
