import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { GradeScale, GradingMethod, Stream } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { FormError } from '../common/Field';
import { btnPrimary, btnSecondary } from '../common/styles';

/**
 * Settings → Grading. One card per বিভাগ: its method and its grades.
 *
 * Two methods, chosen per বিভাগ (`exams/grading.py` has the rules):
 *  - **GPA (board)** — subject-wise grade points, optional-subject bonus,
 *    any compulsory fail is GPA 0.00; merit by GPA then total.
 *  - **Qawmi grades** — মুমতাজ … রাসিব from the total percentage, no GPA;
 *    merit by total.
 *
 * Switching method replaces the grades with that method's standard set, and
 * says so before it does. Editing a grade changes results of exams that are
 * still open; published results were frozen when they were published and do
 * not move.
 */

interface BandDraft {
  min_percent: string;
  grade: string;
  grade_bn: string;
  point: string;
  is_fail: boolean;
}

interface ScaleDraft {
  optional_bonus_above: string;
  bands: BandDraft[];
}

const plain = (value: string | number) => String(Number(value));

function toDraft(scale: GradeScale): ScaleDraft {
  return {
    optional_bonus_above: plain(scale.optional_bonus_above),
    bands: [...scale.bands]
      .sort((a, b) => Number(b.min_percent) - Number(a.min_percent))
      .map((band) => ({
        min_percent: plain(band.min_percent),
        grade: band.grade,
        grade_bn: band.grade_bn,
        point: plain(band.point),
        is_fail: band.is_fail,
      })),
  };
}

/** Compact, but 16px on a phone so iOS does not zoom into the field. */
const cellInput =
  'h-8 w-full min-w-0 rounded-md border border-gray-200 bg-white px-2 text-base text-gray-900 ' +
  'focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30 ' +
  'disabled:border-transparent disabled:bg-transparent sm:text-[13px]';

const DIVISION_STREAMS = new Set(['hifz', 'qaumi']);

export default function GradingTab({ branchId }: { branchId: number | null }) {
  const { t, lang } = useT();
  const { can } = usePermissions();
  const mayEdit = can('settings', 'update');

  const [scales, setScales] = useState<GradeScale[] | null>(null);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [rows, streamRows] = await Promise.all([
        apiClient.listAll<GradeScale>('/grade-scales/', ''),
        apiClient.listStreams(branchId),
      ]);
      setScales(rows);
      setStreams(streamRows);
      setError(null);
    } catch (err) {
      setScales([]);
      setError(apiErrorText(err, t, t('Could not load the grading scales.')));
    }
  }, [branchId, t]);

  useEffect(() => {
    if (branchId === null) return;
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [branchId, load]);

  if (branchId === null) {
    return (
      <div className="rounded-xl border border-dashed border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
        {t('Choose an institution first.')}
      </div>
    );
  }
  if (scales === null) return <p className="text-sm text-gray-400">{t('Loading…')}</p>;

  const streamLabel = (stream: Stream) => (lang === 'bn' ? stream.name_bn || stream.name : stream.name);

  return (
    <div className="space-y-3">
      {error && <FormError message={error} />}
      {streams.map((stream) => {
        const scale = scales.find((row) => row.stream === stream.id);
        return scale ? (
          // Keyed on `updated_at` so a save or a reset remounts the card on the
          // server's copy, rather than an effect copying props into a draft.
          <ScaleCard
            key={`${scale.id}-${scale.updated_at}`}
            scale={scale}
            title={streamLabel(stream)}
            mayEdit={mayEdit}
            onChanged={load}
          />
        ) : (
          <MissingScale
            key={`stream-${stream.id}`}
            stream={stream}
            title={streamLabel(stream)}
            mayEdit={mayEdit}
            onCreated={load}
          />
        );
      })}
    </div>
  );
}

