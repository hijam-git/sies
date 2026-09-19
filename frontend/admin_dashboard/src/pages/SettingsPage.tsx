import { useEffect, useState } from 'react';
import { apiClient } from '../lib/api';
import type { Branch } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../lib/apiErrors';
import { useTabParam } from '../lib/useTabParam';
import TabStrip from '../components/common/TabStrip';
import type { TabDef } from '../components/common/TabStrip';
import StreamsSessionsTab from '../components/settings/StreamsSessionsTab';
import FormTemplatesTab from '../components/forms/FormTemplatesTab';
import QuestionsTab from '../components/forms/QuestionsTab';
import GradingTab from '../components/settings/GradingTab';
import BranchForm from '../components/settings/BranchForm';
import { draftFrom, draftToPayload, emptyDraft } from '../components/settings/branchDraft';
import type { BranchDraft } from '../components/settings/branchDraft';

/**
 * Settings — the institution's own configuration, five tabs, all built.
 *
 * The sidebar lists the same five as sub-items; the tab strip is the other
 * door to them (`pages/navigation.ts`).
 *
 * **Fee heads are not here.** They were a placeholder on this page while fees
 * were unbuilt, and the finished screen went where the money is — Fees → Fee
 * setup, beside the invoices it prices (`components/fees/FeeSetupTab`). Two
 * doors to one editor is one door too many, and the placeholder outlived the
 * feature it stood in for (`CLAUDE.md` §2a).
 */

type Tab = 'institution' | 'streams' | 'grading' | 'form-templates' | 'questions';

const TABS: Tab[] = [
  'institution',
  'streams',
  'grading',
  'form-templates',
  'questions',
];

/**
 * The institution's own record.
 *
 * Which institution that is comes from the header: a branch user has exactly
 * one and the backend ignores any attempt to name another (`docs/02` §3); the
 * platform admin has to pick one in the switcher, because "edit all
 * institutions at once" is not an operation.
 */
function InstitutionTab({ branchId }: { branchId: number | null }) {
  const { t } = useT();
  const { can } = usePermissions();

  const [branch, setBranch] = useState<Branch | null>(null);
  const [draft, setDraft] = useState<BranchDraft>(emptyDraft);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // The fetch lives inside the effect so nothing sets state synchronously in an
  // effect body, and `alive` stops a late answer writing into a screen the user
  // has already left.
  useEffect(() => {
    let alive = true;
    const run = async () => {
      try {
        // `GET /api/branches/` returns the caller's own institution and nothing
        // else for a branch user, and the selected one for a platform admin, so
        // the first row is the right row either way.
        const page = await apiClient.listBranches(branchId === null ? '' : `?branch=${branchId}`);
        if (!alive) return;
        const first = page.results.find((b) => branchId === null || b.id === branchId) ?? null;
        setBranch(first);
        setFormError(null);
        if (first) setDraft(draftFrom(first));
      } catch (err) {
        if (alive) setFormError(apiErrorText(err, t, t('Could not load this institution.')));
      } finally {
        if (alive) setLoading(false);
      }
    };
    void run();
    return () => {
      alive = false;
    };
  }, [branchId, t]);

  const save = async () => {
    if (!branch) return;
    setSaving(true);
    setSaved(false);
    setFormError(null);
    setFieldErrors({});
    try {
      const updated = await apiClient.updateBranch(branch.id, draftToPayload(draft, true));
      setBranch(updated);
      setDraft(draftFrom(updated));
      setSaved(true);
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this institution.')));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="py-8 text-center text-sm text-gray-500">{t('Loading...')}</p>;
  }

  if (!branch) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
        {t('Choose an institution in the header to edit its settings.')}
      </div>
    );
  }

  if (!can('branches', 'update')) {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-gray-900">{branch.name_bn || branch.name}</h2>
        <p className="mt-1 text-sm text-gray-500">{branch.address}</p>
        <p className="mt-4 text-sm text-gray-500">
          {t('You can see these settings but not change them.')}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {saved && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {t('Saved successfully!')}
        </div>
      )}
      <BranchForm
        draft={draft}
        setDraft={setDraft}
        onSubmit={() => void save()}
        saving={saving}
        formError={formError}
        fieldErrors={fieldErrors}
        mode="edit"
      />
    </div>
  );
}

export default function SettingsPage() {
  const { t } = useT();
  const { user, activeBranchId } = useAuth();
  const { canView } = usePermissions();
  const [tab, setTab] = useTabParam<Tab>(TABS, 'institution');

  // A branch user's institution is their own; the platform admin's is whatever
  // the header switcher says, which is null until they choose.
  const branchId = user?.branch ?? activeBranchId;

  if (!canView('settings')) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Settings')}</h1>
        <p className="mt-2 text-sm text-gray-500">
          {t('You do not have permission to do this.')}
        </p>
      </div>
    );
  }

  const tabs: TabDef<Tab>[] = [
    { key: 'institution', label: t('Institution') },
    { key: 'streams', label: t('Streams & Sessions') },
    { key: 'grading', label: t('Grading') },
    { key: 'form-templates', label: t('Form templates') },
    // The question bank sits beside the templates rather than inside one: a
    // question with no template is reusable across every form this institution
    // prints, which is the common case (`docs/07` §5).
    { key: 'questions', label: t('Questions') },
  ];

  return (
    <div className="space-y-3">
      <TabStrip tabs={tabs} active={tab} onChange={setTab} heading={t('Settings')} />

      {tab === 'institution' && <InstitutionTab branchId={branchId} />}
      {tab === 'streams' && canView('academics') && <StreamsSessionsTab branchId={branchId} />}
      {tab === 'streams' && !canView('academics') && (
        <div className="rounded-xl border border-gray-100 bg-white p-6 text-center text-sm text-gray-500 shadow-sm">
          {t('You do not have permission to do this.')}
        </div>
      )}
      {tab === 'grading' && <GradingTab branchId={branchId} />}
      {tab === 'form-templates' && <FormTemplatesTab />}
      {tab === 'questions' && <QuestionsTab />}
    </div>
  );
}
