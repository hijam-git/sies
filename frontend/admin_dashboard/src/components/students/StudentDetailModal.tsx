import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Enrolment, StoredDocument, Student } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { normalizeBdPhone } from '../../lib/normalizeBdPhone';
import { formatDhakaDate } from '../../lib/timezone';
import BaseModal from '../common/BaseModal';
import Field, { FieldGrid, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls, selectCls } from '../common/styles';

/**
 * One student's whole record: who they are, who to call, where they have been,
 * and what paper the office holds.
 *
 * **The enrolment list IS the admission history.** There is no stored history
 * field anywhere in this system — a student's path through the institution is
 * the sequence of Enrolment rows, one per session, each carrying the class, the
 * section, the roll and the admission number issued at the time. Rendering it
 * from anything else would be inventing a second version of the truth.
 */

const DOC_TYPES = [
  { value: 'birth_certificate', label: 'Birth certificate' },
  { value: 'nid', label: 'NID' },
  { value: 'photo', label: 'Photograph' },
  { value: 'testimonial', label: 'Testimonial' },
  { value: 'transfer_certificate', label: 'Transfer certificate' },
  { value: 'marksheet', label: 'Marksheet' },
  { value: 'certificate', label: 'Certificate' },
  { value: 'other', label: 'Other' },
];

const RELATIONS = [
  { value: 'father', label: 'Father' },
  { value: 'mother', label: 'Mother' },
  { value: 'brother', label: 'Brother' },
  { value: 'other', label: 'Other' },
];

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5">
      <dt className="shrink-0 text-xs uppercase tracking-wide text-gray-400">{label}</dt>
      <dd className="min-w-0 text-right text-sm text-gray-900">{value || '—'}</dd>
    </div>
  );
}

