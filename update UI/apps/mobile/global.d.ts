declare module 'react-native/Libraries/Core/ExceptionsManager' {
  export function handleException(err: Error, isFatal: boolean): void;
}

declare module 'react-native-safe-area-context/lib/commonjs' {
  export const SafeAreaView: React.ComponentType<any>;
  export const SafeAreaProvider: React.ComponentType<any>;
  export const SafeAreaInsetsContext: React.Context<any>;
  export const SafeAreaFrameContext: React.Context<any>;
  export function useSafeAreaInsets(): { top: number; right: number; bottom: number; left: number };
  export function useSafeAreaFrame(): { x: number; y: number; width: number; height: number };
  export const initialWindowMetrics: any;
}

declare module 'react-native-web-refresh-control' {
  export const RefreshControl: React.ComponentType<any>;
}

declare module 'react-native-web/dist/exports/ScrollView' {
  const ScrollView: React.ComponentType<any>;
  export default ScrollView;
}

declare module '@anythingai/app/screens/launcher-menu' {
  const LauncherMenuContainer: React.ComponentType<any>;
  export default LauncherMenuContainer;
}

declare module 'lodash' {
  export function merge<T>(...args: T[]): T;
}

declare module '*.css' {}
