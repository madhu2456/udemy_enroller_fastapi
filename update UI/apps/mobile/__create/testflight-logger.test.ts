let mockSendLogsToRemote: jest.Mock;
let mockGetItem: jest.Mock;
let mockSetItem: jest.Mock;
let mockRemoveItem: jest.Mock;
let mockFileStore: Record<string, string>;
let capturedErrorHandler: ((error: Error, isFatal?: boolean) => void) | null;
let originalErrorUtils: unknown;

const CRASH_FILE = "/doc/testflight_crash_logs.json";

const STORAGE_KEY = "testflight_logger_pending_logs";
let originalDev: boolean;

function setDevMode(value: boolean) {
	(globalThis as Record<string, unknown>).__DEV__ = value;
}

beforeEach(() => {
	originalDev = (globalThis as Record<string, unknown>).__DEV__ as boolean;
	jest.resetModules();
	jest.useFakeTimers();
	process.env.EXPO_PUBLIC_CREATE_ENV = "PRODUCTION";

	mockSendLogsToRemote = jest.fn().mockResolvedValue({ success: true });
	mockGetItem = jest.fn().mockResolvedValue(null);
	mockSetItem = jest.fn().mockResolvedValue(undefined);
	mockRemoveItem = jest.fn().mockResolvedValue(undefined);
	mockFileStore = {};

	capturedErrorHandler = null;
	originalErrorUtils = (globalThis as Record<string, unknown>).ErrorUtils;
	(globalThis as Record<string, unknown>).ErrorUtils = {
		getGlobalHandler: () => () => {},
		setGlobalHandler: (handler: (error: Error, isFatal?: boolean) => void) => {
			capturedErrorHandler = handler;
		},
	};

	jest.doMock("./report-error-to-remote", () => ({
		sendLogsToRemote: mockSendLogsToRemote,
	}));

	jest.doMock("@react-native-async-storage/async-storage", () => ({
		getItem: mockGetItem,
		setItem: mockSetItem,
		removeItem: mockRemoveItem,
	}));

	jest.doMock("expo-file-system", () => {
		class MockFile {
			uri: string;
			constructor(directory: string, name: string) {
				this.uri = `${directory}/${name}`;
			}
			get exists() {
				return Object.prototype.hasOwnProperty.call(mockFileStore, this.uri);
			}
			create() {
				if (!(this.uri in mockFileStore)) mockFileStore[this.uri] = "";
			}
			delete() {
				delete mockFileStore[this.uri];
			}
			write(content: string) {
				mockFileStore[this.uri] = content;
			}
			textSync() {
				return mockFileStore[this.uri] ?? "";
			}
		}
		return { File: MockFile, Paths: { document: "/doc" } };
	});
});

afterEach(() => {
	jest.useRealTimers();
	setDevMode(originalDev);
	delete process.env.EXPO_PUBLIC_CREATE_ENV;
	(globalThis as Record<string, unknown>).ErrorUtils = originalErrorUtils;
});

function loadModule() {
	return require("./testflight-logger") as typeof import("./testflight-logger");
}

describe("initTestFlightLogger", () => {
	it("is a no-op when __DEV__ is true", async () => {
		setDevMode(true);
		const { initTestFlightLogger, getTestFlightLogger } = loadModule();

		initTestFlightLogger();

		expect(getTestFlightLogger()).toBeNull();
		expect(mockSendLogsToRemote).not.toHaveBeenCalled();
	});

	it("is a no-op when EXPO_PUBLIC_CREATE_ENV is DEVELOPMENT", async () => {
		setDevMode(false);
		process.env.EXPO_PUBLIC_CREATE_ENV = "DEVELOPMENT";
		const { initTestFlightLogger, getTestFlightLogger } = loadModule();

		initTestFlightLogger();

		expect(getTestFlightLogger()).toBeNull();
	});

	it("activates when not in dev mode", async () => {
		setDevMode(false);
		const { initTestFlightLogger, getTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		const logger = getTestFlightLogger();
		expect(logger).not.toBeNull();
		expect(logger).toHaveProperty("logError");
	});

	it("only creates one instance on multiple calls", async () => {
		setDevMode(false);
		const { initTestFlightLogger, getTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);
		const first = getTestFlightLogger();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);
		const second = getTestFlightLogger();

		expect(first).toBe(second);
	});
});

