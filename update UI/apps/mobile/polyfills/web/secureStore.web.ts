const VALUE_BYTES_LIMIT = 2048;

const KEYCHAIN_CONSTANTS = {
	AFTER_FIRST_UNLOCK: 0,
	AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY: 1,
	ALWAYS: 2,
	WHEN_PASSCODE_SET_THIS_DEVICE_ONLY: 3,
	ALWAYS_THIS_DEVICE_ONLY: 4,
	WHEN_UNLOCKED: 5,
	WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
};

export type KeychainAccessibilityConstant = number;
export const {
	AFTER_FIRST_UNLOCK,
	AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
	ALWAYS,
	WHEN_PASSCODE_SET_THIS_DEVICE_ONLY,
	ALWAYS_THIS_DEVICE_ONLY,
	WHEN_UNLOCKED,
	WHEN_UNLOCKED_THIS_DEVICE_ONLY,
} = KEYCHAIN_CONSTANTS;

export type SecureStoreOptions = {
	keychainService?: string;
	requireAuthentication?: boolean;
	authenticationPrompt?: string;
	keychainAccessible?: KeychainAccessibilityConstant;
};

function isValidValue(value: string) {
	if (typeof value !== 'string') {
		return false;
	}
	if (new Blob([value]).size > VALUE_BYTES_LIMIT) {
		// biome-ignore lint/suspicious/noConsole: useful for debugging
		console.warn(
			`Value being stored in SecureStore is larger than ${VALUE_BYTES_LIMIT} bytes and it may not be stored successfully.`
		);
	}
	return true;
}

function getStorageKey(key: string): string {
	return `_create_secure_store_${key}`;
}

export async function isAvailableAsync(): Promise<boolean> {
	const testKey = '__SECURE_STORE_AVAILABILITY_TEST_KEY__';
	try {
		localStorage.setItem(testKey, 'test');
		if (localStorage.getItem(testKey) !== 'test') {
			return false;
		}
		localStorage.removeItem(testKey);
		return localStorage.getItem(testKey) === null;
	} catch {
		return false;
	}
}

export async function deleteItemAsync(
	key: string,
	_options: SecureStoreOptions = {}
): Promise<void> {
	localStorage.removeItem(getStorageKey(key));
}

export async function getItemAsync(
	key: string,
	_options: SecureStoreOptions = {}
): Promise<string | null> {
	return localStorage.getItem(getStorageKey(key));
}

export async function setItemAsync(
	key: string,
	value: string,
	_options: SecureStoreOptions = {}
): Promise<void> {
	if (!isValidValue(value)) {
		throw new Error(
			'Invalid value provided to SecureStore. Values must be strings; consider JSON-encoding your values if they are serializable.'
		);
	}
	localStorage.setItem(getStorageKey(key), value);
}

export function setItem(
	key: string,
	value: string,
	_options: SecureStoreOptions = {}
): void {
	if (!isValidValue(value)) {
		throw new Error(
			'Invalid value provided to SecureStore. Values must be strings; consider JSON-encoding your values if they are serializable.'
		);
	}
	localStorage.setItem(getStorageKey(key), value);
}

export function getItem(
	key: string,
	_options: SecureStoreOptions = {}
): string | null {
	return localStorage.getItem(getStorageKey(key));
}

export function canUseBiometricAuthentication(): boolean {
	return false;
}
