/**
 * ⚠ ANYTHING PLATFORM — DO NOT REWRITE THIS FILE ⚠
 *
 * Shipped v2 mobile auth hook. `useAuth()` is the public surface for
 * user apps — `{ signIn, signUp, signOut, auth, isAuthenticated, isReady }`.
 * These names are documented in the v2 auth prompt; user code imports them
 * directly. DO NOT rename them, DO NOT remove `initiate()` (it loads the
 * persisted session from SecureStore), and DO NOT add side effects that run
 * before isReady flips true.
 */
import * as SecureStore from 'expo-secure-store';
import { useCallback, useEffect } from 'react';
import { authKey, type Auth, secureStoreOptions, useAuthModal, useAuthStore } from './store';

interface UseAuthReturn {
	isReady: boolean;
	isAuthenticated: boolean | null;
	signIn: () => void;
	signOut: () => void;
	signUp: () => void;
	auth: Auth | null;
	setAuth: (auth: Auth | null) => void;
	initiate: () => void;
}

/**
 * This hook provides authentication functionality.
 * It may be easier to use the `useAuthModal` or `useRequireAuth` hooks
 * instead as those will also handle showing authentication to the user
 * directly.
 */
export const useAuth = (): UseAuthReturn => {
  const { isReady, auth, setAuth } = useAuthStore();
  const { isOpen: _isOpen, close, open } = useAuthModal();

  const initiate = useCallback(() => {
    // The auth state machine must always reach a terminal state. SecureStore
    // can throw or hang in TestFlight release builds (Keychain access denied,
    // missing keychain-access-groups entitlement after EAS migration, locked
    // device first-unlock state, or iOS 26 TurboModule rethrow). Without a
    // catch the unhandled rejection leaves isReady=false forever and the
    // RootLayout renders null — the user sees a blank screen indefinitely.
    Promise.race<string | null>([
      SecureStore.getItemAsync(authKey, secureStoreOptions),
      new Promise<null>((resolve) => setTimeout(() => resolve(null), 3000)),
    ])
      .then((authString) => {
        useAuthStore.setState({
          auth: authString ? (JSON.parse(authString) as Auth) : null,
          isReady: true,
        });
      })
      .catch(() => {
        useAuthStore.setState({ auth: null, isReady: true });
      });
  }, []);

  useEffect(() => {}, []);

  const signIn = useCallback(() => {
    open({ mode: 'signin' });
  }, [open]);
  const signUp = useCallback(() => {
    open({ mode: 'signup' });
  }, [open]);

  const signOut = useCallback(() => {
    setAuth(null);
    close();
  }, [close, setAuth]);

  return {
    isReady,
    isAuthenticated: isReady ? !!auth : null,
    signIn,
    signOut,
    signUp,
    auth,
    setAuth,
    initiate,
  };
};

interface UseRequireAuthOptions {
	mode?: 'signup' | 'signin';
}

export const useRequireAuth = (options?: UseRequireAuthOptions): UseAuthReturn => {
  const authReturn = useAuth();
  const { open } = useAuthModal();

  useEffect(() => {
    if (!authReturn.isAuthenticated && authReturn.isReady) {
      open({ mode: options?.mode });
    }
  }, [authReturn.isAuthenticated, open, options?.mode, authReturn.isReady]);

  return authReturn;
};

export default useAuth;
