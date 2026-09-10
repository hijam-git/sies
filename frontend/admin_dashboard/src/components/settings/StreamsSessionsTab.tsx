import { useEffect, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Session, Stream } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import { formatDhakaDate } from '../../lib/timezone';
import BaseModal from '../common/BaseModal';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import Field, { FieldGrid, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls } from '../common/styles';

/**
 * Streams and academic years, for one institution.
 *
 * The two live on one panel because they are the same setup act: a session
 * covers a set of streams, and neither is useful without the other. Streams are
 * seeded when the institution is created (`docs/08` D2) — this screen is where
 * the institution renames them into **its own** Bangla words (D2a) and adds any
 * the seed did not guess.
 *
 * `branchId` is required for every write. Streams and sessions are
 * branch-scoped, so the server stamps the institution from the request and
 * refuses a write that does not name one — a platform admin has to pick an
 * institution in the header before they can add anything.
 */
export default function StreamsSessionsTab({ branchId }: { branchId: number | null }) {
  const { t } = useT();
  const { can } = usePermissions();

  const [streams, setStreams] = useState<Stream[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [streamDraft, setStreamDraft] = useState<Partial<Stream> | null>(null);
  const [sessionDraft, setSessionDraft] = useState<Partial<Session> | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const mayEdit = can('academics', 'update');
  const mayCreate = can('academics', 'create');

  /** Bumped to ask for fresh lists. The fetch lives inside the effect so
   *  nothing sets state synchronously in an effect body, and `alive` stops a
   *  late answer writing into a screen the user has already left. */
  const [reloadToken, setReloadToken] = useState(0);
  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    let alive = true;
    const run = async () => {
      try {
        const [s, sess] = await Promise.all([
          apiClient.listStreams(branchId),
          apiClient.listSessions(branchId),
        ]);
        if (!alive) return;
        setStreams(s);
        setSessions(sess);
        setLoadError(null);
      } catch (err) {
        if (alive) setLoadError(apiErrorText(err, t, t('Could not load streams and sessions.')));
      } finally {
        if (alive) setLoading(false);
      }
    };
    void run();
    return () => {
      alive = false;
    };
  }, [branchId, reloadToken, t]);

  const startWrite = () => {
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
  };

  const failed = (err: unknown, fallback: string) => {
    setFieldErrors(apiFieldErrors(err));
    setFormError(apiErrorText(err, t, fallback));
  };

  const saveStream = async () => {
    if (!streamDraft || branchId === null) return;
    startWrite();
    try {
      const body = {
        code: (streamDraft.code ?? '').trim().toLowerCase(),
        name: (streamDraft.name ?? '').trim(),
        name_bn: (streamDraft.name_bn ?? '').trim(),
        order: Number(streamDraft.order ?? 0),
        is_active: streamDraft.is_active ?? true,
      };
      if (streamDraft.id) await apiClient.updateStream(streamDraft.id, branchId, body);
      else await apiClient.createStream(branchId, body);
      setStreamDraft(null);
      reload();
    } catch (err) {
      failed(err, t('Could not save this stream.'));
    } finally {
      setSaving(false);
    }
  };

  const saveSession = async () => {
    if (!sessionDraft || branchId === null) return;
    startWrite();
    try {
      const body = {
        name: (sessionDraft.name ?? '').trim(),
        starts_on: sessionDraft.starts_on,
        ends_on: sessionDraft.ends_on,
        streams: sessionDraft.streams ?? [],
      };
      if (sessionDraft.id) await apiClient.updateSession(sessionDraft.id, branchId, body);
      else await apiClient.createSession(branchId, body);
      setSessionDraft(null);
      reload();
    } catch (err) {
      failed(err, t('Could not save this session.'));
    } finally {
      setSaving(false);
    }
  };

  /**
   * Make a session current.
   *
   * Its own action rather than a checkbox in the form: at most one session per
   * (branch, stream) may be current, the rule spans the streams many-to-many so
   * no database constraint can hold it, and the viewset routes this save
   * through `services.set_current_session`, which unsets the others in the same
   * transaction. Setting the field beside the dates would leave two current.
   */
  const makeCurrent = async (session: Session) => {
    if (branchId === null) return;
    setNotice(null);
    try {
      await apiClient.setCurrentSession(session.id, branchId);
      reload();
      setNotice(t('This is now the current session.'));
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not change the current session.')));
    }
  };

  if (branchId === null) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
        {t('Choose an institution in the header to edit its streams and sessions.')}
      </div>
    );
  }

  const streamColumns: Column<Stream>[] = [
    {
      key: 'name',
      label: t('Name'),
      primary: true,
      render: (s) => (
        <span className="block">
          <span className="block">{s.name_bn || s.name}</span>
          {s.name_bn && <span className="block text-xs text-gray-500">{s.name}</span>}
        </span>
      ),
    },
    { key: 'code', label: t('Code'), render: (s) => <span className="font-mono">{s.code}</span> },
    { key: 'order', label: t('Order'), render: (s) => s.order },
    {
      key: 'status',
      label: t('Status'),
      render: (s) => (s.is_active ? t('Active') : t('Inactive')),
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      cellClass: 'px-4 py-3 text-right',
      render: (s) =>
        mayEdit ? (
          <button
            type="button"
            onClick={() => setStreamDraft(s)}
            className="tap rounded-lg px-3 text-sm font-medium text-blue-700 hover:bg-blue-50"
          >
            {t('Edit')}
          </button>
        ) : null,
    },
  ];

  const streamName = (id: number) => {
    const stream = streams.find((s) => s.id === id);
    return stream ? stream.name_bn || stream.name : `#${id}`;
  };

  const sessionColumns: Column<Session>[] = [
    {
      key: 'name',
      label: t('Name'),
      primary: true,
      render: (s) => (
        <span className="flex flex-wrap items-center gap-2">
          <span>{s.name}</span>
          {s.is_current && (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">
              {t('Current')}
            </span>
          )}
        </span>
      ),
    },
    {
      key: 'dates',
      label: t('Date'),
      render: (s) => `${formatDhakaDate(s.starts_on)} – ${formatDhakaDate(s.ends_on)}`,
    },
    {
      key: 'streams',
      label: t('Streams'),
      hideOnNarrow: true,
      render: (s) => (s.streams.length ? s.streams.map(streamName).join(', ') : '—'),
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      cellClass: 'px-4 py-3 text-right',
      render: (s) => (
        <span className="flex flex-wrap items-center justify-end gap-1">
          {mayEdit && !s.is_current && (
            <button
              type="button"
              onClick={() => void makeCurrent(s)}
              className="tap rounded-lg px-3 text-sm font-medium text-emerald-700 hover:bg-emerald-50"
            >
              {t('Make current')}
            </button>
          )}
          {mayEdit && (
            <button
              type="button"
              onClick={() => setSessionDraft(s)}
              className="tap rounded-lg px-3 text-sm font-medium text-blue-700 hover:bg-blue-50"
            >
              {t('Edit')}
            </button>
          )}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-8">
      {loadError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {loadError}
        </div>
      )}
      {notice && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {notice}
        </div>
      )}

      <section className="space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-900">{t('Streams')}</h2>
          </div>
          {mayCreate && (
            <button
              type="button"
              onClick={() =>
                setStreamDraft({ code: '', name: '', name_bn: '', order: (streams.length + 1) * 10, is_active: true })
              }
              className={`${btnPrimary} w-full sm:w-auto`}
            >
              {t('Add stream')}
            </button>
          )}
        </div>

        {loading ? (
          <div className="rounded-xl border border-gray-100 bg-white p-6 text-center text-sm text-gray-500">
            {t('Loading...')}
          </div>
        ) : (
          <ResponsiveTable
            columns={streamColumns}
            rows={streams}
            rowKey={(s) => s.id}
            empty={t('No streams yet.')}
          />
        )}
      </section>

      <section className="space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-900">{t('Sessions')}</h2>
          </div>
          {mayCreate && (
            <button
              type="button"
              onClick={() =>
                setSessionDraft({ name: '', starts_on: '', ends_on: '', streams: [] })
              }
              className={`${btnPrimary} w-full sm:w-auto`}
            >
              {t('Add session')}
            </button>
          )}
        </div>

        {loading ? (
          <div className="rounded-xl border border-gray-100 bg-white p-6 text-center text-sm text-gray-500">
            {t('Loading...')}
          </div>
        ) : (
          <ResponsiveTable
            columns={sessionColumns}
            rows={sessions}
            rowKey={(s) => s.id}
            empty={t('No sessions yet.')}
          />
        )}
      </section>

      <BaseModal
        isOpen={streamDraft !== null}
        onClose={() => setStreamDraft(null)}
        title={streamDraft?.id ? t('Edit stream') : t('Add stream')}
        footer={
          <div className="flex gap-2">
            <button type="button" onClick={() => setStreamDraft(null)} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
            <button type="submit" form="stream-form" className={`${btnPrimary} flex-1`} disabled={saving}>
              {saving ? t('Saving...') : t('Save')}
            </button>
          </div>
        }
      >
        {streamDraft && (
          <form
            id="stream-form"
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void saveStream();
            }}
          >
            <FormError message={formError} />
            <FieldGrid>
              <Field
                label={t('Code')}
                required
                hint={t('Lower case, unique here. Other records point at it.')}
                error={fieldErrors.code}
              >
                <input
                  className={inputCls}
                  value={streamDraft.code ?? ''}
                  onChange={(e) => setStreamDraft({ ...streamDraft, code: e.target.value })}
                  required
                  disabled={Boolean(streamDraft.id)}
                />
              </Field>
              <Field label={t('Order')} error={fieldErrors.order}>
                <input
                  className={inputCls}
                  value={String(streamDraft.order ?? 0)}
                  onChange={(e) =>
                    setStreamDraft({ ...streamDraft, order: Number(e.target.value.replace(/\D/g, '') || 0) })
                  }
                  inputMode="numeric"
                />
              </Field>
              <Field label={t('Name (English)')} required error={fieldErrors.name}>
                <input
                  className={inputCls}
                  value={streamDraft.name ?? ''}
                  onChange={(e) => setStreamDraft({ ...streamDraft, name: e.target.value })}
                  required
                />
              </Field>
              <Field
                label={t('Name (Bangla)')}
                hint={t('Your institution’s own spelling')}
                error={fieldErrors.name_bn}
              >
                <input
                  className={inputCls}
                  lang="bn"
                  value={streamDraft.name_bn ?? ''}
                  onChange={(e) => setStreamDraft({ ...streamDraft, name_bn: e.target.value })}
                />
              </Field>
            </FieldGrid>
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                className="h-5 w-5 rounded border-gray-300 text-blue-600"
                checked={streamDraft.is_active ?? true}
                onChange={(e) => setStreamDraft({ ...streamDraft, is_active: e.target.checked })}
              />
              <span className="text-sm font-medium text-gray-900">{t('Active')}</span>
            </label>
          </form>
        )}
      </BaseModal>

      <BaseModal
        isOpen={sessionDraft !== null}
        onClose={() => setSessionDraft(null)}
        title={sessionDraft?.id ? t('Edit session') : t('Add session')}
        footer={
          <div className="flex gap-2">
            <button type="button" onClick={() => setSessionDraft(null)} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
            <button type="submit" form="session-form" className={`${btnPrimary} flex-1`} disabled={saving}>
              {saving ? t('Saving...') : t('Save')}
            </button>
          </div>
        }
      >
        {sessionDraft && (
          <form
            id="session-form"
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void saveSession();
            }}
          >
            <FormError message={formError} />
            <Field label={t('Name')} required hint={t('For example 2026 or 2026–27')} error={fieldErrors.name}>
              <input
                className={inputCls}
                value={sessionDraft.name ?? ''}
                onChange={(e) => setSessionDraft({ ...sessionDraft, name: e.target.value })}
                required
              />
            </Field>
            <FieldGrid>
              <Field label={t('From')} required error={fieldErrors.starts_on}>
                <input
                  type="date"
                  className={inputCls}
                  value={sessionDraft.starts_on ?? ''}
                  onChange={(e) => setSessionDraft({ ...sessionDraft, starts_on: e.target.value })}
                  required
                />
              </Field>
              <Field label={t('To')} required error={fieldErrors.ends_on}>
                <input
                  type="date"
                  className={inputCls}
                  value={sessionDraft.ends_on ?? ''}
                  onChange={(e) => setSessionDraft({ ...sessionDraft, ends_on: e.target.value })}
                  required
                />
              </Field>
            </FieldGrid>

            <fieldset>
              <legend className="mb-2 text-sm font-medium text-gray-700">{t('Streams')}</legend>
              {fieldErrors.streams && (
                <p className="mb-2 text-xs font-medium text-red-600">{fieldErrors.streams}</p>
              )}
              {/* Stacked checkboxes rather than a multi-select: a native
                  multi-select on a phone is a control almost nobody can operate
                  with a thumb without losing the selection they already made. */}
              <div className="space-y-1">
                {streams.map((stream) => {
                  const on = (sessionDraft.streams ?? []).includes(stream.id);
                  return (
                    <label key={stream.id} className="flex min-h-[44px] items-center gap-3">
                      <input
                        type="checkbox"
                        className="h-5 w-5 rounded border-gray-300 text-blue-600"
                        checked={on}
                        onChange={() =>
                          setSessionDraft({
                            ...sessionDraft,
                            streams: on
                              ? (sessionDraft.streams ?? []).filter((id) => id !== stream.id)
                              : [...(sessionDraft.streams ?? []), stream.id],
                          })
                        }
                      />
                      <span className="text-sm text-gray-900">{stream.name_bn || stream.name}</span>
                    </label>
                  );
                })}
              </div>
            </fieldset>

            {sessionDraft.id && sessionDraft.is_current && (
              <p className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
                {t('This is the current session.')}
              </p>
            )}
          </form>
        )}
      </BaseModal>
    </div>
  );
}
