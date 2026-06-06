import type { ImageProps } from 'expo-image';
import * as ExpoImage from 'expo-image';
import { Buffer } from 'buffer';
import React, { forwardRef, useState, useEffect, useCallback, useRef } from 'react';
import { Platform } from 'react-native';

function buildGridPlaceholder(w: number, h: number): string {
  const size = Math.max(w, h);
  const svg = `
    <svg width="${size}" height="${size}" viewBox="0 0 895 895" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="895" height="895" rx="19" fill="#E9E7E7"/>
      <g stroke="#C0C0C0" stroke-width="1.00975">
        <line x1="447.505" y1="-23"  x2="447.505" y2="901"/>
        <line x1="889.335" y1="447.505" x2="5.66443" y2="447.505"/>
        <line x1="889.335" y1="278.068" x2="5.66443" y2="278.068"/>
        <line x1="889.335" y1="57.1505" x2="5.66443" y2="57.1504"/>
        <line x1="61.8051" y1="883.671" x2="61.8051" y2="0.000061"/>
        <line x1="282.495" y1="907" x2="282.495" y2="-30"/>
        <line x1="611.495" y1="907" x2="611.495" y2="-30"/>
        <line x1="832.185" y1="883.671" x2="832.185" y2="0.000061"/>
        <line x1="889.335" y1="827.53"  x2="5.66443"  y2="827.53"/>
        <line x1="889.335" y1="606.613" x2="5.66443" y2="606.612"/>
        <line x1="4.3568" y1="4.6428"  x2="889.357" y2="888.643"/>
        <line x1="-0.3568" y1="894.643" x2="894.643" y2="0.642772"/>
        <circle cx="447.5"  cy="441.5" r="163.995"/>
        <circle cx="447.911" cy="447.911" r="237.407"/>
        <circle cx="448"    cy="442"    r="384.495"/>
      </g>
    </svg>`;
  const b64 = Buffer.from(svg).toString('base64');
  return `data:image/svg+xml;base64,${b64}`;
}

type Src = ImageProps['source'];
function computeSourceKey(src: Src): string {
  if (Array.isArray(src)) return src.map(computeSourceKey).join('|');
  if (typeof src === 'number') return String(src); // require('./img.png')
  if (typeof src === 'string') return src; // remote on web
  if (src && typeof src === 'object' && 'uri' in src) return src.uri ?? '';
  return '';
}

const WrappedImage = forwardRef<ExpoImage.Image, ImageProps>(function WrappedImage(props, ref) {
  const [fallbackSource, setFallbackSource] = useState<Src | null>(null);
  const source = props.source;
  const onError = props.onError;
  const style = props.style;
  const currentKey = computeSourceKey(props.source);
  const prevKeyRef = useRef(currentKey);

  useEffect(() => {
    if (prevKeyRef.current !== currentKey) {
      // parent really pointed to a different image: clear any old fallback
      setFallbackSource(null);
      prevKeyRef.current = currentKey;
    }
  }, [currentKey]);
  const handleError: ImageProps['onError'] = useCallback(
    (e: ExpoImage.ImageErrorEventData) => {
      onError?.(e);

      /* already swapped or dealing with a multi‑src array */
      if (fallbackSource || Array.isArray(source)) return;

      // prevent it from recursing
      if (
        source &&
        typeof source === 'object' &&
        'uri' in source &&
        source?.uri?.startsWith('data:')
      ) {
        return;
      }
      /* try to infer a sensible grid size */
      const finalStyle = Array.isArray(style) ? Object.assign({}, ...style) : style;
      const width = finalStyle?.width ?? 128;
      const height = finalStyle?.height ?? 128;

      if (Platform.OS === 'web') {
        setFallbackSource({ uri: buildGridPlaceholder(width, height) });
      } else {
        setFallbackSource(require('../../src/__create/placeholder.svg'));
      }
    },
    [source, fallbackSource, onError, style]
  );

  return (
    <ExpoImage.Image {...props} source={fallbackSource ?? source} ref={ref} onError={handleError} />
  );
});

/* expose static helpers so nothing breaks */
Object.assign(WrappedImage, ExpoImage);

/* re‑export everything that expo-image provides */
export * from 'expo-image';
export const Image = WrappedImage;
export default Image;
