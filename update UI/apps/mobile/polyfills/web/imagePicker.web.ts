export enum MediaTypeOptions {
  All = 'All',
  Images = 'Images',
  Videos = 'Videos',
}

export enum UIImagePickerPresentationStyle {
  FULL_SCREEN = 0,
  PAGE_SHEET = 1,
  FORM_SHEET = 2,
  CURRENT_CONTEXT = 3,
  OVERFUL_SCREEN = 4,
  POPOVER = 5,
  AUTOMATIC = -2,
}

interface ImagePickerAsset {
  uri: string;
  width: number;
  height: number;
  type: 'image' | 'video' | undefined;
  fileName: string | null;
  fileSize: number | undefined;
  mimeType: string | undefined;
}

interface ImagePickerResult {
  canceled: boolean;
  assets: ImagePickerAsset[];
}

interface ImagePickerOptions {
  mediaTypes?: MediaTypeOptions;
  allowsEditing?: boolean;
  quality?: number;
  allowsMultipleSelection?: boolean;
  base64?: boolean;
}

function getAcceptString(mediaTypes?: MediaTypeOptions): string {
  switch (mediaTypes) {
    case MediaTypeOptions.Images:
      return 'image/*';
    case MediaTypeOptions.Videos:
      return 'video/*';
    default:
      return 'image/*,video/*';
  }
}

function pickFileViaInput(
  accept: string,
  capture: boolean,
  multiple: boolean
): Promise<ImagePickerResult> {
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = accept;
    input.multiple = multiple;
    if (capture) input.setAttribute('capture', 'environment');
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
        resolve({ canceled: true, assets: [] });
        return;
      }
      const promises = Array.from(files).map(
        (file) =>
          new Promise<ImagePickerAsset>((resolveAsset) => {
            const reader = new FileReader();
            reader.onload = () => {
              const uri = reader.result as string;
              const img = new Image();
              img.onload = () => {
                resolveAsset({
                  uri,
                  width: img.naturalWidth,
                  height: img.naturalHeight,
                  type: file.type.startsWith('video') ? 'video' : 'image',
                  fileName: file.name,
                  fileSize: file.size,
                  mimeType: file.type || undefined,
                });
              };
              img.onerror = () => {
                resolveAsset({
                  uri,
                  width: 0,
                  height: 0,
                  type: file.type.startsWith('video') ? 'video' : 'image',
                  fileName: file.name,
                  fileSize: file.size,
                  mimeType: file.type || undefined,
                });
              };
              img.src = uri;
            };
            reader.readAsDataURL(file);
          })
      );
      void Promise.all(promises).then((assets) => {
        cleanup();
        resolve({ canceled: false, assets });
      });
    });

    // Handle cancel (user closes the file dialog without selecting)
    window.addEventListener(
      'focus',
      () => {
        setTimeout(() => {
          if (!resolved) {
            cleanup();
            resolve({ canceled: true, assets: [] });
          }
        }, 300);
      },
      { once: true }
    );

    input.click();
  });
}

export async function launchImageLibraryAsync(
  options?: ImagePickerOptions
): Promise<ImagePickerResult> {
  return pickFileViaInput(
    getAcceptString(options?.mediaTypes),
    false,
    options?.allowsMultipleSelection ?? false
  );
}

export async function launchCameraAsync(
  options?: ImagePickerOptions
): Promise<ImagePickerResult> {
  return pickFileViaInput(
    getAcceptString(options?.mediaTypes),
    true,
    options?.allowsMultipleSelection ?? false
  );
}

const grantedPermission = {
  status: 'granted' as const,
  granted: true,
  canAskAgain: true,
  expires: 'never' as const,
};

export async function requestMediaLibraryPermissionsAsync() {
  return grantedPermission;
}

export async function getMediaLibraryPermissionsAsync() {
  return grantedPermission;
}

export async function requestCameraPermissionsAsync() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    stream.getTracks().forEach((t) => t.stop());
    return grantedPermission;
  } catch {
    return {
      status: 'denied' as const,
      granted: false,
      canAskAgain: true,
      expires: 'never' as const,
    };
  }
}

export async function getCameraPermissionsAsync() {
  try {
    const result = await navigator.permissions.query({
      name: 'camera' as PermissionName,
    });
    const granted = result.state === 'granted';
    return {
      status: granted ? ('granted' as const) : ('denied' as const),
      granted,
      canAskAgain: result.state !== 'denied',
      expires: 'never' as const,
    };
  } catch {
    return grantedPermission;
  }
}
