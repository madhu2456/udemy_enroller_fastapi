export async function getStringAsync(): Promise<string> {
  try {
    return await navigator.clipboard.readText();
  } catch {
    return '';
  }
}

export async function setStringAsync(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export async function hasStringAsync(): Promise<boolean> {
  try {
    const text = await navigator.clipboard.readText();
    return text.length > 0;
  } catch {
    return false;
  }
}

export async function getImageAsync() {
  return null;
}

export async function setImageAsync() {}

export async function hasImageAsync(): Promise<boolean> {
  return false;
}

export function addClipboardListener(
  _listener: (event: { contentTypes: string[] }) => void
) {
  return { remove: () => {} };
}

export function removeClipboardListener(subscription: { remove: () => void }) {
  subscription.remove();
}

export function isPlatformSupported(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.clipboard;
}
