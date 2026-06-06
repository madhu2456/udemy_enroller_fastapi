import type React from "react";
import { useCallback, useEffect, useMemo, memo, useRef, useReducer } from "react";
import {
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  PanResponder,
  Platform,
  useWindowDimensions,
} from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  interpolate,
  withTiming,
  Easing,
} from "react-native-reanimated";
import {
  SafeAreaProvider,
  useSafeAreaInsets,
} from "react-native-safe-area-context";
import Svg, {
  Path,
  Rect,
  Mask,
  Circle,
  G,
  Defs,
  ClipPath,
  Line,
} from "react-native-svg";
import { NativeModule, requireNativeModule } from "expo-modules-core";
import { MotiView } from "moti";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { WebView } from "react-native-webview";

declare class AnythingLauncherModule extends NativeModule {
  open(url: string): Promise<void>;
  reset(): Promise<void>;
  reload(): Promise<void>;
  isWeb(): Promise<boolean>;
}

const TINT_DURATION_MS = 3000;
const CIRCLE_DIAMETER = 80;
const GAP = 16;
const ICON_SIZE = 18;

const getWebAppUrl = () => {
  return process.env.EXPO_PUBLIC_APP_URL ?? "";
};

const isAnythingApp =
  Platform.OS !== "web" &&
  process.env.EXPO_PUBLIC_IS_ANYTHING_APP === JSON.stringify(true);

const AnythingLauncher = isAnythingApp
  ? requireNativeModule<AnythingLauncherModule>("AnythingLauncherModule")
  : null;

