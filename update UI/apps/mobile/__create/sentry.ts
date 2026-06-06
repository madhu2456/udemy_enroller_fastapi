import * as Sentry from "@sentry/react-native";
import { sendLogsToRemote } from "./report-error-to-remote";

function isActive(): boolean {
	return (
		!__DEV__ &&
		process.env.EXPO_PUBLIC_CREATE_ENV !== "DEVELOPMENT" &&
		!!process.env.EXPO_PUBLIC_SENTRY_DSN
	);
}

let initialized = false;

// Mirror a Sentry event into the Anything logs pipeline so native and JS
// crashes — including startup crashes that Sentry caches natively and reports
// on the next launch — surface in the Flux builder, not only the Sentry
// dashboard.
function forwardEventToRemote(event: Sentry.Event): void {
	try {
		const exception = event.exception?.values?.[0];
		const lines: string[] = [];
		if (exception && (exception.type || exception.value)) {
			lines.push(`${exception.type ?? "Error"}: ${exception.value ?? ""}`);
		} else if (typeof event.message === "string") {
			lines.push(event.message);
		}
		const frames = exception?.stacktrace?.frames;
		if (frames && frames.length > 0) {
			lines.push(
				frames
					.slice(-20)
					.reverse()
					.map(
						(frame) =>
							`  at ${frame.function ?? "?"} (${frame.filename ?? "?"}:${frame.lineno ?? 0})`,
					)
					.join("\n"),
			);
		}
		const message = lines.join("\n").trim();
		if (!message) return;
		const timestamp =
			typeof event.timestamp === "number"
				? new Date(event.timestamp * 1000).toISOString()
				: new Date().toISOString();
		sendLogsToRemote([
			{
				message: `[SENTRY] ${message}`,
				timestamp,
				level: "error",
				source: "TEST_FLIGHT",
			},
		]);
	} catch (_err) {
		// Silent
	}
}

export function initSentry(): void {
	try {
		if (!isActive() || initialized) return;
		initialized = true;
		Sentry.init({
			dsn: process.env.EXPO_PUBLIC_SENTRY_DSN,
			enableNativeCrashHandling: true,
			beforeSend: (event) => {
				forwardEventToRemote(event);
				return event;
			},
		});
		const projectGroupId = process.env.EXPO_PUBLIC_PROJECT_GROUP_ID;
		if (projectGroupId) {
			Sentry.setTag("projectGroupId", projectGroupId);
		}
	} catch (_err) {
		// Silent — Sentry must never crash the host app
	}
}
