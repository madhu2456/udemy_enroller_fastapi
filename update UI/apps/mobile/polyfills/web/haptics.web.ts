export enum NotificationFeedbackType {
	Success = 'success',
	Warning = 'warning',
	Error = 'error',
}

export enum ImpactFeedbackStyle {
	Light = 'light',
	Medium = 'medium',
	Heavy = 'heavy',
	Soft = 'soft',
	Rigid = 'rigid',
}

const vibrationPatterns: Record<
	NotificationFeedbackType | ImpactFeedbackStyle | 'selection',
	VibratePattern
> = {
	[NotificationFeedbackType.Success]: [40, 100, 40],
	[NotificationFeedbackType.Warning]: [50, 100, 50],
	[NotificationFeedbackType.Error]: [60, 100, 60, 100, 60],
	[ImpactFeedbackStyle.Light]: [40],
	[ImpactFeedbackStyle.Medium]: [50],
	[ImpactFeedbackStyle.Heavy]: [60],
	[ImpactFeedbackStyle.Soft]: [35],
	[ImpactFeedbackStyle.Rigid]: [45],
	selection: [50],
};

function isVibrationAvailable(): boolean {
	return (
		typeof window !== 'undefined' &&
		'navigator' in window &&
		'vibrate' in navigator
	);
}

export const selectionAsync = async (): Promise<void> => {
	if (!isVibrationAvailable()) {
		return;
	}
	navigator.vibrate(vibrationPatterns.selection);
};

export const notificationAsync = async (
	type: NotificationFeedbackType = NotificationFeedbackType.Success
): Promise<void> => {
	if (!isVibrationAvailable()) {
		return;
	}
	navigator.vibrate(vibrationPatterns[type]);
};

export const impactAsync = async (
	style: ImpactFeedbackStyle = ImpactFeedbackStyle.Medium
): Promise<void> => {
	if (!isVibrationAvailable()) {
		return;
	}
	navigator.vibrate(vibrationPatterns[style]);
};