describe("console patching", () => {
	it("intercepts console.log and buffers the message", async () => {
		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		console.log("test message");

		await jest.advanceTimersByTimeAsync(5_000);

		expect(mockSendLogsToRemote).toHaveBeenCalled();
		const logs = mockSendLogsToRemote.mock.calls[0][0];
		const logMessage = logs.find(
			(l: Record<string, string>) => l.message === "test message",
		);
		expect(logMessage).toBeDefined();
		expect(logMessage.level).toBe("log");
		expect(logMessage.source).toBe("TEST_FLIGHT");
	});

	it("intercepts console.error", async () => {
		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		console.error("bad thing");

		await jest.advanceTimersByTimeAsync(5_000);

		expect(mockSendLogsToRemote).toHaveBeenCalled();
		const logs = mockSendLogsToRemote.mock.calls[0][0];
		const errorLog = logs.find(
			(l: Record<string, string>) => l.message === "bad thing",
		);
		expect(errorLog).toBeDefined();
		expect(errorLog.level).toBe("error");
	});

	it("serializes non-string arguments as JSON", async () => {
		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		console.log("count:", { x: 1 });

		await jest.advanceTimersByTimeAsync(5_000);

		const logs = mockSendLogsToRemote.mock.calls[0][0];
		const entry = logs.find((l: Record<string, string>) =>
			l.message.includes("count:"),
		);
		expect(entry.message).toBe('count: {"x":1}');
	});
});

