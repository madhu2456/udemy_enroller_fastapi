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
        assert "window._loadGTM = gtm" in html

    def test_consent_default_denied_before_gtm_loader(self):
        """F012/F048: Consent Mode default denied precedes any GTM bootstrap."""
        html = self._render(gtm_container_id=GTM_ID)
        default_idx = html.find("gtag('consent','default'")
        update_idx = html.find("gtag('consent','update'")
        gtm_idx = html.find("googletagmanager.com/gtm.js")
        assert default_idx != -1
        assert update_idx != -1
        assert gtm_idx != -1
        assert default_idx < update_idx < gtm_idx
        assert "analytics_storage:'denied'" in html
        assert "ad_storage:'denied'" in html
        assert "ad_user_data:'denied'" in html
        assert "ad_personalization:'denied'" in html
        assert "wait_for_update:500" in html
        assert "window._loadGTM = gtm" in html
        assert "localStorage.getItem('cookie_consent') === 'accepted'" in html
        assert "if (window._loadGTM) window._loadGTM();" in html

    def test_accepted_restore_updates_consent_before_gtm(self):
        """Returning accepted visitors: consent update precedes gtm.js; default first."""
        html = self._render(gtm_container_id=GTM_ID)
        default_end = html.find("gtag('consent','default'")
        assert default_end != -1
        head_html = html[: html.find("googletagmanager.com/gtm.js")]
        restore_marker = (
            "if (localStorage.getItem('cookie_consent') === 'accepted') {\n"
            "                gtag('consent','update',{"
        )
        assert restore_marker in head_html
        restore_idx = html.find(restore_marker)
        gtm_idx = html.find("googletagmanager.com/gtm.js")
        assert default_end < restore_idx < gtm_idx
        assert "ad_storage:'granted'" not in html

    def test_consent_default_denied_before_ga4_loader(self):
        """F012/F048: Consent Mode default denied precedes the direct GA4 loader."""
        html = self._render(ga4_measurement_id=GA4_ID)
        default_idx = html.find("gtag('consent','default'")
        ga_idx = html.find("googletagmanager.com/gtag/js")
        assert default_idx != -1
        assert ga_idx != -1
        assert default_idx < ga_idx
        assert "analytics_storage:'denied'" in html
        assert "window._loadGA4 = loadGA4" in html

    def test_consent_update_granted_only_on_accept(self):
        """Accept updates Consent Mode to analytics granted, then loads GTM."""
        html = self._render(gtm_container_id=GTM_ID)
        update_idx = html.find("gtag('consent','update'")
        load_idx = html.find("if (window._loadGTM) window._loadGTM();")
        assert update_idx != -1
        assert load_idx != -1
        assert update_idx < load_idx
        assert "analytics_storage:'granted'" in html
        assert "ad_storage:'granted'" not in html
        assert "ad_user_data:'granted'" not in html
        assert "ad_personalization:'granted'" not in html

    def test_asset_version_bumps_present(self):
        """Self-hosted asset references carry ?v=2 (cache bust), icons fully bumped."""
        html = self._render()
        assert html.count("inter-latin.woff2?v=2") == 1
        assert html.count("inter.css?v=2") == 1
        # preload + favicon + apple-touch-icon + header logo + footer logo
        assert html.count("icon-512.webp?v=2") == 5
        # every icon reference is versioned (no unversioned stragglers)
        assert html.count("icon-512.webp") == 5
