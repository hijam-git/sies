import type { FeeStatus } from '../../lib/api';
import { FEE_STATUS_LABEL } from './feeConstants';

// Colour carries meaning, so it is fixed per state: red is money owed past its
// date, amber is money owed, blue is part-settled, green is settled, grey is
// written off. **The word is always there too** — colour alone is not a status
// for anybody reading this on a phone in strong daylight at a counter.
const TONE: Record<FeeStatus, string> = {
  unpaid: 'bg-amber-100 text-amber-800',
  partial: 'bg-blue-100 text-blue-800',
  paid: 'bg-emerald-100 text-emerald-800',
  overdue: 'bg-red-100 text-red-800',
  waived: 'bg-gray-200 text-gray-700',
};

/** The invoice's state, drawn identically on every screen that shows one.
 *  Shared rather than copied: an invoice that is amber here and grey on the
 *  next screen is a screen somebody stops trusting. */
export default function FeeStatusBadge({
  status,
  t,
}: {
  status: FeeStatus;
  t: (s: string) => string;
}) {
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ${
        TONE[status] ?? 'bg-gray-100 text-gray-700'
      }`}
    >
      {t(FEE_STATUS_LABEL[status] ?? status)}
    </span>
  );
}