describe("logError", () => {
	it("immediately flushes error entries", async () => {
		setDevMode(false);
		const { initTestFlightLogger, getTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		const logger = getTestFlightLogger()!;
		logger.logError("critical failure");

		// Should flush without waiting for the 5s interval
		await jest.advanceTimersByTimeAsync(0);

		expect(mockSendLogsToRemote).toHaveBeenCalled();
		const logs = mockSendLogsToRemote.mock.calls[0][0];
		expect(logs[0].message).toBe("critical failure");
		expect(logs[0].level).toBe("error");
	});
});

describe("buffering and flushing", () => {
	it("flushes buffer every 5 seconds", async () => {
		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		console.log("entry 1");

		// Not flushed yet at 3 seconds
		await jest.advanceTimersByTimeAsync(3_000);
		expect(mockSendLogsToRemote).not.toHaveBeenCalled();

		// Flushed at 5 seconds
		await jest.advanceTimersByTimeAsync(2_000);
		expect(mockSendLogsToRemote).toHaveBeenCalledTimes(1);
	});

	it("auto-flushes when buffer reaches 50 entries", async () => {
		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		for (let i = 0; i < 50; i++) {
			console.log(`entry ${i}`);
		}

		await jest.advanceTimersByTimeAsync(0);
		expect(mockSendLogsToRemote).toHaveBeenCalled();
	});
});

describe("persistence and retry", () => {
	it("persists logs to AsyncStorage when flush fails", async () => {
		mockSendLogsToRemote.mockResolvedValue({ success: false });
		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		console.log("will fail");

		await jest.advanceTimersByTimeAsync(5_000);

		expect(mockSetItem).toHaveBeenCalledWith(
			STORAGE_KEY,
			expect.stringContaining("will fail"),
		);
	});

	it("restores persisted logs on startup and re-sends them", async () => {
		const persistedLogs = [
			{
				message: "old log",
				timestamp: "2026-01-01T00:00:00Z",
				level: "error",
				source: "TEST_FLIGHT",
				sessionId: "old-session",
			},
		];
		mockGetItem.mockResolvedValueOnce(JSON.stringify(persistedLogs));

		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		expect(mockRemoveItem).toHaveBeenCalledWith(STORAGE_KEY);
		expect(mockSendLogsToRemote).toHaveBeenCalledWith(persistedLogs);
	});

	it("re-persists restored logs if resend also fails", async () => {
		const persistedLogs = [
			{
				message: "stubborn log",
				timestamp: "2026-01-01T00:00:00Z",
				level: "error",
				source: "TEST_FLIGHT",
				sessionId: "old-session",
			},
		];
		mockGetItem
			.mockResolvedValueOnce(JSON.stringify(persistedLogs))
			.mockResolvedValueOnce(null);

		mockSendLogsToRemote.mockResolvedValueOnce({ success: false });

		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		expect(mockSetItem).toHaveBeenCalledWith(
			STORAGE_KEY,
			expect.stringContaining("stubborn log"),
		);
	});

	it("caps persisted entries at 200", async () => {
		const existingLogs = Array.from({ length: 195 }, (_, i) => ({
			message: `existing ${i}`,
			timestamp: "2026-01-01T00:00:00Z",
			level: "log",
			source: "TEST_FLIGHT",
			sessionId: "s",
		}));

		mockSendLogsToRemote.mockResolvedValue({ success: false });
		mockGetItem
			.mockResolvedValueOnce(null)
			.mockResolvedValueOnce(JSON.stringify(existingLogs));

		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		for (let i = 0; i < 10; i++) {
			console.log(`new ${i}`);
		}

		await jest.advanceTimersByTimeAsync(5_000);

		const setItemCalls = mockSetItem.mock.calls;
		const lastCall = setItemCalls[setItemCalls.length - 1];
		const saved = JSON.parse(lastCall[1]);
		expect(saved.length).toBeLessThanOrEqual(200);
	});
});

describe("crash persistence", () => {
	it("synchronously snapshots the buffer to the crash file on a fatal error", async () => {
		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		console.log("breadcrumb before crash");
		capturedErrorHandler!(new Error("startup boom"), true);

		const crashFile = mockFileStore[CRASH_FILE];
		expect(crashFile).toContain("startup boom");
		expect(crashFile).toContain("breadcrumb before crash");
	});

	it("does not snapshot the crash file for a non-fatal error", async () => {
		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		capturedErrorHandler!(new Error("recoverable"), false);

		expect(mockFileStore[CRASH_FILE]).toBeUndefined();
	});

	it("captures the in-flight batch when a fatal error triggers auto-flush", async () => {
		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		// One short of the auto-flush threshold; the fatal error is the 50th
		// entry, so addEntry's auto-flush empties `buffer` before
		// persistBufferSync runs.
		for (let i = 0; i < 49; i++) {
			console.log(`entry ${i}`);
		}
		capturedErrorHandler!(new Error("boundary crash"), true);

		const crashFile = mockFileStore[CRASH_FILE];
		expect(crashFile).toContain("boundary crash");
		expect(crashFile).toContain("entry 0");
	});

	it("ships crash-file logs on the next startup and clears the file", async () => {
		mockFileStore[CRASH_FILE] = JSON.stringify([
			{
				message: "[FATAL] crashed last run",
				timestamp: "2026-01-01T00:00:00Z",
				level: "error",
				source: "TEST_FLIGHT",
				sessionId: "prev",
			},
		]);
		setDevMode(false);
		const { initTestFlightLogger } = loadModule();

		initTestFlightLogger();
		await jest.advanceTimersByTimeAsync(0);

		expect(mockSendLogsToRemote).toHaveBeenCalled();
		const sent = mockSendLogsToRemote.mock.calls[0][0];
		expect(
			sent.some(
				(entry: Record<string, string>) =>
					entry.message === "[FATAL] crashed last run",
			),
		).toBe(true);
		expect(mockFileStore[CRASH_FILE]).toBeUndefined();
	});
});
