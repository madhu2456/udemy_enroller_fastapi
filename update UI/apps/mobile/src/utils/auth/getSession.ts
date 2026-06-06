/**
 * ⚠ ANYTHING PLATFORM — DO NOT REWRITE THIS FILE ⚠
 *
 * Shipped v2 auth helpers. `authFetch` auto-adds Authorization: Bearer <jwt>
 * when a session exists — use it instead of bare fetch() for calls to the
 * web app's API routes. The web server's better-auth bearer() plugin
 * validates these headers. DO NOT reimplement these helpers in user code.
 */
'use client';

import { useAuthStore } from './store';

/**
 * Read the current session (jwt + user) synchronously from the auth store.
 * Returns null if the user is not authenticated.
 */
export const getSession = () => useAuthStore.getState().auth;

/**
 * Read the current session's JWT for use in an Authorization header.
 * Returns null if the user is not authenticated.
 */
export const getJwt = () => useAuthStore.getState().auth?.jwt ?? null;

/**
 * Drop-in replacement for fetch() that automatically adds the
 * `Authorization: Bearer <jwt>` header when the user is signed in. Use this
 * for calls from the mobile app to the web app's API routes — the web server
 * uses better-auth's `bearer()` plugin to authenticate these requests.
 *
 * Existing Authorization headers on the caller's `init.headers` are preserved.
 */
export const authFetch: typeof fetch = (input, init) => {
  const jwt = getJwt();
  const headers = new Headers(init?.headers);
  if (jwt && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${jwt}`);
  }
  return fetch(input, { ...init, headers });
};
