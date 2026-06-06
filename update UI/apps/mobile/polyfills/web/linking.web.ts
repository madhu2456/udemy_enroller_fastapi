export async function openURL(url: string): Promise<true> {
  window.open(url, '_blank');
  return true;
}

export async function canOpenURL(_url: string): Promise<boolean> {
  return true;
}

export function getInitialURL(): string {
  return typeof window !== 'undefined' ? window.location.href : '';
}

export function createURL(
  path: string,
  namedParameters?: { queryParams?: Record<string, string> }
): string {
  const base = typeof window !== 'undefined' ? window.location.origin : '';
  const url = new URL(path.startsWith('/') ? path : `/${path}`, base);
  if (namedParameters?.queryParams) {
    for (const [key, value] of Object.entries(namedParameters.queryParams)) {
      url.searchParams.set(key, value);
    }
  }
  return url.toString();
}

export function parse(url: string) {
  const parsed = new URL(url);
  const queryParams: Record<string, string> = {};
  parsed.searchParams.forEach((value, key) => {
    queryParams[key] = value;
  });
  return {
    path: parsed.pathname,
    queryParams,
    hostname: parsed.hostname,
    scheme: parsed.protocol.replace(':', ''),
  };
}

export function addEventListener(
  _type: string,
  handler: (event: { url: string }) => void
) {
  const listener = () => handler({ url: window.location.href });
  window.addEventListener('popstate', listener);
  return { remove: () => window.removeEventListener('popstate', listener) };
}

export function useURL(): string | null {
  return typeof window !== 'undefined' ? window.location.href : null;
}
