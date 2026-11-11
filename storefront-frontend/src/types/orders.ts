export type OrderStatus =
  | 'PENDING'
  | 'CONFIRMED'
  | 'PROCESSING'
  | 'PACKED'
  | 'SHIPPED'
  | 'OUT_FOR_DELIVERY'
  | 'DELIVERED'
  | 'CANCELLED'
  | 'RETURN_REQUESTED'
  | 'RETURNED'
  | 'REFUNDED';

/** PARTIALLY_PAID: a cash order whose advance is paid, with the balance still due. */
export type PaymentStatus = 'PENDING' | 'PARTIALLY_PAID' | 'PAID' | 'FAILED' | 'REFUNDED';

/**
 * How the money arrives: cash at the door, an advance recorded by the store,
 * or online through Razorpay.
 */
export type PaymentProvider = 'COD' | 'PREPAID' | 'RAZORPAY';

/** What the shopper picks at checkout. Everything but cash is paid through Razorpay. */
export type PaymentMethod = 'UPI' | 'CREDIT_CARD' | 'DEBIT_CARD' | 'NET_BANKING' | 'CASH_ON_DELIVERY';

export const ONLINE_PAYMENT_METHODS: readonly PaymentMethod[] = ['UPI', 'CREDIT_CARD', 'DEBIT_CARD', 'NET_BANKING'];

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  UPI: 'UPI',
  CREDIT_CARD: 'Credit Card',
  DEBIT_CARD: 'Debit Card',
  NET_BANKING: 'Net Banking',
  CASH_ON_DELIVERY: 'Cash on Delivery',
};

/** Which status an order may move to next. Mirrors ALLOWED_TRANSITIONS. */
export const ALLOWED_TRANSITIONS: Record<OrderStatus, readonly OrderStatus[]> = {
  PENDING: ['CONFIRMED', 'PROCESSING', 'CANCELLED'],
  CONFIRMED: ['PROCESSING', 'PACKED', 'CANCELLED'],
  PROCESSING: ['PACKED', 'SHIPPED', 'CANCELLED'],
  PACKED: ['SHIPPED', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED'],
  SHIPPED: ['OUT_FOR_DELIVERY', 'DELIVERED', 'RETURNED'],
  OUT_FOR_DELIVERY: ['DELIVERED', 'RETURNED'],
  DELIVERED: [],
  CANCELLED: [],
  RETURN_REQUESTED: [],
  RETURNED: [],
  REFUNDED: [],
};

export interface Payment {
  id: string;
  order_id: string;
  amount: string;
  currency: string;
  status: PaymentStatus;
  provider: PaymentProvider;
  /** Razorpay's order id, set for online payments. Checkout opens against it. */
  gateway_order_id?: string | null;
  gateway_payment_id?: string | null;
  created_at: string;
}

/** What Razorpay Checkout hands the browser after a successful payment. */
export interface RazorpayVerification {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

/** Everything the browser needs to open Razorpay Checkout for one order. */
export interface OnlinePaymentRequest {
  orderId: string;
  orderNumber: string;
  razorpayOrderId: string;
  /** In paise. */
  amount: number;
  currency: string;
  method: PaymentMethod;
  name: string;
  contact: string;
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

export interface OrderItem {
  product_id: string;
  variant_id: string;
  product_name: string;
  variant_name: string;
  sku: string;
  quantity: number;
  unit_price: string;
  subtotal: string;
  /** This line's share of the order discount, when the order was priced line by line. */
  discount_amount?: string | null;
}

export interface Shipment {
  courier_name: string | null;
  tracking_number: string | null;
  tracking_url: string | null;
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
  /** Extra charged for paying cash. */
  cod_fee?: string;
  tax_amount: string;
  total_amount: string;
  /** The part of a cash order's total payable online up front. */
  advance_amount?: string;
  currency: string;
  payment_method?: PaymentMethod;
  /** Whether the shopper may cancel it now. The backend decides; it also enforces it. */
  can_cancel: boolean;
  payment: Payment | null;
  /** Every payment on the order, e.g. a COD advance alongside the balance. */
  payments?: Payment[];
  delivery_address: DeliveryAddress;
  contact_email?: string | null;
  estimated_delivery_date?: string | null;
  shipment?: Shipment;
  return_reason?: string | null;
  return_note?: string | null;
  created_at: string;
}

export type TrackingSource = 'SYSTEM' | 'ADMIN' | 'COURIER';

export interface TrackingEvent {
  status: OrderStatus | null;
  description: string;
  location: string | null;
  source: TrackingSource;
  occurred_at: string;
}

/** `GET /orders/{id}/tracking`: the order's recorded history, oldest first. */
export interface OrderTracking {
  order_number: string;
  status: OrderStatus;
  estimated_delivery_date: string | null;
  shipment: Shipment;
  events: TrackingEvent[];
  courier?: CourierTracking | null;
}

export interface CourierTracking {
  state: string;
  status_label: string | null;
  courier_name: string | null;
  awb_code: string | null;
  tracking_url: string | null;
  provider_etd: string | null;
  last_event_at: string | null;
}

export interface InvoiceParty {
  name: string | null;
  gstin: string | null;
  address: string | null;
  state: string | null;
  state_code: string | null;
}

export interface InvoiceLine {
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
}

export interface InvoiceTotals {
  subtotal: string;
  discount: string;
  shipping: string;
  cod_fee: string;
  taxable_value: string;
  cgst_amount: string;
  sgst_amount: string;
  igst_amount: string;
  tax_amount: string;
  total: string;
}

/** Exact invoice lines and totals returned by GET /orders/{id}/invoice. */
export interface InvoiceRead {
  invoice_number: string;
  invoice_date: string;
  order_number: string;
  order_status: OrderStatus;
  gst_type: string | null;
  tax_split_known: boolean;
  place_of_supply: string | null;
  seller: InvoiceParty;
  buyer: InvoiceParty;
  lines: InvoiceLine[];
  totals: InvoiceTotals;
  currency: string;
}

/** A row in a list of orders. Carries no items, so listings stay cheap. */
export interface OrderSummary {
  id: string;
  order_number: string;
  status: OrderStatus;
  payment_status: PaymentStatus;
  total_amount: string;
  currency: string;
  payment_method?: PaymentMethod;
  tracking_number?: string | null;
  created_at: string;
}

export interface CheckoutItem {
  product_id: string;
  variant_id: string;
  product_name: string;
  variant_name: string;
  sku: string;
  quantity: number;
  unit_price: string;
  subtotal: string;
}

/** The only place tax, shipping and the order total can be read before placing. */
export interface CheckoutPreview {
  items: CheckoutItem[];
  subtotal: string;
  coupon_code: string | null;
  discount_amount: string;
  shipping_amount: string;
  tax_amount: string;
  total_amount: string;
  /** Extra charged for paying cash; present when the backend prices it. */
  cod_fee?: string;
  payment_method?: PaymentMethod;
  cod?: { available: boolean; message: string | null } | null;
}

export interface CouponApplyResult {
  code: string;
  discount_amount: string;
  currency: string;
}

/** An active automatic discount advertised by the storefront. */
export interface Offer {
  code: string;
  discount_type: 'PERCENTAGE' | 'FIXED_AMOUNT' | 'FREE_SHIPPING' | 'BOGO';
  discount_value: string;
  min_order_amount: string | null;
  min_quantity: number | null;
  buy_quantity: number | null;
  get_quantity: number | null;
  first_order_only: boolean;
  category_ids: string[];
  expires_at: string | null;
  currency: string;
}
