"""Validate committed performance baseline artifact (BACKLOG-011)."""

import json
from pathlib import Path

BASELINE_PATH = Path(__file__).with_name("performance-baseline.json")
REQUIRED_ROUTES = {
    "/",
    "/udemycoupons",
    "/faq",
    "/about",
    "/guides",
    "/privacy",
}
REQUIRED_VIEWPORTS = {"mobile", "desktop"}
REQUIRED_METRICS = {
    "ttfb_ms",
    "fcp_ms",
    "lcp_ms",
    "cls",
    "dom_content_loaded_ms",
    "load_ms",
    "request_count",
    "transfer_bytes",
}


class TestPerformanceBaselineArtifact:
    def test_baseline_file_exists(self):
        assert BASELINE_PATH.exists(), (
            "Run `npm run audit:performance:baseline` to generate "
            "tests/performance-baseline.json"
        )

    def test_baseline_schema(self):
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

        assert data["base_url"]
        assert data["tool_version"]
        assert isinstance(data["routes"], list)
        assert len(data["routes"]) == len(REQUIRED_ROUTES)

        paths = {route["path"] for route in data["routes"]}
        assert paths == REQUIRED_ROUTES

        for route in data["routes"]:
            viewport_names = {viewport["name"] for viewport in route["viewports"]}
            assert viewport_names == REQUIRED_VIEWPORTS

            for viewport in route["viewports"]:
                assert REQUIRED_METRICS.issubset(viewport["metrics"].keys())
                assert viewport["metrics"]["request_count"] >= 0
                assert viewport["metrics"]["transfer_bytes"] >= 0
                assert "ratings" in viewport or "metrics" in viewport