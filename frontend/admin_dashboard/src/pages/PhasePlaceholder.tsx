import { Link } from 'react-router-dom';
import { useT } from '../lib/i18n';

/**
 * What a nav item points at when its module belongs to a later phase.
 *
 * The navigation is complete from phase 0 so the shape of the system is
 * visible from the start — an institution's admin can see that fees, exams and
 * attendance are coming and where they will live. But a link that goes nowhere,
 * or to a screen pretending to be empty, is worse than no link: it reads as a
 * broken product rather than an unfinished one. So each says plainly which
 * phase builds it.
 */
export default function PhasePlaceholder({
  labelKey,
  phase,
}: {
  /** The nav item's English label — a dictionary key, translated here rather
   *  than at the route, so the heading follows the language toggle without the
   *  route table having to re-render. */
  labelKey: string;
  phase: number;
}) {
  const { t } = useT();
  const title = t(labelKey);

  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-xl border border-gray-100 bg-white p-6 text-center shadow-sm sm:p-10">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-blue-50">
          <svg
            className="h-6 w-6 text-blue-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>

        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{title}</h1>

        <p className="mt-2 text-sm font-medium text-blue-700">
          {t('This screen is built in phase PHASE.').replace('PHASE', String(phase))}
        </p>

        <p className="mx-auto mt-4 max-w-md text-sm leading-relaxed text-gray-500">
          {t(
            'The navigation is complete so the shape of the system is visible from the start. Nothing here is hidden from you — this module simply has not been built yet.',
          )}
        </p>

        <Link
          to="/"
          className="tap mt-6 rounded-lg bg-blue-600 px-5 text-sm font-medium text-white hover:bg-blue-700"
        >
          {t('Back to overview')}
        </Link>
      </div>
    </div>
  );
}
