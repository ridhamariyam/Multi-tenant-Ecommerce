export type UserRole = 'CUSTOMER' | 'STAFF' | 'ADMIN';

export type UserStatus = 'ACTIVE' | 'INACTIVE' | 'DELETED';

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  /** Access token lifetime in seconds. */
  expires_in: number;
}

export interface UserProfile {
  id: string;
  tenant_id: string;
  phone: string | null;
  email: string | null;
  name: string | null;
  role: UserRole;
  status: UserStatus;
  is_verified: boolean;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
}
