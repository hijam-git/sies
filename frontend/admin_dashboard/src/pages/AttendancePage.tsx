import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient } from '../lib/api';
import type { AcademicClass, Period, Section, Subject } from '../lib/api';
import { usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { useTabParam } from '../lib/useTabParam';
import TabStrip from '../components/common/TabStrip';
import type { TabDef } from '../components/common/TabStrip';
import MonthRegisterTab from '../components/attendance/MonthRegisterTab';
import ClassAttendanceTab from '../components/attendance/ClassAttendanceTab';

/**
 * Attendance — the month register, and the per-period roster.
 *
 * The two are not variants of one screen; they are the two paths of `docs/08`
 * D7. An institution that takes attendance once a day lives in the register and
 * never opens the second tab; one that takes it per period arrives at the
 * second from the teacher's day board and never opens the first.
 *
 * **The class picker is the access model made visible** (`docs/08` D6). The
 * list comes from `/classes/`, which is teacher-scoped on the server, so a
 * teacher simply sees their own classes — the restriction reads as a shorter
 * list rather than as an error on a class they should not have been offered.
 */

type Tab = 'register' | 'class';

const TABS: Tab[] = ['register', 'class'];

export default function AttendancePage() {
  const { t } = useT();
  const { canView } = usePermissions();
  const [tab, setTab] = useTabParam<Tab>(TABS, 'register');
  const [params] = useSearchParams();

  const [classes, setClasses] = useState<AcademicClass[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [periods, setPeriods] = useState<Period[]>([]);

  const mayView = canView('attendance');

  /** Sections and subjects are fetched per class and kept, so switching back to
   *  a class already looked at costs nothing. */
  const fetched = useRef(new Set<string>());

  const loadForClass = useCallback((classId: string) => {
    if (!classId || fetched.current.has(classId)) return;
    fetched.current.add(classId);
    void apiClient
      .listAll<Section>('/sections/', `?academic_class=${classId}&is_active=true`)
      .then((rows) => setSections((prev) => [...prev.filter((s) => String(s.academic_class) !== classId), ...rows]))
      .catch(() => undefined);
    void apiClient
      .listAll<Subject>('/subjects/', `?academic_class=${classId}&is_active=true`)
      .then((rows) => setSubjects((prev) => [...prev.filter((s) => String(s.academic_class) !== classId), ...rows]))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!mayView) return;
    void apiClient
      .listAll<AcademicClass>('/classes/', '?is_active=true')
      .then(setClasses)
      .catch(() => setClasses([]));
    // The bell schedule. A missing `academics.view` leaves the period picker
    // empty rather than breaking the page — the register does not need it.
    void apiClient
      .listAll<Period>('/periods/', '?is_active=true&ordering=order')
      .then(setPeriods)
      .catch(() => setPeriods([]));
  }, [mayView]);

  if (!mayView) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Attendance')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  const tabs: TabDef<Tab>[] = [
    { key: 'register', label: t('Month register') },
    { key: 'class', label: t('Class attendance') },
  ];

  // The day board links here with the period it wants already chosen, so the
  // teacher lands on the roster rather than on four pickers.
  const initial = params.get('class')
    ? {
        academicClass: params.get('class') ?? '',
        section: params.get('section') ?? '',
        period: params.get('period') ?? '',
        subject: params.get('subject') ?? '',
      }
    : null;

  return (
    <div className="space-y-3">
      <TabStrip tabs={tabs} active={tab} onChange={setTab} heading={t('Attendance')} />

      {tab === 'register' && (
        <MonthRegisterTab classes={classes} sections={sections} onSectionsNeeded={loadForClass} />
      )}
      {tab === 'class' && (
        <ClassAttendanceTab
          classes={classes}
          sections={sections}
          periods={periods}
          subjects={subjects}
          onSectionsNeeded={loadForClass}
          initial={initial}
        />
      )}
    </div>
  );
}
