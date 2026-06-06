import React, { useState, useEffect, useRef } from 'react';
import {
	View,
	Text,
	Modal,
	StyleSheet,
	Animated,
	TouchableOpacity,
	TextInput,
} from 'react-native';

type AlertButton = {
	text: string;
	onPress?: (value?: string | { login: string; password: string }) => void;
	style: 'cancel' | 'destructive' | 'default';
};

type AlertOptions = {
	userInterfaceStyle: string;
};

type AlertType = 'default' | 'plain-text' | 'secure-text' | 'login-password';

let globalAlertData = {
	visible: false,
	title: '',
	message: '',
	buttons: [{ text: 'OK', onPress: () => {}, style: 'default' }],
	userInterfaceStyle: 'light',
};
let setGlobalAlert: ((data: typeof globalAlertData) => void) | null = null;

let globalPromptData = {
	visible: false,
	title: '',
	message: '',
	callbackOrButtons: [{ text: 'OK', onPress: () => {}, style: 'default' }],
	type: 'default',
	defaultValue: '',
	keyboardType: 'default',
	userInterfaceStyle: 'light',
};
let setGlobalPrompt: ((data: typeof globalPromptData) => void) | null = null;

const processButtons = (
	buttons?: AlertButton[],
	includeCancel = false
): AlertButton[] => {
	let processedButtons =
		buttons && buttons.length > 0
			? buttons.map((button) => ({ ...button, onPress: button.onPress || (() => {}) }))
			: includeCancel
				? [
						{ text: 'Cancel', onPress: () => {}, style: 'cancel' as const },
						{ text: 'OK', onPress: () => {}, style: 'default' as const },
					]
				: [{ text: 'OK', onPress: () => {}, style: 'default' as const }];

	// cancel button should always be the last button unless there are two buttons
	if (processedButtons.length === 2) {
		const cancelIndex = processedButtons.findIndex(
			(btn) => btn.style === 'cancel'
		);
		if (cancelIndex === 1) {
			processedButtons = [processedButtons[1], processedButtons[0]];
		}
	} else if (processedButtons.length >= 3) {
		const cancelIndex = processedButtons.findLastIndex(
			(btn) => btn.style === 'cancel'
		);
		if (cancelIndex !== -1 && cancelIndex !== processedButtons.length - 1) {
			const cancelButton = processedButtons[cancelIndex];
			const otherButtons = processedButtons.filter(
				(_, index) => index !== cancelIndex
			);
			processedButtons = [...otherButtons, cancelButton];
		}
	}

	return processedButtons;
};

const Alert = {
	alert(
		title: string,
		message: string,
		buttons?: AlertButton[],
		userInterfaceStyle?: AlertOptions
	) {
		const processedButtons = processButtons(buttons);

		globalAlertData = {
			visible: true,
			title: title,
			message: message || '',
			buttons: processedButtons.map((button) => ({
				...button,
				onPress: button.onPress || (() => {}),
			})),
			userInterfaceStyle: userInterfaceStyle?.userInterfaceStyle || 'light',
		};
		if (setGlobalAlert) {
			setGlobalAlert({ ...globalAlertData });
		}
	},

	prompt(
		title: string,
		message?: string,
		callbackOrButtons?: AlertButton[],
		type?: AlertType,
		defaultValue?: string,
		keyboardType?: string,
		userInterfaceStyle?: AlertOptions
	) {
		const processedButtons = processButtons(callbackOrButtons, true);

		globalPromptData = {
			visible: true,
			title: title,
			message: message || '',
			callbackOrButtons: processedButtons.map((button) => ({
				...button,
				onPress: button.onPress || (() => {}),
			})),
			type: type || 'plain-text',
			defaultValue: defaultValue || '',
			keyboardType: keyboardType || 'default',
			userInterfaceStyle: userInterfaceStyle?.userInterfaceStyle || 'light',
		};
		if (setGlobalPrompt) {
			setGlobalPrompt({ ...globalPromptData });
		}
	},
};

