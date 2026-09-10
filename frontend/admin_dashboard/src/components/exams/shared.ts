import type { AcademicClass, Exam, ExamStatus, ExamType, Session, Stream, Subject, Teacher } from '../../lib/api';

/** What the three exam tabs all need, fetched once by the page. */
export interface ExamsData {
  sessions: Session[];
  streams: Stream[];
  classes: AcademicClass[];
  teachers: Teacher[];
  exams: Exam[];
  reloadExams: () => Promise<void>;
  /** Subjects arrive per class and are cached by the page — the marks grid and
   *  the schedule both ask for the same list. */
  subjectsFor: (classId: string) => Subject[];
  loadSubjects: (classId: string) => void;
}

/** English source strings; the screens run them through `t()`. */
export const EXAM_TYPES: { value: ExamType; label: string }[] = [
  { value: 'monthly', label: 'Monthly' },
  { value: 'half_yearly', label: 'Half-yearly' },
  { value: 'annual', label: 'Annual' },
  { value: 'test', label: 'Test' },
  // The two madrasah forms (`docs/08` D1): the daily lesson examination, and
  // the external board exam whose marks are only recorded here.
  { value: 'sabaq', label: 'Sabaq' },
  { value: 'board', label: 'Board' },
];

export const EXAM_STATUS_LABEL: Record<ExamStatus, string> = {
  draft: 'Draft',
  scheduled: 'Scheduled',
  ongoing: 'Ongoing',
  marks_entry: 'Marks entry',
  published: 'Published',
};

export const EXAM_STATUS_CLASS: Record<ExamStatus, string> = {
  draft: 'bg-gray-100 text-gray-600',
  scheduled: 'bg-blue-50 text-blue-700',
  ongoing: 'bg-blue-100 text-blue-800',
  marks_entry: 'bg-amber-100 text-amber-800',
  published: 'bg-green-100 text-green-700',
};

export function examLabel(exam: Exam | undefined): string {
  if (!exam) return '';
  return exam.name_bn || exam.name;
}

export function classLabel(row: AcademicClass | undefined): string {
  if (!row) return '';
  return row.name_bn || row.name;
}

export function subjectLabel(row: Subject | undefined): string {
  if (!row) return '';
  return row.name_bn || row.name;
}

/** `"78.50"` → `"78.5"`, and null → `""`. Marks are typed, so a stored
 *  `78.50` must not come back into the box as something the teacher has to
 *  edit around. */
export function marksInputValue(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '';
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return String(n);
}
