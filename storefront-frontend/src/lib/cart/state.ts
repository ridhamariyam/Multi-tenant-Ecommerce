import type { Cart } from '@/types/cart';

export interface CartActionState {
  status: 'idle' | 'success' | 'error';
  message: string | null;
}

export const initialCartState: CartActionState = { status: 'idle', message: null };

export interface CartMutation {
  cart: Cart;
  error: string | null;
}
