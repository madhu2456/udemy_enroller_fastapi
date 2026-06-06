export enum WebBrowserResultType {
  CANCEL = 'cancel',
  DISMISS = 'dismiss',
  OPENED = 'opened',
  LOCKED = 'locked',
}

interface WebBrowserResult {
  type: WebBrowserResultType;
}

let _openWindow: Window | null = null;

export async function openBrowserAsync(
  url: string,
  _options?: {
    toolbarColor?: string;
    controlsColor?: string;
    secondaryToolbarColor?: string;
    enableBarCollapsing?: boolean;
    showTitle?: boolean;
    enableDefaultShareMenuItem?: boolean;
    windowName?: string;
    windowFeatures?: string;
  }
): Promise<WebBrowserResult> {
  _openWindow = window.open(url, '_blank');
  return { type: WebBrowserResultType.OPENED };
}

export async function openAuthSessionAsync(
  url: string,
  _redirectUrl?: string,
  _options?: { showInRecents?: boolean }
): Promise<WebBrowserResult & { url?: string }> {
  const authWindow = window.open(url, '_blank');
  if (!authWindow) {
    return { type: WebBrowserResultType.CANCEL };
  }
  return { type: WebBrowserResultType.OPENED };
}

export function dismissBrowser(): void {
  if (_openWindow && !_openWindow.closed) {
    _openWindow.close();
    _openWindow = null;
  }
}

export async function warmUpAsync(): Promise<void> {}
export async function coolDownAsync(): Promise<void> {}
export async function mayInitWithUrlAsync(
  _url: string
): Promise<{ servicePackage: string | null }> {
  return { servicePackage: null };
}