export default function StudentDetailModal({
  studentId,
  sectionName,
  onClose,
  onChanged,
  onEdit,
}: {
  studentId: number;
  sectionName: (id: number | null) => string;
  onClose: () => void;
  onChanged: () => Promise<void>;
  onEdit: (student: Student) => void;
}) {
  const { t } = useT();
  const { can } = usePermissions();

  const [student, setStudent] = useState<Student | null>(null);
  const [enrolments, setEnrolments] = useState<Enrolment[]>([]);
  const [documents, setDocuments] = useState<StoredDocument[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [loginPhone, setLoginPhone] = useState('');
  const [loginResult, setLoginResult] = useState<string | null>(null);

  const [guardianName, setGuardianName] = useState('');
  const [guardianPhone, setGuardianPhone] = useState('');
  const [guardianRelation, setGuardianRelation] = useState('father');

  const [docType, setDocType] = useState('birth_certificate');
  const [docTitle, setDocTitle] = useState('');
  const [docFile, setDocFile] = useState<File | null>(null);

  const mayUpdate = can('students', 'update');
  const maySeeDocuments = can('documents', 'view');
  const mayUpload = can('documents', 'upload');

  const load = useCallback(async () => {
    setError(null);
    try {
      const [row, enrolmentRows] = await Promise.all([
        apiClient.retrieve<Student>('/students/', studentId),
        // Enrolments are gated on `admissions`, not `students` — somebody with
        // only `students.view` sees the profile and an empty history rather than
        // a failed screen.
        apiClient
          .listAll<Enrolment>('/enrolments/', `?student=${studentId}&ordering=-enrolled_on`)
          .catch(() => [] as Enrolment[]),
      ]);
      setStudent(row);
      // `?student=` is not one of the enrolment filterset's fields, so the
      // server ignores it and answers with the whole register. Narrowing here is
      // what makes the history this student's own.
      setEnrolments(enrolmentRows.filter((e) => e.student === studentId));
      if (maySeeDocuments) {
        setDocuments(
          await apiClient
            .listAll<StoredDocument>('/documents/', `?student=${studentId}`)
            .catch(() => [] as StoredDocument[]),
        );
      }
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not load this student.')));
    }
  }, [studentId, maySeeDocuments, t]);

  // Deferred by a tick rather than called from the effect body: `load` sets
  // state synchronously, which during an effect cascades a render before the
  // first paint. The same shape the other list screens use.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  const enableLogin = async () => {
    const canonical = normalizeBdPhone(loginPhone);
    if (!canonical) {
      setError(t('Enter an 11-digit mobile number, e.g. 01712345678.'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await apiClient.enableStudentLogin(studentId, canonical);
      setLoginResult(result.phone);
      setLoginPhone('');
      await load();
      await onChanged();
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not create a login for this student.')));
    } finally {
      setBusy(false);
    }
  };

  const addGuardian = async () => {
    if (!guardianName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient.addStudentGuardian(studentId, {
        name: guardianName.trim(),
        phone: normalizeBdPhone(guardianPhone) || guardianPhone.trim(),
        relation: guardianRelation,
        is_primary: (student?.guardians.length ?? 0) === 0,
      });
      setGuardianName('');
      setGuardianPhone('');
      await load();
      await onChanged();
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not save this guardian.')));
    } finally {
      setBusy(false);
    }
  };

  const uploadDocument = async () => {
    if (!docFile) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient.uploadDocument(docFile, {
        owner_type: 'student',
        student: String(studentId),
        doc_type: docType,
        title: docTitle.trim() || docFile.name,
      });
      setDocFile(null);
      setDocTitle('');
      await load();
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not upload this document.')));
    } finally {
      setBusy(false);
    }
  };

  return (
    <BaseModal
      isOpen
      onClose={onClose}
      title={student ? student.name_bn || student.name : t('Student')}
      maxWidth="4xl"
      footer={
        <div className="flex gap-2">
          <button type="button" onClick={onClose} className={`${btnSecondary} flex-1`}>
            {t('Close')}
          </button>
          {student && mayUpdate && (
            <button type="button" onClick={() => onEdit(student)} className={`${btnPrimary} flex-1`}>
              {t('Edit student')}
            </button>
          )}
        </div>
      }
    >
      <div className="space-y-5">
        <FormError message={error} />

        {!student ? (
          <p className="py-8 text-center text-sm text-gray-500">{t('Loading…')}</p>
        ) : (
          <>
            <section className="flex flex-col gap-4 sm:flex-row">
              {student.photo ? (
                <img
                  src={student.photo}
                  alt=""
                  className="h-24 w-24 shrink-0 rounded-lg object-cover"
                />
              ) : (
                <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-2xl text-gray-400">
                  {(student.name_bn || student.name).slice(0, 1)}
                </div>
              )}
              <dl className="min-w-0 flex-1 divide-y divide-gray-50">
                <Line label={t('Student ID')} value={student.student_id} />
                <Line label={t('Stream')} value={student.stream_name ?? ''} />
                <Line label={t('Status')} value={student.status_display} />
                <Line
                  label={t('Date of birth')}
                  value={student.date_of_birth ? formatDhakaDate(student.date_of_birth) : ''}
                />
                <Line label={t('Address')} value={student.full_address} />
                <Line label={t('Mobile')} value={student.phone} />
              </dl>
            </section>

            {/* ── Enable login (docs/08 D4) ─────────────────────────────── */}
            <section className="rounded-lg border border-gray-100 bg-gray-50 p-3">
              <h3 className="text-sm font-semibold text-gray-900">{t('Login')}</h3>
              {student.has_login ? (
                <p className="mt-1 text-sm text-gray-600">
                  {t('This student can sign in with')} {loginResult || student.phone}
                </p>
              ) : (
                <>
                  <p className="mt-1 text-xs leading-relaxed text-gray-500">
                    {t('Optional. Most students are admitted without a phone, so a login is an action on the record and never a step in admission.')}
                  </p>
                  {mayUpdate && (
                    <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                      <input
                        type="tel"
                        inputMode="numeric"
                        value={loginPhone}
                        onChange={(e) => setLoginPhone(e.target.value)}
                        placeholder="01712345678"
                        aria-label={t('Mobile')}
                        className={inputCls}
                      />
                      <button
                        type="button"
                        onClick={() => void enableLogin()}
                        disabled={busy || !loginPhone.trim()}
                        className={`${btnPrimary} sm:w-auto`}
                      >
                        {t('Enable login')}
                      </button>
                    </div>
                  )}
                </>
              )}
            </section>

            {/* ── Guardians ─────────────────────────────────────────────── */}
            <section>
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
                {t('Guardians')}
              </h3>
              <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
                {student.guardians.map((g) => (
                  <li key={g.id} className="flex items-center justify-between gap-3 px-3 py-2">
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-gray-900">{g.guardian_name}</span>
                      <span className="block text-xs text-gray-500">{t(g.relation)}</span>
                    </span>
                    <a href={`tel:${g.guardian_phone}`} className="shrink-0 font-mono text-sm text-blue-700">
                      {g.guardian_phone}
                    </a>
                  </li>
                ))}
                {student.guardians.length === 0 && (
                  <li className="px-3 py-4 text-center text-sm text-gray-500">{t('No guardian recorded.')}</li>
                )}
              </ul>

              {mayUpdate && (
                <div className="mt-3 space-y-3 rounded-lg border border-gray-100 bg-gray-50 p-3">
                  <FieldGrid>
                    <Field label={t('Name')} required>
                      <input
                        value={guardianName}
                        onChange={(e) => setGuardianName(e.target.value)}
                        className={inputCls}
                      />
                    </Field>
                    <Field label={t('Mobile')}>
                      <input
                        type="tel"
                        inputMode="numeric"
                        value={guardianPhone}
                        onChange={(e) => setGuardianPhone(e.target.value)}
                        className={inputCls}
                      />
                    </Field>
                    <Field
                      label={t('Relation')}
                      hint={t('A number already on file attaches this student to that guardian — which is how siblings share one record.')}
                    >
                      <select
                        value={guardianRelation}
                        onChange={(e) => setGuardianRelation(e.target.value)}
                        className={selectCls}
                      >
                        {RELATIONS.map((r) => (
                          <option key={r.value} value={r.value}>
                            {t(r.label)}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </FieldGrid>
                  <button
                    type="button"
                    onClick={() => void addGuardian()}
                    disabled={busy || !guardianName.trim()}
                    className={`${btnPrimary} w-full sm:w-auto`}
                  >
                    {t('Add guardian')}
                  </button>
                </div>
              )}
            </section>

            {/* ── Enrolment history = the admission history ─────────────── */}
            <section>
              <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-gray-500">
                {t('Enrolment history')}
              </h3>
              <p className="mb-2 text-xs text-gray-500">
                {t('One row per session — this is the admission history, not a separate record.')}
              </p>
              <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
                {enrolments.map((e) => (
                  <li key={e.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-gray-900">
                        {e.class_name}
                        {e.section !== null && ` · ${sectionName(e.section)}`}
                      </span>
                      <span className="block text-xs text-gray-500">
                        {t('Roll')} {e.roll ?? '—'} · {e.admission_number}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-gray-500">
                      {formatDhakaDate(e.enrolled_on)}
                    </span>
                  </li>
                ))}
                {enrolments.length === 0 && (
                  <li className="px-3 py-4 text-center text-sm text-gray-500">
                    {t('Not enrolled in any session yet.')}
                  </li>
                )}
              </ul>
            </section>

            {/* ── Documents ─────────────────────────────────────────────── */}
            {maySeeDocuments && (
              <section>
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
                  {t('Documents')}
                </h3>
                <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
                  {documents.map((d) => (
                    <li key={d.id} className="flex items-center justify-between gap-3 px-3 py-2">
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-gray-900">
                          {d.title || d.filename}
                        </span>
                        <span className="block text-xs text-gray-500">{d.doc_type_display}</span>
                      </span>
                      {/* A plain link, because the download endpoint checks the
                          branch and the permission on every request — the stored
                          file path is never exposed at all. */}
                      <a
                        href={d.download_url}
                        className="tap shrink-0 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700"
                      >
                        {t('Download')}
                      </a>
                    </li>
                  ))}
                  {documents.length === 0 && (
                    <li className="px-3 py-4 text-center text-sm text-gray-500">{t('No documents yet.')}</li>
                  )}
                </ul>

                {mayUpload && (
                  <div className="mt-3 space-y-3 rounded-lg border border-gray-100 bg-gray-50 p-3">
                    <FieldGrid>
                      <Field label={t('Document type')}>
                        <select value={docType} onChange={(e) => setDocType(e.target.value)} className={selectCls}>
                          {DOC_TYPES.map((d) => (
                            <option key={d.value} value={d.value}>
                              {t(d.label)}
                            </option>
                          ))}
                        </select>
                      </Field>
                      <Field label={t('Title')}>
                        <input value={docTitle} onChange={(e) => setDocTitle(e.target.value)} className={inputCls} />
                      </Field>
                      <Field label={t('File')}>
                        <input
                          type="file"
                          onChange={(e) => setDocFile(e.target.files?.[0] ?? null)}
                          className="w-full text-base text-gray-700 file:mr-3 file:min-h-[36px] file:rounded-lg file:border-0 file:bg-gray-200 file:px-3 file:text-sm"
                        />
                      </Field>
                    </FieldGrid>
                    <button
                      type="button"
                      onClick={() => void uploadDocument()}
                      disabled={busy || !docFile}
                      className={`${btnPrimary} w-full sm:w-auto`}
                    >
                      {t('Upload')}
                    </button>
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </BaseModal>
  );
}
