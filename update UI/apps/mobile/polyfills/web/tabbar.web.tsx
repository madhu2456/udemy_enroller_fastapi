import { Tabs as ExpoTabs } from 'expo-router/build/layouts/Tabs';
import { merge } from 'lodash';
import { forwardRef } from 'react';
import { Platform } from 'react-native';
export const BASE_TAB_BAR_HEIGHT = Platform.OS === 'ios' ? 49 : 56;

export const Tabs = forwardRef((props: any, ref: any) => {
  const isInIframe = typeof window !== 'undefined' ? window.self !== window.top : false;
  const height = props.screenOptions.tabBarStyle?.height || (BASE_TAB_BAR_HEIGHT + (isInIframe ? 34 : 0));

  return (
    <ExpoTabs
      {...props}
      screenOptions={merge(props.screenOptions, {
        tabBarStyle: merge(props.screenOptions.tabBarStyle, { height }),
      })}
      ref={ref}
    />
  );
});

(Tabs as any).Screen = ExpoTabs.Screen;

export default Tabs;
