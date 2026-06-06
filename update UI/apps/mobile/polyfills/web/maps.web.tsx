import WebMapView, * as WebMaps from '@teovilla/react-native-web-maps';
import React from 'react';

export const PROVIDER_GOOGLE = 'google';
export const PROVIDER_DEFAULT = undefined;

const GOOGLE_MAPS_API_KEY = process.env.EXPO_PUBLIC_GOOGLE_MAPS_API_KEY;

const MapView = React.forwardRef((props: Record<string, unknown>, ref: React.Ref<unknown>) => {
  return (
    // @ts-expect-error — library default export is not typed as a valid JSX component
    <WebMapView
      ref={ref}
      provider={PROVIDER_GOOGLE}
      googleMapsApiKey={GOOGLE_MAPS_API_KEY}
      {...props}
      options={{
        disableDefaultUI: true,
        zoomControl: false,
        streetViewControl: false,
        mapTypeControl: false,
        fullscreenControl: false,
        rotateControl: false,
        scaleControl: false,
        keyboardShortcuts: false,
        ...(props.options as Record<string, unknown>),
      }}
    />
  );
});

Object.assign(MapView, {
  ...WebMaps,
  PROVIDER_GOOGLE,
  PROVIDER_DEFAULT,
});

// The library namespace export doesn't declare these members but they exist at runtime
const Maps = WebMaps as Record<string, unknown>;
export const Marker = Maps.Marker;
export const Callout = Maps.Callout;
export const Polyline = Maps.Polyline;
export const Polygon = Maps.Polygon;
export const Circle = Maps.Circle;
export const Overlay = Maps.Overlay;
export const Heatmap = Maps.Heatmap;
export const UrlTile = Maps.UrlTile;
export const WMSTile = Maps.WMSTile;
export const LocalTile = Maps.LocalTile;

export default MapView;
