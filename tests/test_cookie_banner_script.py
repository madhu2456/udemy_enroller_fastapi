"""Cookie-banner inline-script contract in base.html (HTML-contract test).

The banner's keydown handler is plain JS that pytest cannot execute, so this
test pins the rendered HTML guards themselves: if the decline function, the
outside-click guard, the modal visibility guards, the hidden-class check, or
the capture-phase registration ever regress, this test fails.
"""

from fastapi.testclient import TestClient

from main import app

GTM_ID = "GTM-TEST123"
GA4_ID = "G-TEST1234"

_LOADER_KEYS = ("gtm_container_id", "ga4_measurement_id")


class TestCookieBannerScript:
    """Rendered banner HTML guards (JS is not executed under pytest)."""

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

    def test_banner_renders_when_analytics_configured(self):
        """Banner (and its inline script) render only with analytics IDs."""
        html = self._render(gtm_container_id=GTM_ID)
        assert 'id="cookie-banner"' in html
        assert "function declineCookies()" in html

    def test_no_analytics_no_banner_script(self):
        """Without analytics IDs the banner block is absent entirely."""
        html = self._render()
        assert 'id="cookie-banner"' not in html
        assert "declineCookies" not in html

    def test_decline_cookie_contract(self):
        """Decline writes the declined consent and hides the banner."""
        html = self._render(ga4_measurement_id=GA4_ID)
        assert "function declineCookies()" in html
        assert "localStorage.setItem('cookie_consent', 'declined')" in html
        assert "banner.classList.add('hidden')" in html

    def test_outside_click_guard(self):
        """Escape only dismisses when the keystroke originates in the banner."""
        html = self._render(gtm_container_id=GTM_ID)
        assert "e.target !== banner && !banner.contains(e.target)" in html

    def test_modal_visibility_guards(self):
        """Banner escape is suppressed while a11y-confirm/stats-modal is open."""
        html = self._render(ga4_measurement_id=GA4_ID)
        assert "!a11yRoot.classList.contains('hidden')" in html
        assert "!statsModal.classList.contains('hidden')" in html

    def test_hidden_class_check(self):
        """Escape handler no-ops while the banner itself is hidden."""
        html = self._render(gtm_container_id=GTM_ID)
        assert "banner.classList.contains('hidden')" in html

    def test_capture_listener_registration(self):
        """Keydown handler is registered on document in the capture phase."""
        html = self._render(ga4_measurement_id=GA4_ID)
        assert "document.addEventListener('keydown', onKeydown, true)" in html

    def test_measured_spacer_contract(self):
        """F043: open banner measures height onto body; hide clears it."""
        html = self._render(gtm_container_id=GTM_ID)
        assert "function applyCookieSpacer()" in html
        assert "getBoundingClientRect().height" in html
        assert "--cookie-banner-height" in html
        assert "cookie-banner-open" in html
        assert "aria-modal=\"false\"" in html
        assert "spacerObserver.disconnect()" in html

    def test_cookie_spacer_css_on_body_only(self):
        """R3: spacer padding applies to body, not also #main-content."""
        from pathlib import Path

        css = Path("app/static/css/site.css").read_text(encoding="utf-8")
        assert "body.cookie-banner-open" in css
        assert "body.cookie-banner-open #main-content" not in css

    def test_banner_does_not_trap_focus(self):
        """F043: cookie chrome is not a modal focus trap (Escape only)."""
        html = self._render(gtm_container_id=GTM_ID)
        start = html.index('id="cookie-banner"')
        end = html.index("<!-- Accessible confirm dialog", start)
        banner_js = html[start:end]
        assert "e.key === 'Escape'" in banner_js
        assert "e.key !== \"Tab\"" not in banner_js
        assert "e.key !== 'Tab'" not in banner_js
