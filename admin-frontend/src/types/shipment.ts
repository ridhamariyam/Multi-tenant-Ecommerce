export interface Parcel {
  weight_kg: string;
  length_cm: string;
  breadth_cm: string;
  height_cm: string;
}

export interface ShipmentEvent {
  source: string;
  provider_status_code: number | null;
  status_label: string | null;
  state: string | null;
  activity: string | null;
  location: string | null;
  occurred_at: string;
}

export interface CourierShipment {
  id: string;
  state: string;
  attempt: number;
  channel_order_id: string;
  awb_code: string | null;
  courier_name: string | null;
  tracking_url: string | null;
  label_url: string | null;
  manifest_url: string | null;
  pickup_scheduled_date: string | null;
  pickup_token_number: string | null;
  provider_etd: string | null;
  package: Parcel;
  payment_mode: 'COD' | 'PREPAID';
  declared_value: string;
  cod_amount: string;
  freight_charge: string | null;
  cod_charge: string | null;
  provider_status_label: string | null;
  pending_operation: string | null;
  operation_status: string | null;
  last_error: string | null;
  recovery_hint: string | null;
  last_synced_at: string | null;
  actions: string[];
  events: ShipmentEvent[];
}

export interface OrderShipments {
  provider_enabled: boolean;
  credentials_configured: boolean;
  can_create: boolean;
  create_blocked_reason: string | null;
  package_defaults: Parcel | null;
  current: CourierShipment | null;
  history: CourierShipment[];
}

export interface CourierRate {
  courier_id: string;
  courier_name: string;
  freight_charge: string | null;
  cod_charge: string | null;
  total_charge: string | null;
  cod_available: boolean;
  etd: string | null;
  estimated_delivery_days: string | null;
  is_recommended: boolean;
}

export interface ProviderSettings {
  is_enabled: boolean;
  credentials_configured: boolean;
  webhook_configured: boolean;
  pickup_location: string | null;
  pickup_postcode: string | null;
  fallback_email: string | null;
  package_defaults: Parcel | null;
  updated_at: string | null;
}

export type ProviderSettingsInput = Pick<ProviderSettings,
  'is_enabled' | 'pickup_location' | 'pickup_postcode' | 'fallback_email' | 'package_defaults'>;

export interface PickupLocation {
  name: string;
  postcode: string | null;
  city: string | null;
  state: string | null;
  is_primary: boolean;
}
