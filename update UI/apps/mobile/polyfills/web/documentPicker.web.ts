interface DocumentPickerAsset {
  name: string;
  size: number | null;
  uri: string;
  mimeType: string | null;
}

interface DocumentPickerResult {
  canceled: boolean;
  assets: DocumentPickerAsset[];
  output: null;
}

interface DocumentPickerOptions {
  type?: string | string[];
  copyToCacheDirectory?: boolean;
  multiple?: boolean;
}

export async function getDocumentAsync(
  options?: DocumentPickerOptions
): Promise<DocumentPickerResult> {
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = options?.multiple ?? false;

    if (options?.type) {
      const types = Array.isArray(options.type)
        ? options.type
        : [options.type];
      const filtered = types.filter((t) => t !== '*/*');
      if (filtered.length > 0) {
        input.accept = filtered.join(',');
      }
    }

    input.style.display = 'none';
    document.body.appendChild(input);

    let resolved = false;
    const cleanup = () => {
      if (!resolved) {
        resolved = true;
        document.body.removeChild(input);
      }
    };

    input.addEventListener('change', () => {
      const files = input.files;
      if (!files || files.length === 0) {
        cleanup();
        resolve({ canceled: true, assets: [], output: null });
        return;
      }

      const promises = Array.from(files).map(
        (file) =>
          new Promise<DocumentPickerAsset>((resolveAsset) => {
            const reader = new FileReader();
            reader.onload = () => {
              resolveAsset({
                name: file.name,
                size: file.size,
                uri: reader.result as string,
                mimeType: file.type || null,
              });
            };
            reader.readAsDataURL(file);
          })
      );

      void Promise.all(promises).then((assets) => {
        cleanup();
        resolve({ canceled: false, assets, output: null });
      });
    });

    window.addEventListener(
      'focus',
      () => {
        setTimeout(() => {
          if (!resolved) {
            cleanup();
            resolve({ canceled: true, assets: [], output: null });
          }
        }, 300);
      },
      { once: true }
    );

    input.click();
  });
}
