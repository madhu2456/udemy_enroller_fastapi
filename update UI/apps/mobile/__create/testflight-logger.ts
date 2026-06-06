import AsyncStorage from "@react-native-async-storage/async-storage";
import { File, Paths } from "expo-file-system";
import { AppState, type AppStateStatus } from "react-native";
import { sendLogsToRemote } from "./report-error-to-remote";

const STORAGE_KEY = "testflight_logger_pending_logs";
// Written synchronously from the crash handlers so logs survive a startup
// crash that tears down the JS runtime before the async network / AsyncStorage
// paths can finish. Shipped and cleared on the next launch.
const CRASH_FILE_NAME = "testflight_crash_logs.json";
const MAX_STORED_ENTRIES = 200;
const MAX_BUFFER_SIZE = 50;
const FLUSH_INTERVAL_MS = 5_000;

interface LogEntry {
	message: string;
	timestamp: string;
	level: "log" | "info" | "warn" | "error" | "debug";
	source: "TEST_FLIGHT";
	sessionId: string;
}

function isActive(): boolean {
	return !__DEV__ && process.env.EXPO_PUBLIC_CREATE_ENV !== "DEVELOPMENT";
}

function generateSessionId(): string {
	return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

let instance: TestFlightLogger | null = null;

class TestFlightLogger {
	private buffer: LogEntry[] = [];
	// Entries spliced out of `buffer` by an in-flight `flush()` that hasn't
	// confirmed delivery yet. Tracked so a crash mid-flush can still snapshot
	// them — `buffer` alone would miss them.
	private inFlightBatch: LogEntry[] = [];
	private sessionId: string;
	private flushTimer: ReturnType<typeof setInterval> | null = null;
	private originalConsole: Record<string, (...args: unknown[]) => void> = {};
	private isFlushing = false;

	constructor() {
		this.sessionId = generateSessionId();
	}

	async start(): Promise<void> {
		try {
			await this.restorePersistedLogs();
			this.patchConsole();
			this.hookUncaughtExceptions();
			this.hookUnhandledRejections();
			this.hookAppState();
			this.flushTimer = setInterval(() => {
				this.flush();
			}, FLUSH_INTERVAL_MS);
		} catch (_err) {
			// Silent — the logger must never crash the host app
		}
	}

	logError(message: string): void {
		try {
			this.addEntry("error", message);
			this.flush();
		} catch (_err) {
			// Silent
		}
	}

	private addEntry(level: LogEntry["level"], message: string): void {
		this.buffer.push({
			message,
			timestamp: new Date().toISOString(),
			level,
			source: "TEST_FLIGHT",
			sessionId: this.sessionId,
		});
		if (this.buffer.length >= MAX_BUFFER_SIZE) {
			this.flush();
		}
	}

	private patchConsole(): void {
		const levels = ["log", "info", "warn", "error", "debug"] as const;
		for (const level of levels) {
			this.originalConsole[level] = console[level].bind(console);
			console[level] = (...args: unknown[]) => {
				try {
					const message = args
						.map((arg) => {
							if (typeof arg === "string") return arg;
							try {
								return JSON.stringify(arg);
							} catch {
								return String(arg);
							}
						})
						.join(" ");
					this.addEntry(level, message);
				} catch (_err) {
					// Silent
				}
				this.originalConsole[level]?.(...args);
			};
		}
	}

	private hookUncaughtExceptions(): void {
		const ErrorUtils = (globalThis as Record<string, unknown>).ErrorUtils as
			| {
					getGlobalHandler: () => (error: Error, isFatal?: boolean) => void;
					setGlobalHandler: (
						handler: (error: Error, isFatal?: boolean) => void,
					) => void;
			  }
			| undefined;

		if (!ErrorUtils) return;

		const previousHandler = ErrorUtils.getGlobalHandler();
		ErrorUtils.setGlobalHandler((error: Error, isFatal?: boolean) => {
			try {
				const tag = isFatal ? "[FATAL]" : "[UNCAUGHT]";
				this.addEntry("error", `${tag} ${error.message}\n${error.stack ?? ""}`);
				// Only a fatal error tears down the runtime before the async
				// flush can finish, so only then is the synchronous crash-file
				// snapshot needed. Non-fatal errors are delivered by flush /
				// AsyncStorage retry; snapshotting them would just duplicate
				// entries on the next launch.
				if (isFatal) {
					this.persistBufferSync();
				}
				this.flush();
			} catch (_err) {
				// Silent
			}
			previousHandler(error, isFatal);
		});
	}

	private hookUnhandledRejections(): void {
		const previous: ((event: PromiseRejectionEvent) => void) | null =
			globalThis.onunhandledrejection;
		globalThis.onunhandledrejection = (event: PromiseRejectionEvent) => {
			try {
				const reason =
					event.reason instanceof Error
						? `${event.reason.message}\n${event.reason.stack ?? ""}`
						: String(event.reason);
				this.addEntry("error", `[UNHANDLED_REJECTION] ${reason}`);
				this.flush();
			} catch (_err) {
				// Silent
			}
			if (previous) {
				previous(event);
			}
		};
	}

	private hookAppState(): void {
		AppState.addEventListener("change", (state: AppStateStatus) => {
			try {
				this.addEntry("info", `[APP_STATE] ${state}`);
				if (state === "background" || state === "inactive") {
					this.flush();
				}
			} catch (_err) {
				// Silent
			}
		});
	}

	private async flush(): Promise<void> {
		if (this.isFlushing || this.buffer.length === 0) return;
		this.isFlushing = true;
		const batch = this.buffer.splice(0);
		this.inFlightBatch = batch;
		try {
			const result = await sendLogsToRemote(batch);
			if (!result.success) {
				await this.persistLogs(batch);
			}
		} catch (_err) {
			await this.persistLogs(batch);
		} finally {
			this.inFlightBatch = [];
			this.isFlushing = false;
		}
	}

	private async persistLogs(logs: LogEntry[]): Promise<void> {
		try {
			const raw = await AsyncStorage.getItem(STORAGE_KEY);
			const existing: LogEntry[] = raw ? JSON.parse(raw) : [];
			const merged = [...existing, ...logs].slice(-MAX_STORED_ENTRIES);
			await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
		} catch (_err) {
			// Silent
		}
	}

	// Synchronously snapshot pending logs to disk. Called from the crash
	// handlers before the runtime is torn down, so a startup crash is still
	// recoverable on the next launch. Includes any in-flight flush batch,
	// since `addEntry`'s auto-flush may have already emptied `buffer`.
	private persistBufferSync(): void {
		try {
			const pending = [...this.inFlightBatch, ...this.buffer];
			if (pending.length === 0) return;
			const merged = [...this.readCrashLogsSync(), ...pending].slice(
				-MAX_STORED_ENTRIES,
			);
			const file = new File(Paths.document, CRASH_FILE_NAME);
			if (file.exists) {
				file.delete();
			}
			file.create();
			file.write(JSON.stringify(merged));
		} catch (_err) {
			// Silent — the logger must never crash the host app
		}
	}

	private readCrashLogsSync(): LogEntry[] {
		try {
			const file = new File(Paths.document, CRASH_FILE_NAME);
			if (!file.exists) return [];
			const parsed: unknown = JSON.parse(file.textSync());
			return Array.isArray(parsed) ? (parsed as LogEntry[]) : [];
		} catch (_err) {
			return [];
		}
	}

	private clearCrashFileSync(): void {
		try {
			const file = new File(Paths.document, CRASH_FILE_NAME);
			if (file.exists) {
				file.delete();
			}
		} catch (_err) {
			// Silent
		}
	}

	private async restorePersistedLogs(): Promise<void> {
		try {
			const crashLogs = this.readCrashLogsSync();
			if (crashLogs.length > 0) {
				this.clearCrashFileSync();
			}
			const raw = await AsyncStorage.getItem(STORAGE_KEY);
			if (raw) {
				await AsyncStorage.removeItem(STORAGE_KEY);
			}
			const storedLogs: LogEntry[] = raw ? JSON.parse(raw) : [];
			const logs = [...crashLogs, ...storedLogs];
			if (logs.length === 0) return;
			const result = await sendLogsToRemote(logs);
			if (!result.success) {
				await this.persistLogs(logs);
			}
		} catch (_err) {
			// Silent
		}
	}
}

export function initTestFlightLogger(): void {
	try {
		if (!isActive()) return;
		if (instance) return;
		instance = new TestFlightLogger();
		instance.start();
	} catch (_err) {
		// Silent
	}
}

export function getTestFlightLogger(): {
	logError: (message: string) => void;
} | null {
	try {
		if (!isActive()) return null;
		return instance;
	} catch (_err) {
		return null;
	}
}
