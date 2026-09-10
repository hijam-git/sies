import React, { useEffect } from 'react';
import { useT } from '../../lib/i18n';

interface BaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '4xl' | '6xl';
  showCloseButton?: boolean;
  /** A sticky action row at the foot of the sheet — Save / Cancel. Kept out of
   *  `children` so it can stay put while a long form scrolls behind it, which
   *  is the whole reason a phone user can reach Save without scrolling to the
   *  bottom of a forty-field admission form. */
  footer?: React.ReactNode;
}

/**
 * The one dialog shell, so an admission form and a fee receipt open the same
 * way. Every module's modal is this with different children.
 *
 * **Full-screen sheet below `md`, centred dialog from `md` up** (`CLAUDE.md`
 * §7a rule 6). Solved here once: a centred card on a 360px screen leaves a
 * useless margin of backdrop on each side and pushes the form into a column
 * too narrow to type in.
 */
export default function BaseModal({
  isOpen,
  onClose,
  title,
  children,
  maxWidth = 'md',
  showCloseButton = true,
  footer,
}: BaseModalProps) {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  // Without this the page behind scrolls under the sheet on a phone, and the
  // user loses their place in a student list they have to come back to.
  useEffect(() => {
    if (isOpen) document.body.style.overflow = 'hidden';
    else document.body.style.overflow = 'unset';
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  const { t } = useT();

  if (!isOpen) return null;

  const maxWidthClasses = {
    sm: 'md:max-w-sm',
    md: 'md:max-w-md',
    lg: 'md:max-w-lg',
    xl: 'md:max-w-xl',
    '2xl': 'md:max-w-2xl',
    '4xl': 'md:max-w-4xl',
    '6xl': 'md:max-w-6xl',
  };

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
      {/* No backdrop below md — the sheet covers the screen, so tinting what
          is behind it only costs a repaint. */}
      <div
        className="fixed inset-0 hidden bg-black bg-opacity-50 transition-opacity md:block"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="flex h-full w-full md:min-h-full md:items-center md:justify-center md:p-4">
        <div
          className={`relative flex h-full w-full flex-col bg-white shadow-2xl
                      md:h-auto md:max-h-[90vh] md:rounded-2xl ${maxWidthClasses[maxWidth]}`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Sticky, because on a phone this header is the only thing telling
              the user what they are filling in once the form scrolls. */}
          {/* Compact from `md` up: a 24px title and 24px of padding above it
              spent a tenth of a laptop dialog on saying what the user just
              clicked. The phone sheet keeps its own padding — there the header
              is the only context once the form scrolls. */}
          <div className="sticky top-0 z-10 flex shrink-0 items-center justify-between gap-3 border-b border-gray-100 bg-white px-4 py-2 md:rounded-t-2xl md:border-0 md:px-5 md:pb-2 md:pt-4">
            <h2 className="min-w-0 truncate text-base font-bold text-gray-900 md:text-lg">{title}</h2>
            {showCloseButton && (
              <button
                onClick={onClose}
                className="-mr-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-50 hover:text-gray-600"
                aria-label={t('Close modal')}
              >
                <svg
                  className="h-6 w-6"
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 md:px-5 md:pb-4 md:pt-0">
            {children}
          </div>

          {footer && (
            // pb-safe clears the phone's home indicator; without it the Save
            // button sits under the gesture bar and cannot be tapped.
            <div className="shrink-0 border-t border-gray-100 bg-white px-4 py-2 pb-safe md:rounded-b-2xl md:px-5">
              {footer}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
