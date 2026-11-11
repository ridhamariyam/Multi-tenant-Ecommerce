export interface PeriodMetric {
  order_count: number;
  revenue: string;
  previous_order_count: number;
  previous_revenue: string;
  order_count_change_pct: number | null;
  revenue_change_pct: number | null;
}

export interface StockItem {
  product_id: string;
  product_name: string;
  variant_id: string | null;
  sku: string;
  available_quantity: number;
  low_stock_threshold: number;
}

export interface DashboardOverview {
  sales: { today: PeriodMetric; week: PeriodMetric; month: PeriodMetric; total_order_count: number; total_revenue: string };
  orders: Record<string, number>;
  products: { total: number };
  inventory: {
    low_stock_count: number;
    out_of_stock_count: number;
    low_stock_variants: StockItem[];
    out_of_stock_variants: StockItem[];
  };
  customers: { total: number; new_today: number; new_this_month: number };
  payments: { paid_count: number; pending_count: number; failed_count: number; refunded_count: number; today_paid_amount: string };
  recent_orders: {
    order_id: string;
    order_number: string;
    customer_email: string | null;
    total_amount: string;
    currency: string;
    order_status: string;
    payment_status: string;
    created_at: string;
  }[];
  insights: {
    attention: Record<"new_orders" | "awaiting_packing" | "awaiting_shipment" | "in_transit" | "advance_pending", number>;
    comparison: {
      today_orders: number;
      today_revenue: string;
      yesterday_orders: number;
      yesterday_revenue: string;
      last_week_orders: number;
      last_week_revenue: string;
      orders_vs_yesterday_pct: number | null;
      revenue_vs_yesterday_pct: number | null;
      orders_vs_last_week_pct: number | null;
      revenue_vs_last_week_pct: number | null;
    };
    last_30_days: {
      revenue: string;
      orders: number;
      average_order_value: string;
      return_rate: number | null;
      cancellation_rate: number | null;
      cod_orders: number;
      prepaid_orders: number;
      cod_share_pct: number | null;
      new_customers: number;
      returning_customers: number;
    };
    visitors_today: number | null;
    visitors_note: string;
  } | null;
}

export interface SalesTrendPoint { date: string; order_count: number; revenue: string }
