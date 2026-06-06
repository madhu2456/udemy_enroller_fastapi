export {
	SafeAreaProvider,
	SafeAreaInsetsContext,
	SafeAreaFrameContext,
	useSafeAreaFrame,
	initialWindowMetrics,
} from 'react-native-safe-area-context/lib/commonjs';
import { useSafeAreaInsets as useNativeSafeAreaInsets } from 'react-native-safe-area-context/lib/commonjs';

export { SafeAreaView } from './SafeAreaView.web';

export const useSafeAreaInsets = () => {
	const isTabletAndAbove =
		typeof window !== 'undefined' ? window.self !== window.top : true;
	const insets = useNativeSafeAreaInsets();
	if (isTabletAndAbove) {
		return {
			left: 0,
			right: 0,
			top: 64,
			bottom: 34,
		};
	}
	return insets;
};
