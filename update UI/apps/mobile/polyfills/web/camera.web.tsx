import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import { View, Text, StyleSheet, type ViewStyle } from 'react-native';

export enum CameraType {
  front = 'front',
  back = 'back',
}

export enum FlashMode {
  off = 'off',
  on = 'on',
  auto = 'auto',
  torch = 'torch',
}

export enum CameraMode {
  picture = 'picture',
  video = 'video',
}

interface CameraViewProps {
  style?: ViewStyle;
  facing?: 'front' | 'back';
  flash?: 'off' | 'on' | 'auto';
  mode?: 'picture' | 'video';
  zoom?: number;
  enableTorch?: boolean;
  onCameraReady?: () => void;
  onMountError?: (event: { message: string }) => void;
  children?: React.ReactNode;
}

interface CameraViewRef {
  takePictureAsync: (options?: {
    quality?: number;
    base64?: boolean;
  }) => Promise<{ uri: string; width: number; height: number; base64?: string }>;
  recordAsync: (options?: {
    maxDuration?: number;
  }) => Promise<{ uri: string }>;
  stopRecording: () => void;
}

export const CameraView = forwardRef<CameraViewRef, CameraViewProps>(
  function CameraView(
    { style, facing = 'back', onCameraReady, onMountError, children },
    ref
  ) {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const [hasCamera, setHasCamera] = useState(true);

    const startCamera = useCallback(async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: facing === 'front' ? 'user' : 'environment',
          },
        });
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        onCameraReady?.();
      } catch (err) {
        setHasCamera(false);
        onMountError?.({
          message:
            err instanceof Error ? err.message : 'Camera not available',
        });
      }
    }, [facing, onCameraReady, onMountError]);

    useEffect(() => {
      void startCamera();
      return () => {
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      };
    }, [startCamera]);

    useImperativeHandle(ref, () => ({
      takePictureAsync: async (options) => {
        const video = videoRef.current;
        if (!video || !streamRef.current) {
          throw new Error('Camera is not ready');
        }
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d')!;
        ctx.drawImage(video, 0, 0);
        const quality = options?.quality ?? 0.85;
        const dataUrl = canvas.toDataURL('image/jpeg', quality);
        const result: {
          uri: string;
          width: number;
          height: number;
          base64?: string;
        } = {
          uri: dataUrl,
          width: canvas.width,
          height: canvas.height,
        };
        if (options?.base64) {
          result.base64 = dataUrl.split(',')[1];
        }
        return result;
      },
      recordAsync: async () => {
        throw new Error('Video recording is not supported in web preview');
      },
      stopRecording: () => {},
    }));

    if (!hasCamera) {
      return (
        <View style={[styles.container, style]}>
          <View style={styles.placeholder}>
            <Text style={styles.placeholderText}>Camera</Text>
            <Text style={styles.placeholderSubtext}>
              Not available in this browser
            </Text>
          </View>
          {children}
        </View>
      );
    }

    return (
      <View style={[styles.container, style]}>
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
        />
        {children}
      </View>
    );
  }
);

const grantedPermission = {
  status: 'granted' as const,
  granted: true,
  canAskAgain: true,
  expires: 'never' as const,
};

const deniedPermission = {
  status: 'denied' as const,
  granted: false,
  canAskAgain: true,
  expires: 'never' as const,
};

export function useCameraPermissions(): [
  { status: string; granted: boolean; canAskAgain: boolean } | null,
  () => Promise<{ status: string; granted: boolean; canAskAgain: boolean }>,
] {
  const [permission, setPermission] = useState<{
    status: string;
    granted: boolean;
    canAskAgain: boolean;
  } | null>(null);

  const requestPermission = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      stream.getTracks().forEach((t) => t.stop());
      setPermission(grantedPermission);
      return grantedPermission;
    } catch {
      setPermission(deniedPermission);
      return deniedPermission;
    }
  }, []);

  return [permission, requestPermission];
}

export async function requestCameraPermissionsAsync() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    stream.getTracks().forEach((t) => t.stop());
    return grantedPermission;
  } catch {
    return deniedPermission;
  }
}

export async function getCameraPermissionsAsync() {
  try {
    const result = await navigator.permissions.query({
      name: 'camera' as PermissionName,
    });
    return result.state === 'granted' ? grantedPermission : deniedPermission;
  } catch {
    return deniedPermission;
  }
}

const styles = StyleSheet.create({
  container: {
    overflow: 'hidden',
    backgroundColor: '#000',
  },
  placeholder: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#1a1a1a',
  },
  placeholderText: {
    color: '#999',
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 4,
  },
  placeholderSubtext: {
    color: '#666',
    fontSize: 13,
  },
});
