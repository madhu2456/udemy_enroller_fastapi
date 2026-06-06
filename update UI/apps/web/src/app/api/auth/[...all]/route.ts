/**
 * ⚠ ANYTHING PLATFORM — DO NOT REWRITE THIS FILE ⚠
 *
 * Shipped v2 better-auth catch-all. `toNextJsHandler(auth)` wires up every
 * better-auth endpoint (/sign-up/email, /sign-in/email, /get-session, ...).
 * Do not hand-roll your own routes for these paths; it will conflict with
 * this handler and break signup/signin/session lookup.
 */
import { auth } from "@/lib/auth";
import { toNextJsHandler } from "better-auth/next-js";

export const { GET, POST } = toNextJsHandler(auth);
