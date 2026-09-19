import { useState } from 'react';
import type { FormEvent } from 'react';
import { apiClient } from '../../lib/api';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import { useAuth } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import BaseModal from '../common/BaseModal';
import Field, { FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls } from '../common/styles';

/**
 * Changing your own password — and, when the account was created for you, the
 * screen you cannot get past until you do.
 *
 * Every account an admin creates arrives with `must_change_password` set,
 * because the password was said out loud in order to hand it over. That flag
 * had nothing behind it: the API's change-password endpoint existed with no
 * caller anywhere in the SPA, and no screen offered it, so every temporary
 * password stayed live for as long as the account did.
 *
 * `forced` is the difference between the two uses. Forced, there is no cancel
 * and no backdrop dismissal — the staff member is standing at the counter with
 * a password a colleague knows, and "later" is how it stays that way.
 */
export default function ChangePasswordModal({
  forced = false,
  onClose,
}: {
  forced?: boolean;
  onClose?: () => void;
}) {
  const { t } = useT();
  const { refreshUser } = useAuth();

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [done, setDone] = useState(false);

  const mismatch = again !== '' && next !== again;
  const ready = current !== '' && next !== '' && next === again && !saving;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    setSaving(true);
    setError(null);
    setFieldErrors({});
    try {
      await apiClient.changePassword(current, next);
      // The flag lives on the account, so the screen behind this one only stops
      // asking once the server's own copy of the user says so.
      await refreshUser();
      setDone(true);
      if (!forced) onClose?.();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setError(apiErrorText(err, t, t('The password could not be changed.')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <BaseModal
      isOpen
      title={forced ? t('Choose your own password') : t('Change password')}
      // Forced, there is no way out of this modal: no close button, and Escape
      // resolves to nothing. That is the point of it.
      onClose={forced ? () => {} : (onClose ?? (() => {}))}
      showCloseButton={!forced}
    >
      <form onSubmit={submit} className="space-y-4">
        {forced && !done && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {t('This account was created for you, so somebody else knows its password. Choose your own to carry on.')}
          </p>
        )}

        <FormError message={error} />

        <Field label={t('Current password')} error={fieldErrors.current_password}>
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
            className={inputCls}
          />
        </Field>

        <Field label={t('New password')} error={fieldErrors.new_password}>
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
            className={inputCls}
          />
        </Field>

        <Field
          label={t('New password again')}
          error={mismatch ? t('The two do not match.') : undefined}
        >
          <input
            type="password"
            value={again}
            onChange={(e) => setAgain(e.target.value)}
            autoComplete="new-password"
            className={inputCls}
          />
        </Field>

        <div className="flex gap-2">
          {!forced && (
            <button type="button" onClick={onClose} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
          )}
          <button type="submit" disabled={!ready} className={`${btnPrimary} flex-1`}>
            {saving ? t('Saving…') : t('Change password')}
          </button>
        </div>
      </form>
    </BaseModal>
  );
}
