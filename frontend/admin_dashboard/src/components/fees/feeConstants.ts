import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Branch, FeeStatus, PaymentMethod, Recurrence } from '../../lib/api';
import { useAuth } from '../../lib/auth-context';

/**
 * The choice lists the four fee tabs share, and the letterhead the receipt
 * prints.
 *
 * Separate from `FeeStatusBadge.tsx` because a module that exports both a
 * component and a constant loses Fast Refresh for every file importing it —
 * the same reason `components/common/styles.ts` exists beside `Field.tsx`.
 */

/** `docs/06` #8's five states, and nothing else can appear. */
export const FEE_STATUSES: FeeStatus[] = ['unpaid', 'partial', 'paid', 'overdue', 'waived'];

/** English source strings, translated through the dictionary like everything
 *  else — never the API's own `"Unpaid · বকেয়া"` label, which hard-codes both
 *  languages into one string and cannot follow the toggle. */
export const FEE_STATUS_LABEL: Record<FeeStatus, string> = {
  unpaid: 'Unpaid',
  partial: 'Partly paid',
  paid: 'Paid',
  overdue: 'Overdue',
  waived: 'Waived',
};

/** The eight ways money arrives (`fees.models.PaymentMethod`). Order is the
 *  order a Bangladeshi counter meets them in, not alphabetical. */
export const PAYMENT_METHODS: { value: PaymentMethod; label: string }[] = [
  { value: 'cash', label: 'Cash' },
  { value: 'bkash', label: 'bKash' },
  { value: 'nagad', label: 'Nagad' },
  { value: 'rocket', label: 'Rocket' },
  { value: 'bank', label: 'Bank' },
  { value: 'cheque', label: 'Cheque' },
  { value: 'card', label: 'Card' },
  { value: 'online', label: 'Online' },
];

/** The three the API refuses without a transaction id — a wallet collection
 *  with none cannot be reconciled against the wallet's statement, which is the
 *  only reason the id exists. Checked on the screen too, so the clerk is told
 *  before the request goes out rather than by a 400 afterwards. */
export const METHODS_NEEDING_TXN: PaymentMethod[] = ['bkash', 'nagad', 'rocket'];

export function methodLabel(method: PaymentMethod, t: (s: string) => string): string {
  return t(PAYMENT_METHODS.find((m) => m.value === method)?.label ?? method);
}

export const RECURRENCES: { value: Recurrence; label: string }[] = [
  { value: 'one_time', label: 'One time' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'session', label: 'Per session' },
  { value: 'exam', label: 'Per exam' },
  { value: 'custom', label: 'Custom' },
];

/**
 * The institution, for the receipt's letterhead.
 *
 * `GET /api/branches/` costs `branches.view`, which an **accountant does not
 * hold** — and an accountant is exactly who prints receipts. So a failure is not
 * an error here: the receipt falls back to the institution name carried on the
 * user's own account, which every user has, and prints without a logo or an
 * address rather than not printing at all.
 */
export function useLetterhead() {
  const { user, activeBranchId, branches } = useAuth();
  const [fetched, setFetched] = useState<Branch | null>(null);

  const wanted = activeBranchId ?? user?.branch ?? null;
  // The switcher already loaded it for a platform admin. Derived, not copied
  // into state — a `setState` in an effect body is a second render before paint.
  const known = useMemo(
    () => branches.find((b) => b.id === wanted) ?? null,
    [branches, wanted],
  );

  useEffect(() => {
    if (known) return;
    let alive = true;
    void apiClient
      .getBranches()
      .then((rows) => {
        if (alive) setFetched(rows.find((b) => b.id === wanted) ?? rows[0] ?? null);
      })
      .catch(() => {
        // No `branches.view`. The fallback below still names the institution.
      });
    return () => {
      alive = false;
    };
  }, [known, wanted]);

  const branch = known ?? fetched;

  return {
    institutionName: branch?.name ?? user?.branch_name ?? '',
    institutionNameBn: branch?.name_bn ?? '',
    institutionAddress: branch
      ? [branch.address, branch.thana, branch.district].filter(Boolean).join(', ')
      : '',
    institutionPhone: branch?.phone ?? '',
    logoUrl: branch?.logo ?? null,
  };
}
