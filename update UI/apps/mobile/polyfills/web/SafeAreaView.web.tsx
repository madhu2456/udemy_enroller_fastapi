import React, { forwardRef, type ReactNode } from 'react';
import { View } from 'react-native';

import { SafeAreaView as NativeSafeAreaView } from 'react-native-safe-area-context/lib/commonjs';
export {
  initialWindowMetrics,
  SafeAreaFrameContext,
  SafeAreaInsetsContext,
  SafeAreaProvider,
  useSafeAreaFrame,
} from 'react-native-safe-area-context/lib/commonjs';

type Edge = 'top' | 'right' | 'bottom' | 'left';
type Edges = Edge[] | Record<Edge, 'off' | 'additive' | 'maximum'>;

interface SafeAreaViewProps {
  children?: ReactNode;
  edges?: Edges;
  [key: string]: unknown;
}

export const SafeAreaView = forwardRef<View, SafeAreaViewProps>(
  ({ children, edges = ['top', 'right', 'bottom', 'left'] as Edges, ...rest }, forwardedRef) => {
    const isTabletAndAbove = typeof window !== 'undefined' ? window.self !== window.top : true;
    return (
      <NativeSafeAreaView {...rest} edges={edges} ref={forwardedRef}>
        {isTabletAndAbove && (Array.isArray(edges) && (edges as Edge[]).includes('top') || (!Array.isArray(edges) && (edges as Record<Edge, string>).top !== 'off')) && (
          <View style={{ height: 64 }} />
        )}
        {children}
        {isTabletAndAbove && (Array.isArray(edges) && (edges as Edge[]).includes('bottom') || (!Array.isArray(edges) && (edges as Record<Edge, string>).bottom !== 'off')) && (
          <View style={{ height: 34 }} />
        )}
      </NativeSafeAreaView>
    );
  }
);
export default SafeAreaView;
