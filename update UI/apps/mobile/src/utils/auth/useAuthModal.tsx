/**
 * ⚠ ANYTHING PLATFORM — DO NOT REWRITE THIS FILE ⚠
 *
 * Shipped v2 <AuthModal /> — the modal that wraps the AuthWebView. It's
 * already mounted in app/_layout.tsx; DO NOT mount it again. The env-var
 * preflight (returns a "not configured" modal when EXPO_PUBLIC_BASE_URL or
 * EXPO_PUBLIC_PROXY_BASE_URL is missing) is intentional — removing it turns
 * env-var misconfig into a silent "nothing happens" bug. The named export of
 * useAuthModal at the top is also load-bearing (user code imports it from
 * this file, not just from ./store).
 */
'use client';

import React from 'react';
import { Modal, Text, View } from 'react-native';
import { AuthWebView } from './AuthWebView';
import { useAuthModal, useAuthStore } from './store';

export { useAuthModal } from './store';

/**
 * This component renders a modal for authentication purposes.
 * To show it programmatically, you should either use the `useRequireAuth` hook or the `useAuthModal` hook.
 *
 * @example
 * ```js
 * import { useAuthModal } from '@/utils/useAuthModal';
 * function MyComponent() {
 * const { open } = useAuthModal();
 * return <Button title="Login" onPress={() => open({ mode: 'signin' })} />;
 * }
 * ```
 *
 * @example
 * ```js
 * import { useRequireAuth } from '@/utils/auth';
 * function MyComponent() {
 *   // automatically opens the auth modal if the user is not authenticated
 *   useRequireAuth();
 *   return <Text>Protected Content</Text>;
 * }
 *
 */
export const AuthModal = () => {
  const { auth } = useAuthStore();
  const { isOpen, mode } = useAuthModal();

  const proxyURL = process.env.EXPO_PUBLIC_PROXY_BASE_URL;
  const baseURL = process.env.EXPO_PUBLIC_BASE_URL;
  if (!proxyURL || !baseURL) {
    const missing = [
      !proxyURL && 'EXPO_PUBLIC_PROXY_BASE_URL',
      !baseURL && 'EXPO_PUBLIC_BASE_URL',
    ]
      .filter(Boolean)
      .join(', ');
    console.error(
      `AuthModal: missing required env var(s): ${missing}. Auth cannot open.`
    );
    return (
      <Modal
        visible={isOpen && !auth}
        animationType="slide"
        presentationStyle="pageSheet"
      >
        <View className="flex-1 items-center justify-center bg-white p-[24px]">
          <Text className="mb-[8px] text-[18px] font-semibold">
            Auth is not configured
          </Text>
          <Text className="text-center text-[14px] text-gray-600">
            Missing environment variable{missing.includes(',') ? 's' : ''}:{' '}
            {missing}. Set {missing.includes(',') ? 'them' : 'it'} in your .env
            and restart the app.
          </Text>
        </View>
      </Modal>
    );
  }

  return (
    <Modal visible={isOpen && !auth} animationType="slide" presentationStyle='pageSheet'>
      <View
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: '100%',
          width: '100%',
          backgroundColor: '#fff',
          padding: 0,
        }}
      >
        <AuthWebView
          mode={mode}
          proxyURL={proxyURL}
          baseURL={baseURL}
        />
      </View>
    </Modal>
  );
};

export default useAuthModal;
