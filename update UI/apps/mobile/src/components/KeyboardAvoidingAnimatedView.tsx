import React, { useRef, useEffect, forwardRef } from 'react';
import { Platform, Keyboard, KeyboardAvoidingView, LayoutChangeEvent, ViewStyle, KeyboardEvent } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

interface Layout {
	x: number;
	y: number;
	width: number;
	height: number;
}

interface KeyboardAvoidingAnimatedViewProps {
	children: React.ReactNode;
	behavior?: 'padding' | 'height' | 'position';
	keyboardVerticalOffset?: number;
	style?: ViewStyle;
	contentContainerStyle?: ViewStyle;
	enabled?: boolean;
	onLayout?: (event: LayoutChangeEvent) => void;
}

const KeyboardAvoidingAnimatedView = forwardRef<Animated.View, KeyboardAvoidingAnimatedViewProps>((props, ref) => {
  const {
    children,
    behavior = Platform.OS === 'ios' ? 'padding' : 'height',
    keyboardVerticalOffset = 0,
    style,
    contentContainerStyle,
    enabled = true,
    onLayout,
    ...leftoverProps
  } = props;

  const animatedViewRef = useRef<Layout | null>(null); // ref to animated view in this polyfill
  const initialHeight = useSharedValue(0); // original height of animated view before keyboard appears
  const bottomHeight = useSharedValue(0); // whats going to be added to the bottom when keyboard appears

  useEffect(() => {
    if (!enabled) return;

    const onKeyboardShow = (event: KeyboardEvent) => {
      const { duration, endCoordinates } = event;
      const animatedView = animatedViewRef.current;

      if (!animatedView) return;

      let height = 0;

      // calculate how much the view needs to move up
      const keyboardY = endCoordinates.screenY - keyboardVerticalOffset;
      height = Math.max(animatedView.y + animatedView.height - keyboardY, 0);

      bottomHeight.value = withTiming(height, {
        duration: duration > 10 ? duration : 300,
      });
    };

    const onKeyboardHide = () => {
      bottomHeight.value = withTiming(0, { duration: 300 });
    };

    const showEvent = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvent = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';

    const showSubscription = Keyboard.addListener(showEvent, onKeyboardShow);
    const hideSubscription = Keyboard.addListener(hideEvent, onKeyboardHide);

    return () => {
      showSubscription.remove();
      hideSubscription.remove();
    };
  }, [keyboardVerticalOffset, enabled, bottomHeight]);

  const animatedStyle = useAnimatedStyle(() => {
    if (behavior === 'height') {
      return {
        height: initialHeight.value - bottomHeight.value,
        flex: bottomHeight.value > 0 ? 0 : (null as never),
      };
    }
    if (behavior === 'padding') {
      return {
        paddingBottom: bottomHeight.value,
      };
    }
    return {};
  });

  const positionAnimatedStyle = useAnimatedStyle(() => ({
    bottom: bottomHeight.value,
  }));

  const handleLayout = (event: LayoutChangeEvent) => {
    const layout = event.nativeEvent.layout;
    animatedViewRef.current = layout;

    // initial height before keybaord appears
    if (initialHeight.value === 0) {
      initialHeight.value = layout.height;
    }

    if (onLayout) {
      onLayout(event);
    }
  };

  const renderContent = () => {
    if (behavior === 'position') {
      return (
        <Animated.View style={[contentContainerStyle, positionAnimatedStyle]}>
          {children}
        </Animated.View>
      );
    }
    // render children if padding or height
    return children;
  };

  // for web, default to unused keyboard avoiding view
  if (Platform.OS === 'web') {
    return (
      <KeyboardAvoidingView
        behavior={behavior}
        style={style}
        contentContainerStyle={contentContainerStyle}
        {...leftoverProps}
      >
        {children}
      </KeyboardAvoidingView>
    );
  }

  return (
    <Animated.View
      ref={ref}
      style={[style, animatedStyle]}
      onLayout={handleLayout}
      {...leftoverProps}
    >
      {renderContent()}
    </Animated.View>
  );
});

KeyboardAvoidingAnimatedView.displayName = 'KeyboardAvoidingAnimatedView';

export default KeyboardAvoidingAnimatedView;
