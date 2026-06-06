import { useFocusEffect } from '@react-navigation/native';
import { useNavigation } from 'expo-router';
import { BackHandler } from 'react-native';

export const usePreventBack = (): void => {
	const navigation = useNavigation();

	useFocusEffect(() => {
		navigation.setOptions({
			headerLeft: () => null,
			gestureEnabled: false,
		});

		navigation.getParent()?.setOptions({ gestureEnabled: false });

		// Android back button handler
		const hardwareBackPressHandler = BackHandler.addEventListener(
			'hardwareBackPress',
			() => {
				// Prevent default behavior of leaving the screen
				return true;
			}
		);

		return () => {
			navigation.getParent()?.setOptions({ gestureEnabled: true });
			navigation.setOptions({
				gestureEnabled: true,
			});
			hardwareBackPressHandler.remove();
		};
	});
};

export default usePreventBack;
