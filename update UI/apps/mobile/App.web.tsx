import { usePathname, useRouter } from 'expo-router';
import { App } from 'expo-router/build/qualified-entry';
import React, { memo, useEffect } from 'react';
import './src/__create/polyfills';

import { ErrorBoundary } from './src/__create/ErrorBoundary';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Toaster } from 'sonner-native';
import { AlertModal } from './polyfills/web/alerts.web';
import './global.css';

const RUNTIME_ERROR_PATTERNS = [
  /fetch failed/i,
  /networks*(error|request)/i,
  /failed to fetch/i,
  /load failed/i,
  /ECONNREFUSED/i,
  /ECONNRESET/i,
  /ETIMEDOUT/i,
  /ENOTFOUND/i,
  /ERR_CONNECTION/i,
  /aborted/i,
  /timeout/i,
  /socket hang up/i,
  /503\b/,
  /502\b/,
  /504\b/,
  /getaddrinfo/i,
];

function isRuntimeError(msg: string) {
  return RUNTIME_ERROR_PATTERNS.some((p) => p.test(msg));
}

function postErrorToParent(message: string, name: string, stack: string) {
  try {
    if (window.parent !== window) {
      window.parent.postMessage(
        {
          type: 'sandbox:error:detected',
          error: { message, name, stack },
        },
        '*'
      );
    }
  } catch {}
}

const GlobalErrorReporter = () => {
  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const errorHandler = (event: ErrorEvent) => {
      if (typeof event.preventDefault === 'function') event.preventDefault();
      console.error(event.error);

      const error = event.error;
      const message = error?.message || event.message || 'Unknown error';
      if (!isRuntimeError(message)) {
        postErrorToParent(message, error?.name || 'Error', error?.stack || '');
      }
    };
    const unhandledRejectionHandler = (event: PromiseRejectionEvent) => {
      if (typeof event.preventDefault === 'function') event.preventDefault();
      const reason = event.reason;
      console.error('Unhandled promise rejection:', reason);

      const message = reason?.message || String(reason || '');
      if (isRuntimeError(message)) return;
      const isCodeError =
        reason instanceof TypeError ||
        reason instanceof ReferenceError ||
        reason instanceof SyntaxError ||
        reason?.code === 'MODULE_RESOLVE_FAILED';
      if (!isCodeError) return;
      postErrorToParent(message, reason?.name || 'Error', reason?.stack || '');
    };
    window.addEventListener('error', errorHandler);
    window.addEventListener('unhandledrejection', unhandledRejectionHandler);
    return () => {
      window.removeEventListener('error', errorHandler);
      window.removeEventListener(
        'unhandledrejection',
        unhandledRejectionHandler
      );
    };
  }, []);
  return null;
};

const Wrapper = memo(() => {
  return (
    <ErrorBoundary>
      <SafeAreaProvider
        initialMetrics={{
          insets: { top: 64, bottom: 34, left: 0, right: 0 },
          frame: {
            x: 0,
            y: 0,
            width: typeof window === 'undefined' ? 390 : window.innerWidth,
            height: typeof window === 'undefined' ? 844 : window.innerHeight,
          },
        }}
      >
        <App />
        <GlobalErrorReporter />
        <Toaster />
      </SafeAreaProvider>
    </ErrorBoundary>
  );
});
const healthyResponse = {
  type: 'sandbox:mobile:healthcheck:response',
  healthy: true,
};

const useHandshakeParent = () => {
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data.type === 'sandbox:mobile:healthcheck') {
        window.parent.postMessage(healthyResponse, '*');
      }
    };
    window.addEventListener('message', handleMessage);
    // Immediately respond to the parent window with a healthy response in
    // case we missed the healthcheck message
    window.parent.postMessage(healthyResponse, '*');
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, []);
};

const CreateApp = () => {
  const router = useRouter();
  const pathname = usePathname();
  useHandshakeParent();

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (
        event.data.type === 'sandbox:navigation' &&
        event.data.pathname !== pathname
      ) {
        router.push(event.data.pathname);
      }
    };

    window.addEventListener('message', handleMessage);
    window.parent.postMessage({ type: 'sandbox:mobile:ready' }, '*');
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, [router, pathname]);

  useEffect(() => {
    window.parent.postMessage(
      {
        type: 'sandbox:mobile:navigation',
        pathname,
      },
      '*'
    );
  }, [pathname]);

  return (
    <>
      <Wrapper />
      <AlertModal />
    </>
  );
};

export default CreateApp;
