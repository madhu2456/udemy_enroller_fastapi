import LauncherMenuContainer from '@anythingai/app/screens/launcher-menu';
import React from 'react';
import { StyleSheet, View } from 'react-native';

const isExpoGo = globalThis.expo?.modules?.ExpoGo;

export default () => {
  if (isExpoGo) {
    return null;
  }
  return (
    <View
      style={{ ...StyleSheet.absoluteFillObject, zIndex: 9999 }}
      pointerEvents="box-none"
    >
      <LauncherMenuContainer />
    </View>
  );
};
