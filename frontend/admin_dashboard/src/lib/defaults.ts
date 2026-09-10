/**
 * The defaults every picker on every screen should already be holding
 * (`CLAUDE.md` §7b).
 *
 * All of these are **pure derivations**, never state. A screen calls them on
 * the render path as `explicitChoice || obviousDefault || firstAsLastResort`,
 * so an explicit choice always wins and no second render is spent applying a
 * default the component could have worked out the first time.
 *
 * They live in `lib/` rather than beside one screen because the same three
 * questions — which exam, which class, which month — are asked by attendance,
 * exams, academics and reports, and four copies of "prefer the exam in marks
 * entry" is four places for the order to drift.
 */
import { useMemo } from 'react';
import type { AcademicClass, Exam, ExamStatus, Teacher } from './api';
import { useAuth } from './auth-context';
import { currentMonthInDhaka } from './timezone';

/**
 * How interesting an exam is to somebody who just opened Marks entry or
 * Results, worst first.
 *
 * `marks_entry` is the state that exists *because* marks are being typed, so it
 * wins outright. `ongoing` is next — papers are being sat, marks start today.
 * A `published` exam is finished business and a `draft` has no papers to enter
 * against, so both rank below a `scheduled` one that is at least coming.
 */
const EXAM_RANK: Record<ExamStatus, number> = {
  marks_entry: 4,
  ongoing: 3,
  scheduled: 2,
  published: 1,
  draft: 0,
};

/**
 * The exam a screen should open on: the one actually being worked on, and only
 * failing that the most recent.
 *
 * Never `exams[0]` — the list arrives newest-first by creation, and "whichever
 * row the API happened to put first" is an accident, not an answer.
 */
export function preferredExam(exams: Exam[]): Exam | undefined {
  let best: Exam | undefined;
  for (const exam of exams) {
    if (
      best === undefined
      || EXAM_RANK[exam.status] > EXAM_RANK[best.status]
      // Ties break on the later exam: within one status the interesting one is
      // the current term's, not last year's of the same name.
      || (EXAM_RANK[exam.status] === EXAM_RANK[best.status] && exam.starts_on > best.starts_on)
    ) {
      best = exam;
    }
  }
  return best;
}

/** `preferredExam` as the id a `<select value>` wants, or `''`. */
export function preferredExamId(exams: Exam[]): string {
  return String(preferredExam(exams)?.id ?? '');
}

/**
 * The `Teacher` id behind the signed-in account, or `null` for anyone who is
 * not a teacher.
 *
 * `class_teacher` and `in_charge` point at `staff.Teacher`, not at the user, and
 * the user payload carries no link to it — so the mapping needs a teacher list
 * the screen has **already** loaded. Pass none and this is `null`, which is the
 * honest answer: no backend call is worth one picker's default.
 */
export function useOwnTeacherId(teachers?: Teacher[]): number | null {
  const { user } = useAuth();
  return useMemo(() => {
    if (!user || user.user_type !== 'teacher' || !teachers) return null;
    return teachers.find((x) => x.user === user.id)?.id ?? null;
  }, [user, teachers]);
}

/**
 * The class a screen should open on.
 *
 * `/classes/` is already teacher-scoped server-side (`docs/08` D6), so a
 * teacher's list is only ever their own classes and any of them is a defensible
 * answer. Among those, the one they are *class teacher* of is the one they are
 * almost always there about — a class teacher's register, their own students —
 * so it comes first when the caller could tell us who they are.
 */
export function preferredClassId(classes: AcademicClass[], ownTeacherId: number | null): string {
  const own = ownTeacherId === null
    ? undefined
    : classes.find((c) => c.class_teacher === ownTeacherId);
  return String((own ?? classes[0])?.id ?? '');
}

/** `YYYY-MM-DD` for the first and last day of the current month in Dhaka —
 *  what a date range defaults to (§7b rule 5), never an empty pair. */
export function thisMonthRange(): { from: string; to: string } {
  const { year, month } = currentMonthInDhaka();
  const mm = String(month).padStart(2, '0');
  // Day 0 of the next month is the last day of this one, which is how February
  // and a leap year are handled without a table of month lengths.
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return { from: `${year}-${mm}-01`, to: `${year}-${mm}-${String(last).padStart(2, '0')}` };
}