export const AlertModal = () => {
	const [alertData, setAlertData] = useState(globalAlertData);
	const [promptData, setPromptData] = useState(globalPromptData);
	const [modalVisible, setModalVisible] = useState(false);
	const [currentModalData, setCurrentModalData] = useState<{
		visible: boolean;
		title: string;
		message: string;
		buttons: {
			text: string;
			onPress: (value?: string | { login: string; password: string }) => void;
			style: string;
		}[];
		userInterfaceStyle: string;
		isPrompt: boolean;
		type?: string;
		defaultValue?: string;
		keyboardType?: string;
	} | null>(null);
	const [inputValue, setInputValue] = useState('');
	const [loginValue, setLoginValue] = useState('');
	const scaleAnim = useRef(new Animated.Value(1.25)).current;
	const opacityAnim = useRef(new Animated.Value(0)).current;

	useEffect(() => {
		const showModal = () => {
			setModalVisible(true);
			Animated.parallel([
				Animated.timing(opacityAnim, {
					toValue: 1,
					duration: 250,
					useNativeDriver: true,
				}),
				Animated.timing(scaleAnim, {
					toValue: 1,
					duration: 250,
					useNativeDriver: true,
				}),
			]).start();
		};

		if (promptData.visible) {
			setCurrentModalData({
				...promptData,
				isPrompt: true,
				buttons: promptData.callbackOrButtons,
			});
			showModal();
		} else if (alertData.visible) {
			setCurrentModalData({
				...alertData,
				buttons: alertData.buttons,
				isPrompt: false,
			});
			showModal();
		} else {
			setCurrentModalData(null);
		}
	}, [
		promptData.visible,
		alertData.visible,
		promptData,
		alertData,
		opacityAnim,
		scaleAnim,
	]);

	const modalData = currentModalData || {
		...alertData,
		isPrompt: false,
		buttons: alertData.buttons,
		type: 'default',
		defaultValue: '',
		keyboardType: 'default',
	};

	useEffect(() => {
		setGlobalAlert = setAlertData;
		setGlobalPrompt = setPromptData;
		return () => {
			setGlobalAlert = null;
			setGlobalPrompt = null;
		};
	}, []);

	const closeModal = () => {
		Animated.timing(opacityAnim, {
			toValue: 0,
			duration: 250,
			useNativeDriver: true,
		}).start(() => {
			setModalVisible(false);
			scaleAnim.setValue(1.25);
			setInputValue('');
			setLoginValue('');
			globalAlertData = {
				visible: false,
				title: '',
				message: '',
				buttons: [],
				userInterfaceStyle: 'light',
			};
			globalPromptData = {
				visible: false,
				title: '',
				message: '',
				callbackOrButtons: [],
				type: 'default',
				defaultValue: '',
				keyboardType: 'default',
				userInterfaceStyle: 'light',
			};
			setAlertData(globalAlertData);
			setPromptData(globalPromptData);
			setCurrentModalData(null);
		});
	};

	const styles = styling(modalData.userInterfaceStyle);

	return (
		<Modal visible={modalVisible} transparent animationType="none">
			<Animated.View style={[styles.container, { opacity: opacityAnim }]}>
				<Animated.View
					style={[
						styles.content,
						{ transform: [{ scale: scaleAnim }] },
						modalData.userInterfaceStyle === 'dark'
							? {
									backgroundColor: 'rgba(0,0,0,0.65)',
								}
							: { backgroundColor: 'rgba(255, 255, 255, 0.75)' },
					]}
				>
					<View style={styles.contentContainer}>
						<Text
							style={[
								styles.title,
								modalData.userInterfaceStyle === 'dark' && {
									color: 'white',
								},
							]}
						>
							{modalData.title}
						</Text>
						{modalData.message ? (
							<Text
								style={[
									styles.message,
									modalData.userInterfaceStyle === 'dark' && {
										color: 'white',
									},
								]}
							>
								{modalData.message}
							</Text>
						) : null}
						{modalData?.isPrompt && modalData.type !== 'default' ? (
							<View>
								{modalData.type === 'login-password' ? (
									<TextInput
										style={[
											styles.textInput,
											styles.textInputTop,
											modalData.userInterfaceStyle === 'dark'
												? {
														backgroundColor: 'rgba(0, 0, 0, 0.6)',
														color: 'white',
														borderColor: 'rgba(255,255,255,0.3)',
													}
												: {
														backgroundColor: 'rgba(255,255,255,0.9)',
														color: 'black',
														borderColor: 'rgba(0, 0, 0, 0.2)',
													},
										]}
										value={loginValue}
										onChangeText={setLoginValue}
										placeholder="Login"
										placeholderTextColor={
											modalData.userInterfaceStyle === 'dark'
												? 'rgba(255,255,255,0.5)'
												: 'rgba(0,0,0,0.5)'
										}
										autoFocus
									/>
								) : null}
								<TextInput
									style={[
										styles.textInput,
										modalData.type === 'login-password' &&
											styles.textInputBottom,
										modalData.userInterfaceStyle === 'dark'
											? {
													backgroundColor: 'rgba(0, 0, 0, 0.6)',
													color: 'white',
													borderColor: 'rgba(255,255,255,0.3)',
												}
											: {
													backgroundColor: 'rgba(255,255,255,0.9)',
													color: 'black',
													borderColor: 'rgba(0, 0, 0, 0.2)',
												},
									]}
									value={inputValue}
									onChangeText={setInputValue}
									placeholder={(() => {
										switch (modalData.type) {
											case 'plain-text':
												return '';
											case 'secure-text':
											case 'login-password':
												return 'Password';
											default:
												return '';
										}
									})()}
									placeholderTextColor={
										modalData.userInterfaceStyle === 'dark'
											? 'rgba(255,255,255,0.5)'
											: 'rgba(0,0,0,0.5)'
									}
									secureTextEntry={
										modalData.type === 'secure-text' ||
										modalData.type === 'login-password'
									}
									keyboardType={
										modalData.keyboardType === 'numeric' ? 'numeric' : 'default'
									}
									autoFocus={modalData.type !== 'login-password'}
								/>
							</View>
						) : null}
					</View>
					<View
						style={[
							modalData.buttons.length >= 3
								? styles.buttonColumnContainer
								: styles.buttonRowContainer,
							modalData.buttons.length <= 2 && styles.buttonTopBorder,
						]}
					>
						{modalData.buttons.map((button, index) => (
							<TouchableOpacity
								key={`${button.text}-${index}`}
								onPress={() => {
									if (modalData?.isPrompt) {
										let valueToPass:
											| string
											| { login: string; password: string } = inputValue;
										if (modalData.type === 'login-password') {
											valueToPass = {
												login: loginValue,
												password: inputValue,
											};
										}
										button.onPress(valueToPass);
									} else {
										button.onPress();
									}
									closeModal();
								}}
								style={[
									styles.button,
									modalData.buttons.length >= 3 && styles.buttonTopBorder,
									modalData.buttons.length === 2 && { width: '50%' },
									modalData.buttons.length <= 1 && { width: '100%' },
									index === 0 &&
										modalData.buttons.length === 2 && {
											borderRightWidth: 1,
											borderColor:
												modalData.userInterfaceStyle === 'dark'
													? 'rgba(255,255,255,0.2)'
													: 'lightgray',
										},
								]}
							>
								<Text
									style={[
										styles.buttonText,
										button.style === 'cancel' && { fontWeight: '600' },
										button.style === 'destructive' && { color: 'red' },
									]}
								>
									{button.text}
								</Text>
							</TouchableOpacity>
						))}
					</View>
				</Animated.View>
			</Animated.View>
		</Modal>
	);
};

