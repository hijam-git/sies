import { useState } from 'react';
import { apiClient, rollHolder } from '../../lib/api';
import type { Enrolment } from '../../lib/api';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import BaseModal from '../common/BaseModal';
import Field, { FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls } from '../common/styles';

/** Who already holds the roll being asked for. */
interface Holder {
  enrolment: number;
  name: string;
}

/**
 * Change one student's class roll (শ্রেণি রোল).
 *
 * The roll is per class — per section when the class has sections — so the
 * only students it can collide with are `peers`, the rest of the same series.
 * When the number is taken the dialog does not just refuse: it names the
 * student who has it and offers to swap, which is what the office actually
 * wants when it renumbers a class ("make Bilal 3 and whoever is 3 gets his").
 *
 * The local check against `peers` is for speed only. The server decides, under
 * a lock, and its `roll_taken` answer opens the same swap question — so a
 * collision with a student admitted a minute ago in another tab still ends in
 * a sentence, not in "duplicate".
 */
export default function RollChangeModal({
  enrolment,
  studentName,
  classLabel,
  peers,
  onClose,
  onSaved,
}: {
  enrolment: Enrolment;
  studentName: string;
  /** "Class 5 · A" — a roll is meaningless without the class it is in. */
  classLabel: string;
  /** The other enrolments in the same session, class and section. */
  peers: Enrolment[];
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const { t } = useT();
  const [value, setValue] = useState(enrolment.roll === null ? '' : String(enrolment.roll));
  const [holder, setHolder] = useState<Holder | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const target = Number(value);
  const valid = value.trim() !== '' && Number.isInteger(target) && target >= 1 && target <= 9999;
  const unchanged = valid && target === enrolment.roll;

  const submit = async (swap: boolean) => {
    if (!valid || unchanged) return;
    setError(null);

    if (!swap) {
      const local = peers.find((p) => p.roll === target && p.id !== enrolment.id);
      if (local) {
        setHolder({ enrolment: local.id, name: local.student_name });
        return;
      }
    }

    setBusy(true);
    try {
      const result = await apiClient.changeRoll(enrolment.id, target, swap);
      const other = result.swapped_with;
      onSaved(
        other
          ? t('Rolls swapped: {a} is now {x}, {b} is now {y}.')
              .replace('{a}', studentName)
              .replace('{x}', String(result.enrolment.roll))
              .replace('{b}', other.student_name)
              .replace('{y}', String(other.roll))
          : t('{a} is now roll {x}.')
              .replace('{a}', studentName)
              .replace('{x}', String(result.enrolment.roll)),
      );
      onClose();
    } catch (err) {
      const taken = rollHolder(err);
      if (taken) {
        setHolder({ enrolment: taken.enrolment, name: taken.name_bn || taken.name });
      } else {
        setError(apiErrorText(err, t, t('Could not change the roll.')));
      }
    } finally {
      setBusy(false);
    }
  };

  const footer = holder ? (
    <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
      <button type="button" onClick={() => setHolder(null)} className={btnSecondary} disabled={busy}>
        {t('Choose another roll')}
      </button>
      <button type="button" onClick={() => void submit(true)} className={btnPrimary} disabled={busy}>
        {busy ? t('Saving…') : t('Swap rolls')}
      </button>
    </div>
  ) : (
    <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
      <button type="button" onClick={onClose} className={btnSecondary}>
        {t('Cancel')}
      </button>
      <button
        type="button"
        onClick={() => void submit(false)}
        className={btnPrimary}
        disabled={busy || !valid || unchanged}
      >
        {busy ? t('Saving…') : t('Save')}
      </button>
    </div>
  );

  return (
    <BaseModal isOpen onClose={onClose} title={t('Change class roll')} maxWidth="sm" footer={footer}>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          void submit(!!holder);
        }}
      >
        <div className="rounded-lg bg-gray-50 px-3 py-2 text-sm">
          <span className="block font-medium text-gray-900">{studentName}</span>
          <span className="block text-gray-600">
            {`${classLabel} · ${t('Current roll')} ${enrolment.roll ?? '—'}`}
          </span>
        </div>

        <Field
          label={t('New roll in this class')}
          hint={t('The roll is counted inside this class, so roll 3 here is unrelated to roll 3 in another class.')}
        >
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={9999}
            step={1}
            autoFocus
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              setHolder(null);
            }}
            className={inputCls}
          />
        </Field>

        {holder && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            <p className="font-medium">
              {t('Roll {x} already belongs to {b}.')
                .replace('{x}', String(target))
                .replace('{b}', holder.name)}
            </p>
            <p className="mt-0.5">
              {t('Swap them? {b} will get roll {y}.')
                .replace('{b}', holder.name)
                .replace('{y}', String(enrolment.roll ?? '—'))}
            </p>
          </div>
        )}

        <FormError message={error} />
      </form>
    </BaseModal>
  );
}
