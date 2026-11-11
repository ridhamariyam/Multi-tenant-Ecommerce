/**
 * Shared shape for the auth forms.
 *
 * Kept out of actions.ts because a 'use server' module may only export
 * async functions -- a plain object there fails the build.
 */
export interface AuthFormState {
  error: string | null;
  fieldErrors?: Record<string, string>;
}