const RefreshIcon = memo(() => {
  return (
    <Svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 18 18" fill="none">
      <Path
        d="M1.5 7.5s1.504-2.049 2.725-3.271a6.75 6.75 0 11-1.712 6.646M1.5 7.5V3m0 4.5H6"
        stroke="#7E7F80"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
});

const CloseIcon = memo(() => {
  return (
    <Svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 18 18" fill="none">
      <Path
        d="M2.25 15.75l13.5-13.5M15.75 15.75L2.25 2.25"
        stroke="#7E7F80"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
});

const MobileViewIcon = memo(({ color }: { color: string }) => {
  return (
    <Svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 18 18" fill="none">
      <Path
        d="M11.8125 1.5H6.1875C5.15197 1.5 4.3125 2.33947 4.3125 3.375V14.625C4.3125 15.6605 5.15197 16.5 6.1875 16.5H11.8125C12.848 16.5 13.6875 15.6605 13.6875 14.625V3.375C13.6875 2.33947 12.848 1.5 11.8125 1.5Z"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Line
        x1={7.89575}
        y1={13.3832}
        x2={10.104}
        y2={13.3832}
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
});

const WebViewIcon = memo(({ color }: { color: string }) => {
  return (
    <Svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 18 18" fill="none">
      <G clipPath="url(#clip0_340_2754)">
        <Path
          d="M15 1.5H3C2.17157 1.5 1.5 2.17157 1.5 3V12C1.5 12.8284 2.17157 13.5 3 13.5H15C15.8284 13.5 16.5 12.8284 16.5 12V3C16.5 2.17157 15.8284 1.5 15 1.5Z"
          stroke={color}
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <Path
          d="M9 13.5V16.5"
          stroke={color}
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <Path
          d="M6 16.5H12"
          stroke={color}
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </G>
      <Defs>
        <ClipPath id="clip0_340_2754">
          <Rect width={18} height={18} fill="white" />
        </ClipPath>
      </Defs>
    </Svg>
  );
});

const ActiveDot = memo(() => {
  return (
    <View
      style={{
        backgroundColor: "#000",
        borderRadius: 50,
        width: 4,
        height: 4,
        position: "absolute",
        bottom: -8,
      }}
    />
  );
});

const InstructionsOverlay = memo(
  ({
    showTint,
    width,
    height,
  }: {
    showTint: boolean;
    width: number;
    height: number;
  }) => {
    const r = CIRCLE_DIAMETER / 2;
    const totalWidth = CIRCLE_DIAMETER * 2 + GAP;
    const left = (width - totalWidth) / 2;
    const cx1 = left + r;
    const cx2 = cx1 + CIRCLE_DIAMETER + GAP;
    const cy = height / 2 + 64;

    return (
      <>
        <MotiView
          from={{ opacity: 0 }}
          animate={{ opacity: showTint ? 1 : 0 }}
          transition={{ type: "timing", duration: 350 }}
          style={menuStyles.holdTwoFingersTextContainer}
        >
          <Text style={menuStyles.holdTwoFingersText}>
            Hold with 2 fingers for menu
          </Text>
        </MotiView>
        <MotiView
          from={{ opacity: 0 }}
          animate={{ opacity: showTint ? 1 : 0 }}
          transition={{ type: "timing", duration: 350 }}
          style={StyleSheet.absoluteFill}
        >
          <Svg width={width} height={height} style={StyleSheet.absoluteFill}>
            <Mask id="holes">
              <Rect x="0" y="0" width={width} height={height} fill="white" />
              <Circle cx={cx1} cy={cy} r={r} fill="black" />
              <Circle cx={cx2} cy={cy} r={r} fill="black" />
            </Mask>

            <Rect
              x="0"
              y="0"
              width={width}
              height={height}
              fill="black"
              opacity={0.8}
              mask="url(#holes)"
            />
          </Svg>
        </MotiView>
      </>
    );
  }
);

type State = {
  isLoading: boolean;
  showTint: boolean;
  showWebView: boolean;
}

type Action = { type: 'INITIALIZE', payload: { showWebView: boolean, showTint: boolean } } | { type: 'TOGGLE_WEB_VIEW' } | { type: 'HIDE_TINT' }

const initialState: State = { isLoading: true, showTint: false, showWebView: false };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'INITIALIZE':
      return { ...state, ...action.payload, isLoading: false };
    case 'TOGGLE_WEB_VIEW':
      return { ...state, showWebView: !state.showWebView };
    case 'HIDE_TINT':
      return { ...state, showTint: false };
    default:
      return state;
  }
}

const AnythingMenu = isAnythingApp
  ? ({ children }: { children: React.ReactNode }) => {
    const insets = useSafeAreaInsets();
    const [state, dispatch] = useReducer(reducer, initialState);
    const { width, height } = useWindowDimensions();

    useEffect(() => {
      if (!AnythingLauncher) {
        throw new Error("AnythingLauncher is not available");
      }

      if (state.isLoading) {
        Promise.all([
          AnythingLauncher.isWeb(),
          AsyncStorage.getItem("hasSeenOnboarding"),
        ]).then(([isWeb, hasSeenOnboarding]) => {
          dispatch({ type: 'INITIALIZE', payload: { showWebView: Boolean(isWeb), showTint: hasSeenOnboarding !== 'true' } });
        }).catch(() => {
          dispatch({ type: 'INITIALIZE', payload: { showWebView: false, showTint: false } });
        });
      }
    }, [state.isLoading]);

    useEffect(() => {
      if (!state.isLoading && state.showTint) {
        const timeout = setTimeout(() => {
          void AsyncStorage.setItem("hasSeenOnboarding", "true");
          dispatch({ type: 'HIDE_TINT' });
        }, TINT_DURATION_MS);

        return () => clearTimeout(timeout);
      }

    }, [state.isLoading, state.showTint])

    const menuProgress = useSharedValue(0);

    const hideMenuOffset = -(44 + 36 + insets.top + 10);

    const exitApp = useCallback(() => {
      void AnythingLauncher?.reset();
    }, []);

    const reloadApp = useCallback(() => {
      void AnythingLauncher?.reload();
    }, []);

    const toggleWebView = useCallback(() => {
      dispatch({ type: 'TOGGLE_WEB_VIEW' });
    }, []);

    const animatedStyle = useAnimatedStyle(() => {
      const scale = interpolate(menuProgress.value, [0, 1], [1, 0.9]);
      const shadowOpacity = interpolate(menuProgress.value, [0, 1], [0, 0.4]);
      const elevation = interpolate(menuProgress.value, [0, 1], [0, 8]);

      return {
        transform: [{ scale }],
        shadowOpacity,
        shadowOffset: { width: 0, height: 0 },
        shadowRadius: 32,
        elevation,
      };
    }, []);

    const menuAnimatedStyle = useAnimatedStyle(() => {
      const translateY = interpolate(
        menuProgress.value,
        [0, 1],
        [hideMenuOffset, 0]
      );

      return {
        transform: [{ translateY }],
      };
    }, [hideMenuOffset]);

    const appPointerEvents = useAnimatedStyle(() => {
      return {
        pointerEvents: menuProgress.value === 1 ? "box-only" : "auto",
      };
    }, [menuProgress]);

    const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

    const panResponder = useMemo(
      () =>
        PanResponder.create({
          onStartShouldSetPanResponder: (evt, gestureState) => {
            if (menuProgress.value === 1) {
              menuProgress.value = withTiming(0, {
                duration: 300,
                easing: Easing.ease,
              });
              if (longPressTimer.current) {
                clearTimeout(longPressTimer.current);
                longPressTimer.current = null;
              }
              return false;
            }
            if (gestureState.numberActiveTouches === 2) {
              longPressTimer.current = setTimeout(() => {
                menuProgress.value = withTiming(1, {
                  duration: 300,
                  easing: Easing.ease,
                });
                longPressTimer.current = null;
              }, 500);
              return true;
            }
            return false;
          },
          onPanResponderEnd: (_evt, _gestureState) => {
            if (longPressTimer.current) {
              clearTimeout(longPressTimer.current);
              longPressTimer.current = null;
            }
          },
        }),
      [menuProgress.value]
    );

    const menuHeaderStyle = useMemo(
      () => ({
        ...menuStyles.menuHeader,
        marginTop: insets.top + 10,
      }),
      [insets.top]
    );

    if (state.isLoading) {
      return null
    }

    return (
      <View style={styles.container}>
        <Animated.View
          style={[styles.fill, animatedStyle]}
          pointerEvents="box-none"
          {...panResponder.panHandlers}
        >
          <Animated.View style={[styles.fillContent, appPointerEvents]}>
            {!state.showWebView ? (
              children
            ) : (
              <WebView
                source={{ uri: getWebAppUrl() }}
                style={[styles.webView, { paddingTop: insets.top }]}
              />
            )}
          </Animated.View>
        </Animated.View>
        <Animated.View style={[styles.menuContainer, menuAnimatedStyle]}>
          <View style={menuStyles.menuContainerStyle}>
            <View style={menuHeaderStyle}>
              <View style={menuStyles.leftSection}>
                <TouchableOpacity
                  onPress={toggleWebView}
                  style={menuStyles.button}
                >
                  <MobileViewIcon
                    color={state.showWebView ? "#7E7F80" : "#18191B"}
                  />
                  {!state.showWebView && <ActiveDot />}
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={toggleWebView}
                  style={menuStyles.button}
                >
                  <WebViewIcon color={state.showWebView ? "#18191B" : "#7E7F80"} />
                  {state.showWebView && <ActiveDot />}
                </TouchableOpacity>
              </View>
              <View style={menuStyles.buttonContainer}>
                <TouchableOpacity
                  onPress={reloadApp}
                  style={menuStyles.button}
                >
                  <RefreshIcon />
                </TouchableOpacity>
                <TouchableOpacity onPress={exitApp} style={menuStyles.button}>
                  <CloseIcon />
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Animated.View>
        <InstructionsOverlay
          showTint={state.showTint}
          width={width}
          height={height}
        />
      </View>
    );
  }
  : ({ children }: { children: React.ReactNode }) => children;

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff",
  },
  fillContent: {
    flex: 1,
    borderRadius: 16,
    overflow: "hidden",
  },
  fill: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  menuContainer: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 1000,
  },
  menuTouchable: {
    flex: 1,
  },
  bottomSheetBackground: {
    backgroundColor: "white",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
  },
  contentContainer: {
    flex: 1,
    paddingHorizontal: 20,
    paddingVertical: 20,
  },
  webViewContainer: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "#fff",
    zIndex: 2000,
  },
  webViewHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingVertical: 18,
    backgroundColor: "#fff",
    borderBottomWidth: 1,
    borderBottomColor: "#e0e0e0",
  },
  webViewTitle: {
    fontSize: 18,
    fontWeight: "600",
    color: "#18191B",
  },
  webViewCloseButton: {
    width: 18,
    height: 18,
    justifyContent: "center",
    alignItems: "center",
  },
  webView: {
    flex: 1,
  },
});

const menuStyles = StyleSheet.create({
  menuContainerStyle: {
    backgroundColor: "#fff",
    shadowColor: "#000",
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
    elevation: 5,
  },
  menuHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingVertical: 18,
  },
  appIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    marginRight: 20,
  },
  appTitle: {
    fontSize: 18,
    fontWeight: "600",
    color: "#18191B",
    flex: 1,
  },
  buttonContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 28,
  },
  button: {
    width: 18,
    height: 18,
    justifyContent: "center",
    alignItems: "center",
  },
  leftSection: {
    flexDirection: "row",
    alignItems: "center",
    gap: 28,
    flex: 1,
  },
  holdTwoFingersTextContainer: {
    zIndex: 1,
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    justifyContent: "center",
    alignItems: "center",
    transform: [{ translateY: -24 }],
  },
  holdTwoFingersText: {
    fontSize: 28,
    color: "#fff",
    fontWeight: "600",
  },
});

export default function Screen({ children }: { children: React.ReactNode }) {
  return (
    <SafeAreaProvider>
      <AnythingMenu>{children}</AnythingMenu>
    </SafeAreaProvider>
  );
}
