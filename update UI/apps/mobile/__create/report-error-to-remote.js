import { serializeError } from "serialize-error";

export const sendLogsToRemote = async (logs) => {
	if (
		!process.env.EXPO_PUBLIC_LOGS_ENDPOINT ||
		!process.env.EXPO_PUBLIC_PROJECT_GROUP_ID ||
		!process.env.EXPO_PUBLIC_CREATE_TEMP_API_KEY
	) {
		return { success: false };
	}
	try {
		const response = await fetch(process.env.EXPO_PUBLIC_LOGS_ENDPOINT, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Authorization: `Bearer ${process.env.EXPO_PUBLIC_CREATE_TEMP_API_KEY}`,
			},
			body: JSON.stringify({
				projectGroupId: process.env.EXPO_PUBLIC_PROJECT_GROUP_ID,
				logs,
			}),
		});
		if (!response.ok) {
			return { success: false };
		}
	} catch (fetchError) {
		return { success: false, error: fetchError };
	}
	return { success: true };
};

export const reportErrorToRemote = async ({ error }) => {
	if (
		!process.env.EXPO_PUBLIC_LOGS_ENDPOINT ||
		!process.env.EXPO_PUBLIC_PROJECT_GROUP_ID ||
		!process.env.EXPO_PUBLIC_CREATE_TEMP_API_KEY
	) {
		console.debug(
			"reportErrorToRemote: Missing environment variables for logging endpoint, project group ID, or API key.",
			error,
		);
		return { success: false };
	}
	return sendLogsToRemote([
		{
			message: JSON.stringify(serializeError(error)),
			timestamp: new Date().toISOString(),
			level: "error",
			source: "BUILDER",
			devServerId: process.env.EXPO_PUBLIC_DEV_SERVER_ID,
		},
	]);
};
