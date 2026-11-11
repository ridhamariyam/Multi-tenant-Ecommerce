export type OrderStatus =
  | "PENDING"
  | "CONFIRMED"
  | "PROCESSING"
  | "PACKED"
  | "SHIPPED"
  | "OUT_FOR_DELIVERY"
  | "DELIVERED"
  | "CANCELLED"
  | "RETURN_REQUESTED"
  | "RETURNED"
  | "REFUNDED";

export const ORDER_STATUSES: OrderStatus[] = [
  "PENDING",
  "CONFIRMED",
  "PROCESSING",
  "PACKED",
  "SHIPPED",
  "OUT_FOR_DELIVERY",
  "DELIVERED",
  "CANCELLED",
  "RETURN_REQUESTED",
  "RETURNED",
  "REFUNDED",
];

// Mirrors the backend's LABEL_STATUSES; the download endpoint validates again.
export const SHIPPING_LABEL_STATUSES: readonly OrderStatus[] = ["CONFIRMED", "PROCESSING", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY"];

// Mirrors the backend's ALLOWED_TRANSITIONS; the backend still validates.
export const NEXT_STATUSES: Record<OrderStatus, OrderStatus[]> = {
  PENDING: ["CONFIRMED", "PROCESSING", "CANCELLED"],
  CONFIRMED: ["PROCESSING", "PACKED", "CANCELLED"],
  PROCESSING: ["PACKED", "SHIPPED", "CANCELLED"],
  PACKED: ["SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"],
  SHIPPED: ["OUT_FOR_DELIVERY", "DELIVERED", "RETURNED"],
  OUT_FOR_DELIVERY: ["DELIVERED", "RETURNED"],
  DELIVERED: [],
  CANCELLED: [],
  RETURN_REQUESTED: [],
  RETURNED: [],
  REFUNDED: [],
};

// Payment methods accepted by the order API; online methods use Razorpay.
export const PAYMENT_METHODS = ["UPI", "CREDIT_CARD", "DEBIT_CARD", "NET_BANKING", "CASH_ON_DELIVERY"] as const;

export type PaymentStatus = "PENDING" | "PARTIALLY_PAID" | "PAID" | "FAILED" | "REFUNDED";
export const PAYMENT_STATUSES: PaymentStatus[] = ["PENDING", "PARTIALLY_PAID", "PAID", "FAILED", "REFUNDED"];

export interface OrderSummary {
  id: string;
  order_number: string;
  status: OrderStatus;
  payment_status: PaymentStatus;
  total_amount: string;
  currency: string;
  payment_method: string;
  tracking_number: string | null;
  created_at: string;
}

export interface OrderItem {
  product_id: string;
  variant_id: string;
  product_name: string;
  variant_name: string;
  sku: string;
  quantity: number;
  unit_price: string;
  subtotal: string;
  hsn_code: string | null;
  gst_rate: string | null;
  discount_amount: string | null;
  taxable_amount: string | null;
  tax_amount: string | null;
}

export interface Payment {
  id: string;
  order_id: string;
  amount: string;
  currency: string;
  status: string;
  provider: "COD" | "PREPAID";
  purpose: "FULL" | "ADVANCE" | "BALANCE";
  remitted_at: string | null;
  remittance_reference: string | null;
  created_at: string;
}

export interface DeliveryAddress {
  full_name: string;
  phone: string;
  address_line_1: string;
  address_line_2: string | null;
  city: string;
  state: string;
  postal_code: string;
  country: string;
}

export interface Order {
  id: string;
  order_number: string;
  status: OrderStatus;
  payment_status: PaymentStatus;
  items: OrderItem[];
  subtotal: string;
  coupon_code: string | null;
  discount_amount: string;
  shipping_amount: string;
  cod_fee: string;
  tax_amount: string;
  total_amount: string;
  advance_amount: string;
  currency: string;
  payment_method: string;
  payment: Payment | null;
  payments: Payment[];
  gst: {
    gst_type: "INTRA_STATE" | "INTER_STATE" | null;
    place_of_supply: string | null;
    cgst_amount: string;
    sgst_amount: string;
    igst_amount: string;
  } | null;
  delivery_address: DeliveryAddress;
  contact_email: string | null;
  is_guest: boolean;
  estimated_delivery_date: string | null;
  shipment: { courier_name: string | null; tracking_number: string | null; tracking_url: string | null };
  return_reason: string | null;
  return_note: string | null;
  created_at: string;
}

export interface ReturnReason {
  id: string;
  label: string;
  is_active: boolean;
  position: number;
}

export interface TrackingEvent {
  status: OrderStatus | null;
  description: string;
  location: string | null;
  source: string;
  occurred_at: string;
}

export interface OrderTracking {
  order_number: string;
  status: OrderStatus;
  estimated_delivery_date: string | null;
  shipment: Order["shipment"];
  events: TrackingEvent[];
}

export interface Invoice {
  invoice_number: string;
  invoice_date: string;
  order_number: string;
  gst_type: string | null;
  place_of_supply: string | null;
  seller: { name: string | null; gstin: string | null; address: string | null; state: string | null };
  buyer: { name: string | null; address: string | null; state: string | null };
  lines: {
    description: string;
    sku: string | null;
    hsn_code: string | null;
    quantity: number;
    unit_price: string;
    discount: string;
    taxable_value: string;
    gst_rate: string;
    cgst_amount: string;
    sgst_amount: string;
    igst_amount: string;
    total: string;
  }[];
  totals: Record<string, string>;
  currency: string;
}
