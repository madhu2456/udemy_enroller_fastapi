jest.mock("serialize-error", () => ({
	serializeError: jest.fn((err) => ({
		message: err instanceof Error ? err.message : String(err),
		name: err instanceof Error ? err.name : "Error",
	})),
}));

let sendLogsToRemote;
let reportErrorToRemote;

beforeEach(() => {
	jest.resetAllMocks();
	jest.resetModules();
	delete process.env.EXPO_PUBLIC_LOGS_ENDPOINT;
	delete process.env.EXPO_PUBLIC_PROJECT_GROUP_ID;
	delete process.env.EXPO_PUBLIC_CREATE_TEMP_API_KEY;
	delete process.env.EXPO_PUBLIC_DEV_SERVER_ID;
	global.fetch = jest.fn();

	// Re-require after mocks are set up
	jest.doMock("serialize-error", () => ({
		serializeError: jest.fn((err) => ({
			message: err instanceof Error ? err.message : String(err),
			name: err instanceof Error ? err.name : "Error",
		})),
	}));
	const mod = require("./report-error-to-remote");
	sendLogsToRemote = mod.sendLogsToRemote;
	reportErrorToRemote = mod.reportErrorToRemote;
});

describe("sendLogsToRemote", () => {
	it("returns success: false when env vars are missing", async () => {
		const result = await sendLogsToRemote([{ message: "test" }]);
		expect(result).toEqual({ success: false });
		expect(global.fetch).not.toHaveBeenCalled();
	});

	it("sends logs to the endpoint with correct auth header", async () => {
		process.env.EXPO_PUBLIC_LOGS_ENDPOINT = "https://logs.test/ingest";
		process.env.EXPO_PUBLIC_PROJECT_GROUP_ID = "pg-123";
		process.env.EXPO_PUBLIC_CREATE_TEMP_API_KEY = "key-abc";

		global.fetch = jest.fn().mockResolvedValue({ ok: true });

		const logs = [
			{ message: "hello", level: "info", timestamp: "2026-01-01T00:00:00Z" },
		];
		const result = await sendLogsToRemote(logs);

		expect(result).toEqual({ success: true });
		expect(global.fetch).toHaveBeenCalledWith("https://logs.test/ingest", {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Authorization: "Bearer key-abc",
			},
			body: JSON.stringify({ projectGroupId: "pg-123", logs }),
		});
	});

	it("returns success: false on non-ok response", async () => {
		process.env.EXPO_PUBLIC_LOGS_ENDPOINT = "https://logs.test/ingest";
		process.env.EXPO_PUBLIC_PROJECT_GROUP_ID = "pg-123";
		process.env.EXPO_PUBLIC_CREATE_TEMP_API_KEY = "key-abc";

		global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 });

		const result = await sendLogsToRemote([{ message: "fail" }]);
		expect(result).toEqual({ success: false });
	});

	it("returns success: false with error on network failure", async () => {
		process.env.EXPO_PUBLIC_LOGS_ENDPOINT = "https://logs.test/ingest";
		process.env.EXPO_PUBLIC_PROJECT_GROUP_ID = "pg-123";
		process.env.EXPO_PUBLIC_CREATE_TEMP_API_KEY = "key-abc";

		const networkError = new Error("Network request failed");
		global.fetch = jest.fn().mockRejectedValue(networkError);

		const result = await sendLogsToRemote([{ message: "fail" }]);
		expect(result).toEqual({ success: false, error: networkError });
	});
});

describe("reportErrorToRemote", () => {
	it("returns success: false when env vars are missing", async () => {
		const result = await reportErrorToRemote({
			error: new Error("test error"),
		});
		expect(result).toEqual({ success: false });
		expect(global.fetch).not.toHaveBeenCalled();
	});

	it("serializes error and sends as a single log entry with source BUILDER", async () => {
		process.env.EXPO_PUBLIC_LOGS_ENDPOINT = "https://logs.test/ingest";
		process.env.EXPO_PUBLIC_PROJECT_GROUP_ID = "pg-123";
		process.env.EXPO_PUBLIC_CREATE_TEMP_API_KEY = "key-abc";
		process.env.EXPO_PUBLIC_DEV_SERVER_ID = "ds-456";

		global.fetch = jest.fn().mockResolvedValue({ ok: true });

		const error = new Error("something broke");
		await reportErrorToRemote({ error });

		expect(global.fetch).toHaveBeenCalledTimes(1);
		const body = JSON.parse(global.fetch.mock.calls[0][1].body);
		expect(body.projectGroupId).toBe("pg-123");
		expect(body.logs).toHaveLength(1);
		expect(body.logs[0].level).toBe("error");
		expect(body.logs[0].source).toBe("BUILDER");
		expect(body.logs[0].devServerId).toBe("ds-456");
		expect(body.logs[0].message).toContain("something broke");
	});
});
