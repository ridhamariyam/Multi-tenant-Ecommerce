import { apiRequest } from '@/lib/api/client';
import type { Address, AddressCreate, AddressUpdate } from '@/types/addresses';

export const addressApi = {
  list(token: string): Promise<Address[]> {
    return apiRequest<Address[]>('/addresses', { token, cache: 'no-store' });
  },

  get(token: string, addressId: string): Promise<Address> {
    return apiRequest<Address>(`/addresses/${addressId}`, { token, cache: 'no-store' });
  },

  create(token: string, data: AddressCreate): Promise<Address> {
    return apiRequest<Address>('/addresses', {
      method: 'POST',
      body: data,
      token,
      cache: 'no-store',
    });
  },

  /** Must carry at least one field, or the backend rejects the patch. */
  update(token: string, addressId: string, data: AddressUpdate): Promise<Address> {
    return apiRequest<Address>(`/addresses/${addressId}`, {
      method: 'PATCH',
      body: data,
      token,
      cache: 'no-store',
    });
  },

  remove(token: string, addressId: string): Promise<null> {
    return apiRequest<null>(`/addresses/${addressId}`, {
      method: 'DELETE',
      token,
      cache: 'no-store',
    });
  },
};
