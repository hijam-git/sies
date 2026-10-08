import type { ReactNode } from 'react';
import { useT } from '../../lib/i18n';

/**
 * "Roll 7 · ID SIES-000123" — the two numbers a register row is known by.
 *
 * The **roll** is the student's number in this class (শ্রেণি রোল): it is what
 * a teacher calls out and the order the register is read in, so it comes
 * first and in weight. The **ID** is the permanent institution-wide number a
 * guardian quotes at the office, so it sits beside it, quieter. Use this only
 * on a screen that already names the class — a roll means nothing without one.
 *
 * `flex-wrap` rather than a separator: on a 360px roster the column beside the
 * four status buttons is about 110px wide, and the ID simply drops to its own
 * line there instead of being truncated into "SIES-0…".
 *
 * `section` is for the whole-class view of a class with sections, where rolls
 * restart per section and "roll 7" alone names two students.
 */
export default function RollAndId({
  roll,
  code,
  section,
  children,
  className = '',
}: {
  roll: number | null;
  code: string;
  section?: string;
  /** Anything else for the same line — a percentage, "already recorded". */
  children?: ReactNode;
  className?: string;
}) {
  const { t } = useT();
  return (
    <span
      className={`flex min-w-0 flex-wrap items-baseline gap-x-1.5 leading-snug ${className}`}
    >
      <span className="shrink-0 font-semibold text-gray-700" title={t('Class roll')}>
        {`${t('Roll')} ${roll ?? '—'}`}
        {section ? <span className="font-normal text-gray-500">{` (${section})`}</span> : null}
      </span>
      <span className="min-w-0 truncate font-mono text-gray-400" title={t('Student ID')}>
        {`${t('ID')} ${code}`}
      </span>
      {children}
    </span>
  );
}