function ScaleCard({
  scale,
  title,
  mayEdit,
  onChanged,
}: {
  scale: GradeScale;
  title: string;
  mayEdit: boolean;
  onChanged: () => Promise<void>;
}) {
  const { t } = useT();
  const [draft, setDraft] = useState<ScaleDraft>(() => toDraft(scale));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const original = useMemo(() => JSON.stringify(toDraft(scale)), [scale]);
  const dirty = JSON.stringify(draft) !== original;
  const isGpa = scale.method === 'gpa';

  const setBand = (index: number, patch: Partial<BandDraft>) =>
    setDraft((d) => ({ ...d, bands: d.bands.map((band, i) => (i === index ? { ...band, ...patch } : band)) }));

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
      await onChanged();
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not save this grading scale.')));
    } finally {
      setBusy(false);
    }
  };

  const save = () =>
    run(() =>
      apiClient.patch<GradeScale>('/grade-scales/', scale.id, {
        optional_bonus_above: draft.optional_bonus_above || '0',
        bands: draft.bands.map((band) => ({
          min_percent: band.min_percent || '0',
          grade: band.grade.trim(),
          grade_bn: band.grade_bn.trim(),
          point: isGpa ? band.point || '0' : '0',
          is_fail: band.is_fail,
        })),
      }),
    );

  const reset = (method: GradingMethod) => {
    const question =
      method === scale.method
        ? t('Replace these grades with the standard set?')
        : t('Switching the method replaces these grades with its standard set. Continue?');
    if (!window.confirm(question)) return;
    void run(() => apiClient.create<GradeScale>(`/grade-scales/${scale.id}/reset/`, { method }));
  };

  return (
    <section className="overflow-hidden rounded-xl border border-gray-200/80 bg-white shadow-sm">
      <header className="flex flex-wrap items-center gap-2 border-b border-gray-100 px-4 py-3">
        <h3 className="mr-1 text-sm font-semibold text-gray-900">{title}</h3>
        <div className="inline-flex h-8 items-center gap-0.5 rounded-lg bg-gray-100 p-0.5">
          {(['gpa', 'division'] as const).map((method) => (
            <button
              key={method}
              type="button"
              aria-pressed={scale.method === method}
              disabled={!mayEdit || busy}
              onClick={() => method !== scale.method && reset(method)}
              className={`h-7 whitespace-nowrap rounded-md px-2.5 text-xs font-medium transition-all disabled:cursor-default ${
                scale.method === method
                  ? 'bg-white text-gray-900 shadow-sm ring-1 ring-gray-900/5'
                  : 'text-gray-500 hover:text-gray-800'
              }`}
            >
              {method === 'gpa' ? t('GPA (board)') : t('Qawmi grades')}
            </button>
          ))}
        </div>
        {mayEdit && (
          <div className="ml-auto flex items-center gap-2">
            <button type="button" onClick={() => reset(scale.method)} disabled={busy} className={btnSecondary}>
              {t('Standard grades')}
            </button>
            <button type="button" onClick={() => void save()} disabled={!dirty || busy} className={btnPrimary}>
              {busy ? t('Saving…') : t('Save')}
            </button>
          </div>
        )}
      </header>

      {error && (
        <div className="px-4 pt-3">
          <FormError message={error} />
        </div>
      )}

      <div className="scroll-x">
        <table className="min-w-full text-[13px]">
          <thead>
            <tr className="bg-gray-50 text-xs text-gray-500">
              <th className="w-24 px-4 py-2 text-left font-medium">{t('From (%)')}</th>
              <th className="min-w-[7rem] px-2 py-2 text-left font-medium">{t('Grade')}</th>
              <th className="min-w-[9rem] px-2 py-2 text-left font-medium">{t('Grade (Bangla)')}</th>
              {isGpa && <th className="w-20 px-2 py-2 text-left font-medium">{t('Point')}</th>}
              <th className="w-20 px-2 py-2 text-center font-medium">{t('Fail')}</th>
              {mayEdit && <th className="w-10 px-2 py-2" aria-label={t('Remove')} />}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {draft.bands.map((band, index) => (
              <tr key={index} className={band.is_fail ? 'bg-red-50/40' : ''}>
                <td className="px-4 py-1.5">
                  <input
                    type="number"
                    inputMode="decimal"
                    min={0}
                    max={100}
                    step="0.01"
                    value={band.min_percent}
                    disabled={!mayEdit}
                    onChange={(e) => setBand(index, { min_percent: e.target.value })}
                    aria-label={t('From (%)')}
                    className={cellInput}
                  />
                </td>
                <td className="px-2 py-1.5">
                  <input
                    value={band.grade}
                    disabled={!mayEdit}
                    onChange={(e) => setBand(index, { grade: e.target.value })}
                    aria-label={t('Grade')}
                    className={cellInput}
                  />
                </td>
                <td className="px-2 py-1.5">
                  <input
                    value={band.grade_bn}
                    disabled={!mayEdit}
                    onChange={(e) => setBand(index, { grade_bn: e.target.value })}
                    aria-label={t('Grade (Bangla)')}
                    className={cellInput}
                  />
                </td>
                {isGpa && (
                  <td className="px-2 py-1.5">
                    <input
                      type="number"
                      inputMode="decimal"
                      min={0}
                      max={5}
                      step="0.01"
                      value={band.point}
                      disabled={!mayEdit}
                      onChange={(e) => setBand(index, { point: e.target.value })}
                      aria-label={t('Point')}
                      className={cellInput}
                    />
                  </td>
                )}
                <td className="px-2 py-1.5 text-center">
                  <input
                    type="checkbox"
                    checked={band.is_fail}
                    disabled={!mayEdit}
                    onChange={(e) => setBand(index, { is_fail: e.target.checked })}
                    aria-label={t('Fail')}
                    className="h-4 w-4 rounded border-gray-300 text-red-600"
                  />
                </td>
                {mayEdit && (
                  <td className="px-2 py-1.5 text-center">
                    <button
                      type="button"
                      onClick={() => setDraft((d) => ({ ...d, bands: d.bands.filter((_, i) => i !== index) }))}
                      aria-label={t('Remove')}
                      className="tap rounded-md text-gray-400 hover:bg-red-50 hover:text-red-600"
                    >
                      <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(mayEdit || isGpa) && (
        <footer className="flex flex-wrap items-center gap-3 border-t border-gray-100 px-4 py-2.5">
          {mayEdit && (
            <button
              type="button"
              onClick={() =>
                setDraft((d) => ({
                  ...d,
                  bands: [...d.bands, { min_percent: '', grade: '', grade_bn: '', point: '0', is_fail: false }],
                }))
              }
              className={btnSecondary}
            >
              + {t('Add grade')}
            </button>
          )}
          {isGpa && (
            <label className="flex items-center gap-2 text-xs text-gray-600 sm:ml-auto">
              {t('Optional subject adds points above')}
              <input
                type="number"
                inputMode="decimal"
                min={0}
                max={5}
                step="0.01"
                value={draft.optional_bonus_above}
                disabled={!mayEdit}
                onChange={(e) => setDraft((d) => ({ ...d, optional_bonus_above: e.target.value }))}
                className={`${cellInput} w-20`}
              />
            </label>
          )}
        </footer>
      )}
    </section>
  );
}

/** A বিভাগ added after grading was set up: offer its standard scale. */
function MissingScale({
  stream,
  title,
  mayEdit,
  onCreated,
}: {
  stream: Stream;
  title: string;
  mayEdit: boolean;
  onCreated: () => Promise<void>;
}) {
  const { t } = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    const method: GradingMethod = DIVISION_STREAMS.has(stream.code) ? 'division' : 'gpa';
    try {
      // Created with a minimal valid scale, then reset: the standard grades live
      // on the server, and a second copy here would drift from them.
      const created = await apiClient.create<GradeScale>('/grade-scales/', {
        stream: stream.id,
        name: stream.name,
        name_bn: stream.name_bn,
        method,
        bands: [
          { min_percent: '33', grade: 'Pass', grade_bn: 'উত্তীর্ণ', point: '1', is_fail: false },
          { min_percent: '0', grade: 'Fail', grade_bn: 'অনুত্তীর্ণ', point: '0', is_fail: true },
        ],
      });
      await apiClient.create<GradeScale>(`/grade-scales/${created.id}/reset/`, { method });
      await onCreated();
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not save this grading scale.')));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="flex flex-wrap items-center gap-3 rounded-xl border border-dashed border-gray-200 bg-white px-4 py-3">
      <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
      <span className="text-xs text-gray-500">{t('No grading scale yet.')}</span>
      {error && <FormError message={error} />}
      {mayEdit && (
        <button type="button" onClick={() => void create()} disabled={busy} className={`${btnPrimary} ml-auto`}>
          {t('Create grading scale')}
        </button>
      )}
    </section>
  );
}
