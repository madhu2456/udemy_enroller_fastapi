import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';

type Props = {
	source: { uri?: string; html?: string; headers?: Record<string, string> };
	style?: StyleProp<ViewStyle>;
	injectedJavaScript?: string;
	onMessage?: (ev: { nativeEvent: { data: string } }) => void;
	onLoadStart?: () => void;
	onLoad?: () => void;
	onLoadEnd?: () => void;
	onError?: (syntheticEvent: {
		nativeEvent: { code: number; description: string };
	}) => void;
	onNavigationStateChange?: (navState: {
		url: string;
		loading: boolean;
		canGoBack: boolean;
		canGoForward: boolean;
	}) => void;
	onShouldStartLoadWithRequest?: (event: { url: string }) => boolean;
	scrollEnabled?: boolean;
	bounces?: boolean;
};

/**
 * Web-based implementation of React Native WebView using iframe
 */
export const WebView = forwardRef((props: Props, ref) => {
	const iframeRef = useRef<HTMLIFrameElement>(null);
	const {
		source,
		style,
		injectedJavaScript,
		onMessage,
		onLoadStart,
		onLoad,
		onLoadEnd,
		onNavigationStateChange,
	} = props;

	useEffect(() => {
		const handleMessage = (event: MessageEvent) => {
			onMessage?.({ nativeEvent: { data: event.data } });
		};
		window.addEventListener('message', handleMessage);
		return () => window.removeEventListener('message', handleMessage);
	}, [onMessage]);

	// Imperative handle to match RN WebView API
	useImperativeHandle(ref, () => ({
		injectJavaScript: (js: string) => {
			iframeRef.current?.contentWindow?.postMessage(js, '*');
		},
		goBack: () => {
			iframeRef.current?.contentWindow?.history.back();
		},
		goForward: () => {
			iframeRef.current?.contentWindow?.history.forward();
		},
		reload: () => {
			iframeRef.current?.contentWindow?.location.reload();
		},
		stopLoading: () => {
			// Not directly possible with iframe
		},
	}));

	const src = source.html
		? `data:text/html;charset=utf-8,${encodeURIComponent(source.html)}`
		: source.uri;

	return (
		<iframe
			ref={iframeRef}
			src={src}
			style={{
				border: 'none',
				width: '100%',
				height: '100%',
				overflow: props.scrollEnabled === false ? 'hidden' : 'auto',
				...(style as Record<string, unknown>),
			}}
			allow="third-party-cookies"
			onLoad={(e) => {
				onLoadStart?.();
				onLoad?.();
				onLoadEnd?.();
				if (injectedJavaScript) {
					iframeRef.current?.contentWindow?.postMessage(
						injectedJavaScript,
						'*'
					);
				}
				const win = e.currentTarget.contentWindow;
				if (win) {
					onNavigationStateChange?.({
						url: win.location.href,
						loading: false,
						canGoBack: win.history.length > 1,
						canGoForward: win.history.length > 1,
					});
				}
			}}
		/>
	);
});

export default WebView;
