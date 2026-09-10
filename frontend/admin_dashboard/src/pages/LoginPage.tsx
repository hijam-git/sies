import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth-context';
import { useT, LanguageToggle } from '../lib/i18n';
import { normalizeBdPhone, phoneInputValue } from '../lib/normalizeBdPhone';
import { errorTextForCode } from '../lib/apiErrors';

interface LocationState {
  from?: string;
}

/**
 * The only way in: **11-digit phone + password**.
 *
 * No email field, no Google button, no social sign-in — one phone, one account
 * (`CLAUDE.md` §1). Half the people who use this system have no email address
 * and all of them have a mobile number, which is why the phone is the identity
 * rather than a contact detail beside it.
 */
export default function LoginPage() {
  const { t } = useT();
  const { login, error, clearError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Live, so the person is told before they submit rather than after — but
  // only once they have typed enough for "too short" to be news.
  const phoneLooksWrong = phone.length === 11 && !normalizeBdPhone(phone);
  const canSubmit = !!normalizeBdPhone(phone) && password.length > 0 && !submitting;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    clearError();
    try {
      await login(phone, password);
      // Back to whatever they were trying to open — a student record shared as
      // a link still lands on that student after signing in.
      const from = (location.state as LocationState | null)?.from;
      navigate(from ?? '/', { replace: true });
    } catch {
      // The message is already in `error`, translated below. Nothing else to do
      // here, and rethrowing would only reach an error boundary.
    } finally {
      setSubmitting(false);
    }
  };

  const fieldCls =
    'w-full rounded-lg border border-gray-300 px-3 py-3 text-base text-gray-900 ' +
    'placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500';

  return (
    // min-h-dvh, not min-h-screen: on a phone `100vh` is the height WITHOUT the
    // browser's address bar, so the card sits partly under it until the user
    // scrolls.
    <div className="flex min-h-dvh flex-col bg-gray-50 px-4 py-8 sm:justify-center sm:py-12">
      <div className="mx-auto w-full max-w-md">
        <div className="mb-6 flex justify-center">
          <LanguageToggle />
        </div>

        <div className="text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 text-2xl font-extrabold tracking-tight text-white">
            S
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-gray-900">SIES</h1>
          <p className="mt-1 text-sm text-gray-600">{t('Smart Islamic Education System')}</p>
          <p className="mt-4 text-base font-medium text-gray-900">
            {t('Sign in to your institution')}
          </p>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-6 rounded-lg bg-red-50 p-4 text-sm font-medium text-red-800"
          >
            {errorTextForCode(error, t, t('Could not sign in. Please try again.'))}
          </div>
        )}

        <form className="mt-6 space-y-5" onSubmit={handleSubmit} noValidate>
          <div>
            <label htmlFor="phone" className="mb-1.5 block text-sm font-medium text-gray-700">
              {t('Mobile number')}
            </label>
            <input
              id="phone"
              name="phone"
              type="tel"
              // `numeric` rather than `tel`: the tel keypad offers +, * and #,
              // none of which belong in an 11-digit number, and its keys are
              // laid out differently from the number pad people know.
              inputMode="numeric"
              autoComplete="username"
              autoFocus
              maxLength={11}
              required
              value={phone}
              // Normalised on every keystroke — digits only, capped at 11 — so
              // a number pasted as +8801712345678 becomes typable rather than
              // being rejected on submit.
              onChange={(e) => setPhone(phoneInputValue(e.target.value))}
              onPaste={(e) => {
                // A paste of '+8801712345678' would otherwise lose its tail to
                // the 11-character cap. Canonicalise the whole thing first.
                const pasted = e.clipboardData.getData('text');
                const canonical = normalizeBdPhone(pasted);
                if (canonical) {
                  e.preventDefault();
                  setPhone(canonical);
                }
              }}
              placeholder="01712345678"
              aria-invalid={phoneLooksWrong}
              aria-describedby="phone-help"
              className={`${fieldCls} ${phoneLooksWrong ? 'border-red-400' : ''}`}
            />
            <p id="phone-help" className={`mt-1.5 text-xs ${phoneLooksWrong ? 'text-red-600' : 'text-gray-500'}`}>
              {phoneLooksWrong
                ? t('Enter an 11-digit mobile number, e.g. 01712345678.')
                : t('Enter the 11-digit number your institution registered.')}
            </p>
          </div>

          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-gray-700">
              {t('Password')}
            </label>
            <div className="relative">
              <input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={`${fieldCls} pr-14`}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? t('Hide password') : t('Show password')}
                className="tap absolute inset-y-0 right-0 text-gray-400 hover:text-gray-600"
              >
                {showPassword ? (
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M3 3l18 18" />
                  </svg>
                ) : (
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={!canSubmit}
            className="tap w-full rounded-lg bg-blue-600 px-4 text-base font-medium text-white transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? (
              <span className="flex items-center gap-3">
                <svg className="h-5 w-5 animate-spin text-white" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {t('Signing in...')}
              </span>
            ) : (
              t('Sign in')
            )}
          </button>

          {/* No "forgot password" flow, deliberately: resetting by SMS is V2,
              and until then the honest answer is the one an institution already
              uses for everything else — ask the office. */}
          <p className="text-center text-xs leading-relaxed text-gray-500">
            {t("Forgotten your password? Your institution's admin can set a new one for you.")}
          </p>
        </form>
      </div>
    </div>
  );
}
