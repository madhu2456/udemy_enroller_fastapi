"""GTM/GA4 analytics loaders and consent gating in base.html (Fix 4)."""

from fastapi.testclient import TestClient

from main import app

GTM_ID = "GTM-TEST123"
GA4_ID = "G-TEST1234"

_LOADER_KEYS = ("gtm_container_id", "ga4_measurement_id")


class TestAnalyticsConsent:
    """Rendered HTML behavior of the consent-gated analytics loaders."""

    def _render(self, gtm_container_id=None, ga4_measurement_id=None):
        """GET /faq with the given analytics state; restore app.state afterward.

        A bare TestClient does not run the lifespan handler, so the analytics
        IDs are injected straight into app.state (as the lifespan would) and
        any prior state is restored in the finally block.
        """
        state = app.state
        saved = {
            key: (hasattr(state, key), getattr(state, key, None))
            for key in _LOADER_KEYS
        }
        client = TestClient(app)
        try:
            state.gtm_container_id = gtm_container_id
            state.ga4_measurement_id = ga4_measurement_id
            response = client.get("/faq")
        finally:
            client.close()
            for key, (existed, old) in saved.items():
                if existed:
                    setattr(state, key, old)
                else:
                    try:
                        delattr(state, key)
                    except (KeyError, AttributeError):
                        pass
        assert response.status_code == 200
        return response.text

    def test_gtm_only_no_noscript_iframe(self):
        """GTM set: loader present, but the noscript iframe is gone."""
        html = self._render(gtm_container_id=GTM_ID)
        assert "ns.html" not in html
        assert "gtm-noscript" not in html
        assert html.count("googletagmanager.com/gtm.js") == 1
        assert html.count("googletagmanager.com/gtag/js") == 0

    def test_both_ids_gtm_wins_no_direct_ga4_loader(self):
        """Both IDs set: GTM loader only; direct GA4 loader is suppressed."""
        html = self._render(gtm_container_id=GTM_ID, ga4_measurement_id=GA4_ID)
        assert html.count("googletagmanager.com/gtm.js") == 1
        assert html.count("googletagmanager.com/gtag/js") == 0

    def test_ga4_only_direct_loader_no_gtm(self):
        """GA4 only: exactly one direct gtag/js loader and no GTM loader."""
        html = self._render(ga4_measurement_id=GA4_ID)
        assert html.count("googletagmanager.com/gtag/js") == 1
        assert html.count("googletagmanager.com/gtm.js") == 0
        assert GA4_ID in html

    def test_no_ids_no_tracker_references(self):
        """Neither ID set: zero googletagmanager references in the HTML."""
        html = self._render()
        assert "googletagmanager.com" not in html

    def test_consent_gating_intact_when_trackers_configured(self):
        """Loaders stay gated behind localStorage cookie_consent === 'accepted'."""
        html = self._render(gtm_container_id=GTM_ID)
        assert "localStorage.getItem('cookie_consent') === 'accepted'" in html

    def test_asset_version_bumps_present(self):
        """Self-hosted asset references carry ?v=2 (cache bust), icons fully bumped."""
        html = self._render()
        assert html.count("inter-latin.woff2?v=2") == 1
        assert html.count("inter.css?v=2") == 1
        # preload + favicon + apple-touch-icon + header logo + footer logo
        assert html.count("icon-512.webp?v=2") == 5
        # every icon reference is versioned (no unversioned stragglers)
        assert html.count("icon-512.webp") == 5
