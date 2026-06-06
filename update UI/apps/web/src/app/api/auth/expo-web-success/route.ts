/**
 * ⚠ ANYTHING PLATFORM — DO NOT REWRITE THIS FILE ⚠
 *
 * Shipped v2 Expo-web postMessage bridge. Renders an HTML page that posts
 * `{ type: 'AUTH_SUCCESS'|'AUTH_ERROR', jwt, user }` to window.parent —
 * AuthWebView.tsx listens for exactly that shape. Changing the event type or
 * payload shape breaks Expo-web auth; do NOT replace with a JSON response or
 * a redirect.
 */
import { auth } from '@/lib/auth';

// Renders an HTML page that posts the session token to the parent frame.
// AuthWebView on the mobile "web" platform listens for this postMessage to
// capture the session after a successful web signin/signup inside its iframe.
export async function GET(request: Request) {
  const session = await auth.api.getSession({ headers: request.headers });

  const payload =
    session?.user && session?.session
      ? {
          type: 'AUTH_SUCCESS',
          jwt: session.session.token,
          user: {
            id: session.user.id,
            email: session.user.email,
            name: session.user.name,
          },
        }
      : { type: 'AUTH_ERROR', error: 'Unauthorized' };

  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Signing in…</title>
</head>
<body>
<script>
(function () {
  var data = ${JSON.stringify(payload)};
  if (window.parent && window.parent !== window) {
    window.parent.postMessage(data, '*');
  }
})();
</script>
</body>
</html>`;

  return new Response(html, {
    status: 200,
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  });
}
