import type { ReactNativeAsset } from '@uploadcare/upload-client';
import * as SecureStore from 'expo-secure-store';
import * as React from 'react';

interface UploadInputReactNative {
	reactNativeAsset: ReactNativeAsset & { file?: File };
}

interface UploadInputUrl {
	url: string;
}

interface UploadInputBase64 {
	base64: string;
}

interface UploadInputBuffer {
	buffer: Buffer;
}

type UploadInput = UploadInputReactNative | UploadInputUrl | UploadInputBase64 | UploadInputBuffer;

interface UploadResult {
	url?: string;
	mimeType?: string | null;
	error?: string;
}

interface UploadHookResult {
	loading: boolean;
}

// Both paths upload via the proxy's /_create/api/upload/ (respects S3 flag).
// Web: globalThis.fetch with full proxy URL + no custom headers (avoids CORS
// preflight — the proxy adds project-group-id from the hostname server-side).
// Native: FileSystem.uploadAsync to same URL with manual auth headers.
function useUpload(): [(input: UploadInput) => Promise<UploadResult>, UploadHookResult] {
  const [loading, setLoading] = React.useState(false);
  const upload = React.useCallback(async (input: UploadInput): Promise<UploadResult> => {
    try {
      setLoading(true);
      let response: Response | undefined;
      if ('reactNativeAsset' in input && input.reactNativeAsset) {
        const asset = input.reactNativeAsset;

        if (asset.file) {
          const proxyBaseUrl = process.env.EXPO_PUBLIC_PROXY_BASE_URL;
          const formData = new FormData();
          formData.append('file', asset.file);
          response = await globalThis.fetch(`${proxyBaseUrl}/_create/api/upload/`, {
            method: 'POST',
            body: formData,
          });
        } else {
          const FileSystem = require('expo-file-system/legacy');
          const proxyBaseUrl = process.env.EXPO_PUBLIC_PROXY_BASE_URL;
          const projectGroupId = process.env.EXPO_PUBLIC_PROJECT_GROUP_ID;
          const host = process.env.EXPO_PUBLIC_HOST;

          const headers: Record<string, string> = {
            'x-createxyz-project-group-id': projectGroupId || '',
            'host': host || '',
            'x-forwarded-host': host || '',
            'x-createxyz-host': host || '',
          };

          try {
            const authStr = await SecureStore.getItemAsync(`${projectGroupId}-jwt`);
            if (authStr) {
              const auth = JSON.parse(authStr);
              if (auth?.jwt) headers['authorization'] = `Bearer ${auth.jwt}`;
            }
          } catch {}

          const uploadResult = await FileSystem.uploadAsync(
            `${proxyBaseUrl}/_create/api/upload/`,
            asset.uri,
            {
              uploadType: FileSystem.FileSystemUploadType.MULTIPART,
              fieldName: 'file',
              headers,
            },
          );

          if (uploadResult.status < 200 || uploadResult.status >= 300) {
            throw new Error(`Upload failed (${uploadResult.status}): ${uploadResult.body}`);
          }

          let data: { url?: string; mimeType?: string | null };
          try {
            data = JSON.parse(uploadResult.body);
          } catch {
            throw new Error('Upload failed: invalid response from upload service');
          }

          return { url: data.url, mimeType: data.mimeType || null };
        }
      } else if ('url' in input) {
        response = await fetch('/_create/api/upload/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ url: input.url }),
        });
      } else if ('base64' in input) {
        response = await fetch('/_create/api/upload/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ base64: input.base64 }),
        });
      } else if ('buffer' in input) {
        response = await fetch('/_create/api/upload/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/octet-stream',
          },
          body: input.buffer as unknown as BodyInit,
        });
      }
      if (!response || !response.ok) {
        if (response?.status === 413) {
          throw new Error('Upload failed: File too large.');
        }
        const body = await response?.text().catch(() => '');
        throw new Error(`Upload failed (${response?.status ?? 'no response'}): ${body}`);
      }
      const data = await response.json();
      return { url: data.url, mimeType: data.mimeType || null };
    } catch (uploadError) {
      if (uploadError instanceof Error) {
        return { error: uploadError.message };
      }
      if (typeof uploadError === 'string') {
        return { error: uploadError };
      }
      return { error: 'Upload failed' };
    } finally {
      setLoading(false);
    }
  }, []);

  return [upload, { loading }];
}

export { useUpload };
export default useUpload;
