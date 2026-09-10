import { ApiError } from './api';

/**
 * Turning the API's error code into a sentence somebody can act on.
 *
 * The backend answers with `{success, message, errors, code}` (`lib/api.ts`).
 * The **code** is what we translate; the **message** is the fallback for a code
 * added on the server before a line was added here, so a new one is never a
 * blank screen — it is English until somebody translates it.
 *
 * The English sentences below are dictionary KEYS, so the Bangla lives in
 * `lib/i18n/dict/errors.ts` with every other string rather than in two places.
 */
export const API_ERROR_MESSAGES: Record<string, string> = {
  // ── Login ──────────────────────────────────────────────────────────────
  invalid_phone: 'Enter an 11-digit mobile number, e.g. 01712345678.',
  // Deliberately does not say WHICH was wrong. Telling a stranger that the
  // phone exists but the password does not is telling them half the answer.
  invalid_credentials: 'This phone number and password do not match an account.',
  account_inactive: 'This account has been switched off. Ask your institution\'s admin.',
  login_failed: 'Could not sign in. Please try again.',

  // ── Access ─────────────────────────────────────────────────────────────
  permission_denied: 'You do not have permission to do this.',
  // A wrong-branch object answers 404, not 403 — 403 would confirm it exists
  // (`CLAUDE.md` §5). So "not found" here genuinely covers both.
  not_found: 'That record does not exist, or it belongs to another institution.',
  out_of_scope: 'This class is not one of yours. Ask the admin to assign it to you.',

  // ── Money ──────────────────────────────────────────────────────────────
  fee_already_paid: 'This fee has already been collected in full.',
  payment_exceeds_due: 'That is more than is outstanding on this fee.',
  receipt_already_reversed: 'This receipt has already been reversed.',

  // ── Attendance and marks ───────────────────────────────────────────────
  attendance_window_closed:
    'The time for taking this period\'s attendance has passed. A class teacher or the principal can still fill it in.',
  results_published: 'Results for this exam are published, so marks can no longer be changed.',

  // ── Setup ──────────────────────────────────────────────────────────────
  duplicate: 'Something with this name or number already exists.',
  protected_reference:
    'Other records point at this one, so it cannot be deleted. Switch it off instead.',
};

/** The stable code, or null when the failure was not an API error at all. */
export function apiErrorCode(err: unknown): string | null {
  return err instanceof ApiError ? err.code : null;
}

/**
 * Field-level validation, ready to hang under the inputs that caused it.
 * `{ phone: "This number already has an account." }`.
 */
export function apiFieldErrors(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || !err.errors) return {};
  return Object.fromEntries(
    Object.entries(err.errors).map(([field, messages]) => [field, messages.join(' ')]),
  );
}

/**
 * The sentence to show. `t` is the caller's translator, so the Bangla comes
 * from the dictionary like every other string.
 *
 * Order matters: a code we have written for beats the server's own English,
 * which beats a generic apology. The last is only reached when the request
 * never got an answer at all.
 */
export function apiErrorText(err: unknown, t: (s: string) => string, fallback: string): string {
  const code = apiErrorCode(err);
  if (code && API_ERROR_MESSAGES[code]) return t(API_ERROR_MESSAGES[code]);
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

/** The same, for a code held on its own — what `auth-context` stores in
 *  `error` so the login screen can translate it rather than show a raw one. */
export function errorTextForCode(
  code: string | null,
  t: (s: string) => string,
  fallback: string,
): string {
  if (code && API_ERROR_MESSAGES[code]) return t(API_ERROR_MESSAGES[code]);
  return fallback;
}