const styling = (userInterfaceStyle: string) =>
	StyleSheet.create<Record<string, any>>({
		container: {
			flex: 1,
			justifyContent: 'center',
			alignItems: 'center',
			backgroundColor: 'rgba(0,0,0,0.2)',
		},
		content: {
			backdropFilter: 'blur(20px)' as any,
			borderRadius: 12,
			width: 244,
		},
		contentContainer: {
			paddingVertical: 20,
			paddingHorizontal: 12,
			gap: 4,
		},
		title: {
			fontSize: 16,
			fontWeight: '600',
			textAlign: 'center',
		},
		message: {
			fontSize: 12,
			textAlign: 'center',
		},
		button: {
			paddingVertical: 12,
		},
		buttonText: {
			color: '#007AFF',
			textAlign: 'center',
			fontSize: 16,
		},
		textInput: {
			borderWidth: 0.5,
			borderColor: 'lightgray',
			borderRadius: 8,
			paddingHorizontal: 12,
			paddingVertical: 8,
			marginTop: 16,
			marginBottom: -8,
			marginHorizontal: 12,
			fontSize: 12,
			outlineStyle: 'none' as any,
		},
		textInputTop: {
			borderTopLeftRadius: 8,
			borderTopRightRadius: 8,
			borderBottomLeftRadius: 0,
			borderBottomRightRadius: 0,
			borderBottomWidth: 0,
			marginBottom: 0,
		},
		textInputBottom: {
			borderTopLeftRadius: 0,
			borderTopRightRadius: 0,
			borderBottomLeftRadius: 8,
			borderBottomRightRadius: 8,
			marginTop: 0,
		},
		buttonTopBorder: {
			borderTopWidth: 0.5,
			borderTopColor:
				userInterfaceStyle === 'dark'
					? 'rgba(255,255,255,0.2)'
					: 'lightgray',
		},
		buttonRowContainer: {
			flexDirection: 'row',
			borderTopWidth: 0.5,
			borderTopColor:
				userInterfaceStyle === 'dark'
					? 'rgba(255,255,255,0.2)'
					: 'lightgray',
		},
		buttonColumnContainer: {
			flexDirection: 'column',
		},
		buttonRightBorder: {
			borderRightWidth: 0.5,
			borderRightColor:
				userInterfaceStyle === 'dark'
					? 'rgba(255,255,255,0.2)'
					: 'lightgray',
		},
	});

export default Alert;
