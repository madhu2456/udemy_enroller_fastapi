/**
 * ⚠ ANYTHING PLATFORM — DO NOT REWRITE THIS FILE ⚠
 *
 * Shipped v2 mobile token-exchange endpoint. The mobile WebView intercepts
 * the redirect to this URL after signup/signin, fetches the JSON, and stores
 * { jwt, user } in SecureStore. The response shape ({ jwt, user: { id,
 * email, name } }) is the exact contract AuthWebView.tsx parses — changing
 * it breaks mobile auth platform-wide.
 */
import { auth } from '@/lib/auth';
import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  const session = await auth.api.getSession({ headers: request.headers });

  if (!session?.user || !session?.session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  return NextResponse.json({
    jwt: session.session.token,
    user: {
      id: session.user.id,
      email: session.user.email,
      name: session.user.name,
    },
  });
}
