import type { LocationGeocodedAddress } from 'expo-location';

type Coords = { latitude: number; longitude: number };

export enum LocationAccuracy {
  Lowest = 1,
  Low = 2,
  Balanced = 3,
  High = 4,
  Highest = 5,
  BestForNavigation = 6,
}

export enum PermissionStatus {
  DENIED = 'denied',
  GRANTED = 'granted',
  UNDETERMINED = 'undetermined',
}

interface LocationObject {
  coords: {
    latitude: number;
    longitude: number;
    altitude: number | null;
    accuracy: number | null;
    altitudeAccuracy: number | null;
    heading: number | null;
    speed: number | null;
  };
  timestamp: number;
}

interface LocationOptions {
  accuracy?: LocationAccuracy;
  distanceInterval?: number;
  timeInterval?: number;
}

interface LocationSubscription {
  remove: () => void;
}

function toLocationObject(position: GeolocationPosition): LocationObject {
  return {
    coords: {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      altitude: position.coords.altitude,
      accuracy: position.coords.accuracy,
      altitudeAccuracy: position.coords.altitudeAccuracy,
      heading: position.coords.heading,
      speed: position.coords.speed,
    },
    timestamp: position.timestamp,
  };
}

function toPermissionResponse(state: PermissionState) {
  const granted = state === 'granted';
  return {
    status: granted
      ? PermissionStatus.GRANTED
      : state === 'prompt'
        ? PermissionStatus.UNDETERMINED
        : PermissionStatus.DENIED,
    granted,
    canAskAgain: state !== 'denied',
    expires: 'never' as const,
  };
}

export async function getCurrentPositionAsync(
  options?: LocationOptions
): Promise<LocationObject> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Geolocation is not available in this browser'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => resolve(toLocationObject(position)),
      (error) => reject(new Error(error.message)),
      {
        enableHighAccuracy:
          options?.accuracy != null && options.accuracy >= LocationAccuracy.High,
        timeout: 10000,
      }
    );
  });
}

export async function watchPositionAsync(
  options: LocationOptions | null,
  callback: (location: LocationObject) => void
): Promise<LocationSubscription> {
  if (!navigator.geolocation) {
    throw new Error('Geolocation is not available in this browser');
  }
  const watchId = navigator.geolocation.watchPosition(
    (position) => callback(toLocationObject(position)),
    () => {},
    {
      enableHighAccuracy:
        options?.accuracy != null && options.accuracy >= LocationAccuracy.High,
    }
  );
  return { remove: () => navigator.geolocation.clearWatch(watchId) };
}

export async function getLastKnownPositionAsync(): Promise<LocationObject | null> {
  try {
    return await getCurrentPositionAsync();
  } catch {
    return null;
  }
}

export async function requestForegroundPermissionsAsync() {
  if (!navigator.geolocation) {
    return toPermissionResponse('denied');
  }
  return new Promise<ReturnType<typeof toPermissionResponse>>((resolve) => {
    navigator.geolocation.getCurrentPosition(
      () => resolve(toPermissionResponse('granted')),
      () => resolve(toPermissionResponse('denied')),
      { timeout: 10000 }
    );
  });
}

export async function requestBackgroundPermissionsAsync() {
  return toPermissionResponse('denied');
}

export async function getForegroundPermissionsAsync() {
  try {
    const result = await navigator.permissions.query({
      name: 'geolocation',
    });
    return toPermissionResponse(result.state);
  } catch {
    return toPermissionResponse('prompt');
  }
}

export async function getBackgroundPermissionsAsync() {
  return toPermissionResponse('denied');
}

export async function geocodeAsync(
  _address: string
): Promise<{ latitude: number; longitude: number; accuracy: number }[]> {
  return [];
}

export async function reverseGeocodeAsync({
  latitude,
  longitude,
}: Coords): Promise<LocationGeocodedAddress[]> {
  return [
    {
      city: 'Sample City',
      street: 'Main Street',
      district: 'Downtown',
      region: 'Sample State',
      postalCode: '12345',
      country: 'Sample Country',
      isoCountryCode: 'SC',
      name: `Location at ${latitude.toFixed(4)}, ${longitude.toFixed(4)}`,
      streetNumber: '123',
      subregion: null,
      timezone: null,
      formattedAddress: null,
    },
  ];
}

export async function hasServicesEnabledAsync(): Promise<boolean> {
  return typeof navigator !== 'undefined' && !!navigator.geolocation;
}

export async function isBackgroundLocationAvailableAsync(): Promise<boolean> {
  return false;
}

const NativeLocation = require('expo-location/build') as Record<string, unknown>;

module.exports = {
  ...NativeLocation,
  LocationAccuracy,
  PermissionStatus,
  getCurrentPositionAsync,
  watchPositionAsync,
  getLastKnownPositionAsync,
  requestForegroundPermissionsAsync,
  requestBackgroundPermissionsAsync,
  getForegroundPermissionsAsync,
  getBackgroundPermissionsAsync,
  geocodeAsync,
  reverseGeocodeAsync,
  hasServicesEnabledAsync,
  isBackgroundLocationAvailableAsync,
};

module.exports.default = module.exports;
