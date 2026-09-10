import type { ReactNode } from 'react';
import { useT } from '../../lib/i18n';

interface SectionCardProps {
  title: string;
  icon?: ReactNode;
  /** A line of what is currently set, so the card answers its own question
   *  without being opened. */
  preview: string;
  onEdit: () => void;
  /** Draws the amber edge and the badge. Settings screens are a checklist an
   *  institution works through once, and an unfinished one has to look it. */
  isComplete?: boolean;
  disabled?: boolean;
  /** The button's words. Defaults to "Edit Section"; a card that opens a list
   *  rather than a form should say so. */
  actionLabel?: string;
}

/** One settings tile — a group of fields behind a preview and a button. Used
 *  across the Settings screens so branch details, fee categories and the grade
 *  scale all present the same way. */
export default function SectionCard({
  title,
  icon,
  preview,
  onEdit,
  isComplete = true,
  disabled = false,
  actionLabel,
}: SectionCardProps) {
  const { t } = useT();

  return (
    <div
      className={`rounded-lg bg-white p-4 shadow-md transition-shadow hover:shadow-lg sm:p-6 ${
        isComplete ? 'border-l-4 border-blue-600' : 'border-l-4 border-amber-400'
      } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          {icon && <div className="flex-shrink-0 text-2xl">{icon}</div>}
          <h3 className="min-w-0 text-base font-semibold text-gray-900 sm:text-lg">{title}</h3>
        </div>
        {!isComplete && (
          <span className="inline-flex shrink-0 rounded-full bg-amber-100 px-2 py-1 text-xs font-medium text-amber-800">
            {t('Incomplete')}
          </span>
        )}
      </div>

      <div className="mb-4 min-h-[48px]">
        <p className="line-clamp-3 text-sm text-gray-600">{preview || t('Not configured')}</p>
      </div>

      <button
        onClick={onEdit}
        disabled={disabled}
        className="tap w-full rounded-lg bg-blue-600 px-4 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {actionLabel || t('Edit Section')}
      </button>
    </div>
  );
}
