export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserProfile {
  id: string;
  tenant_id: string;
  phone: string | null;
  email: string | null;
  name: string | null;
  role: "ADMIN" | "STAFF" | "CUSTOMER";
  status: string;
  is_verified: boolean;
  permissions: string[];
}

export interface StaffMember {
  id: string;
  name: string | null;
  email: string | null;
  phone: string;
  role: "ADMIN" | "STAFF";
  status: "ACTIVE" | "INACTIVE";
  permissions: string[] | null;
  effective_permissions: string[];
  created_at: string;
}

export interface PermissionInfo {
  key: string;
  description: string;
}

export interface AuditLog {
  id: string;
  actor_id: string | null;
  actor_name: string | null;
  actor_role: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  summary: string | null;
  changes: unknown;
  ip_address: string | null;
  created_at: string;
}

export interface CustomerSummary {
  id: string;
  name: string | null;
  email: string | null;
  phone: string | null;
  status: string;
  is_verified: boolean;
  tags: string[];
  order_blocked: boolean;
  order_blocked_at: string | null;
  order_block_reason: string | null;
  total_orders: number;
  total_spent: string;
  last_order_at: string | null;
  created_at: string;
}

export interface CustomerNote {
  id: string;
  author_id: string | null;
  author_name: string | null;
  body: string;
  created_at: string;
}

export interface Address {
  id: string;
  full_name: string;
  phone: string;
  address_line_1: string;
  address_line_2: string | null;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  is_default: boolean;
}

export interface CustomerDetail extends CustomerSummary {
  first_order_at: string | null;
  is_returning: boolean;
  cancelled_orders: number;
  returned_orders: number;
  addresses: Address[];
  notes: CustomerNote[];
  currency: string;
}
