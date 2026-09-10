import { useCallback, useEffect, useMemo, useState } from 'react';
import type { DragEvent, KeyboardEvent } from 'react';
import { apiClient } from '../../lib/api';
import type { AcademicClass, Session, SubjectAssignment, Subject, Teacher } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import Field, { FormError } from '../common/Field';
import Picker from '../common/Picker';

/**
 * Assignments — a board: drag a class or a subject onto the teacher who covers it.
 *
 * This screen is not a directory. With the institution's
 * `restrict_teachers_to_assigned_classes` setting on, these rows are the access
 * grant (`docs/08` D6): a teacher's attendance register, their student list and
 * their marks entry are all narrowed to the classes named here. The line of copy
 * at the top says exactly that, because an admin who reads this as a label will
 * wonder later why a teacher cannot open their own register.
 *
 * Two assignments, and they are not the same thing:
 *   • **class teacher** — owns the daily register for a class, and may correct a
 *     cell somebody else filled in. One per class: dropping the card on a second
 *     teacher MOVES it, because `AcademicClass.class_teacher` is a single FK.
 *   • **subject teacher** — period attendance for their own periods and marks for
 *     that subject only. A `SubjectAssignment` row per class × subject.
 * A teacher's reach is the union of the two.
 *
 * Three ways to do the same thing, because one input device is not a design:
 * drag on a desktop, **tap-to-pick then tap-a-teacher on a phone** (HTML5 drag
 * events do not fire on touch at all), and Space/Enter/Escape from the keyboard.
 * The pick-then-place model is what makes all three the same two steps.
 *
 * Writes are optimistic — the chip moves on the tap and the request follows. A
 * board that waits for a round trip before moving reads as broken on a phone on
 * 3G, and the failure path (put it back, say why) is one branch either way.
 */

/** A draggable piece of work. `key` is what the drag payload carries. */
type Card =
  | { kind: 'class'; key: string; classId: number; title: string; detail: string }
  | { kind: 'subject'; key: string; classId: number; subjectId: number; title: string; detail: string };

/** Where each card currently sits — teacher id, or null for unassigned. The
 *  subject row carries the server row id so a later unassign can DELETE it;
 *  null means the POST that creates it has not answered yet. */
type Placement = {
  classTeacher: Record<number, number | null>;
  subject: Record<number, { rowId: number | null; teacher: number } | undefined>;
};

export default function AssignmentsTab({
  sessions,
  classes,
  teachers,
}: {
  sessions: Session[];
  classes: AcademicClass[];
  teachers: Teacher[];
}) {
  const { t } = useT();
  const { can, canView } = usePermissions();

  const [sessionChoice, setSessionChoice] = useState('');
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [classRows, setClassRows] = useState<AcademicClass[]>([]);
  const [place, setPlace] = useState<Placement>({ classTeacher: {}, subject: {} });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Cards with a request in flight — the chip has already moved, so this only
   *  stops a second tap firing a second write against the same row. */
  const [busy, setBusy] = useState<Record<string, true>>({});
  /** The picked-up card, for tap and for the keyboard. Drag carries its own
   *  payload, but it sets this too so the highlight is one piece of state. */
  const [picked, setPicked] = useState<string | null>(null);
  const [hover, setHover] = useState<number | 'pool' | null>(null);
  const [announce, setAnnounce] = useState('');

  // The assignment IS the academic frame, so it is gated on `academics` and not
  // on `teachers`: whoever may edit the classes may say who teaches them. Same
  // check the form this replaced used — the board changed, the rule did not.
  const mayEdit = can('academics', 'update');
  const mayView = canView('academics');

  const sessionId =
    sessionChoice || String((sessions.find((s) => s.is_current) ?? sessions[0])?.id ?? '');

  // The prop list is the first paint; `classRows` replaces it once loaded, so a
  // class teacher set on this screen is not read back from a stale prop.
  const sessionClasses = useMemo(() => {
    const rows = classRows.length ? classRows : classes;
    return rows
      .filter((c) => String(c.session) === sessionId)
      .slice()
      .sort((a, b) => a.level_order - b.level_order || a.id - b.id);
  }, [classRows, classes, sessionId]);

  const load = useCallback(async () => {
    if (!sessionId) {
      setSubjects([]);
      setClassRows([]);
      setPlace({ classTeacher: {}, subject: {} });
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [classList, subjectRows, assignmentRows] = await Promise.all([
        apiClient.listAll<AcademicClass>('/classes/', `?session=${sessionId}&is_active=true`),
        apiClient.listAll<Subject>('/subjects/', '?is_active=true'),
        apiClient.listAll<SubjectAssignment>(
          '/subject-assignments/',
          `?session=${sessionId}&is_active=true`,
        ),
      ]);
      const classIds = new Set(classList.map((c) => c.id));
      const next: Placement = { classTeacher: {}, subject: {} };
      for (const c of classList) next.classTeacher[c.id] = c.class_teacher;
      for (const a of assignmentRows) {
        if (classIds.has(a.academic_class)) next.subject[a.subject] = { rowId: a.id, teacher: a.teacher };
      }
      setClassRows(classList);
      // `/subjects/` has no session filter — a subject hangs off a class, and
      // the class is what carries the session. Narrowing here rather than one
      // request per class keeps this to three round trips for the whole board.
      setSubjects(subjectRows.filter((s) => classIds.has(s.academic_class)));
      setPlace(next);
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not load the assignments.')));
    } finally {
      setLoading(false);
    }
  }, [sessionId, t]);

  // Deferred by a tick rather than called from the effect body: `load` sets
  // state synchronously, which during an effect cascades a render before the
  // first paint. The same shape the other list screens use.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  const className = (id: number) => {
    const c = sessionClasses.find((x) => x.id === id);
    return c ? c.name_bn || c.name : '';
  };

  const cards = useMemo<Card[]>(() => {
    const out: Card[] = [];
    for (const c of sessionClasses) {
      out.push({
        kind: 'class',
        key: `class:${c.id}`,
        classId: c.id,
        title: c.name_bn || c.name,
        detail: t('class teacher'),
      });
    }
    for (const s of subjects) {
      out.push({
        kind: 'subject',
        key: `subject:${s.id}`,
        classId: s.academic_class,
        subjectId: s.id,
        title: s.name_bn || s.name,
        detail: className(s.academic_class),
      });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionClasses, subjects, t]);

  const holderOf = useCallback(
    (card: Card): number | null =>
      card.kind === 'class'
        ? (place.classTeacher[card.classId] ?? null)
        : (place.subject[card.subjectId]?.teacher ?? null),
    [place],
  );

  const cardByKey = useMemo(() => {
    const m = new Map<string, Card>();
    for (const c of cards) m.set(c.key, c);
    return m;
  }, [cards]);

  const unplaced = cards.filter((c) => holderOf(c) === null);
  const byTeacher = useMemo(() => {
    const m = new Map<number, Card[]>();
    for (const c of cards) {
      const holder = holderOf(c);
      if (holder === null) continue;
      const list = m.get(holder) ?? [];
      list.push(c);
      m.set(holder, list);
    }
    return m;
  }, [cards, holderOf]);

  const teacherName = (id: number) => {
    const x = teachers.find((y) => y.id === id);
    return x ? x.name_bn || x.name : '';
  };

  const cardLabel = (card: Card) =>
    card.kind === 'class' ? `${card.title} — ${t('class teacher')}` : `${card.detail} · ${card.title}`;

  // ── Writes ───────────────────────────────────────────────────────────────
  // Each one moves the chip first and reconciles after. `before` is the exact
  // slice being changed, so a failure restores that one card and leaves every
  // other optimistic move on the board alone.

  const runWrite = async (card: Card, apply: (p: Placement) => Placement, send: () => Promise<void>) => {
    const before = place;
    setBusy((b) => ({ ...b, [card.key]: true }));
    setError(null);
    setPlace(apply);
    try {
      await send();
    } catch (err) {
      setPlace(before);
      setError(apiErrorText(err, t, t('Could not save this assignment.')));
      setAnnounce(t('That did not save — the card went back.'));
    } finally {
      setBusy((b) => {
        const next = { ...b };
        delete next[card.key];
        return next;
      });
    }
  };

  const assign = async (card: Card, teacherId: number) => {
    if (!mayEdit || busy[card.key]) return;
    const previous = holderOf(card);
    if (previous === teacherId) {
      setPicked(null);
      return;
    }
    setPicked(null);
    setAnnounce(
      previous === null
        ? `${cardLabel(card)} → ${teacherName(teacherId)}`
        : `${cardLabel(card)}: ${teacherName(previous)} → ${teacherName(teacherId)}`,
    );

    if (card.kind === 'class') {
      await runWrite(
        card,
        (p) => ({ ...p, classTeacher: { ...p.classTeacher, [card.classId]: teacherId } }),
        async () => {
          // One FK, so this is a move and not a second grant — the previous
          // class teacher loses the class in the same write.
          await apiClient.patch<AcademicClass>('/classes/', card.classId, { class_teacher: teacherId });
        },
      );
      return;
    }

    const existing = place.subject[card.subjectId];
    await runWrite(
      card,
      (p) => ({
        ...p,
        subject: { ...p.subject, [card.subjectId]: { rowId: existing?.rowId ?? null, teacher: teacherId } },
      }),
      async () => {
        if (existing && existing.rowId !== null) {
          await apiClient.patch<SubjectAssignment>('/subject-assignments/', existing.rowId, {
            teacher: teacherId,
          });
        } else {
          const row = await apiClient.create<SubjectAssignment>('/subject-assignments/', {
            session: Number(sessionId),
            academic_class: card.classId,
            subject: card.subjectId,
            teacher: teacherId,
            section: null,
            is_active: true,
          });
          // The optimistic entry had no row id; a later unassign needs one.
          setPlace((p) => ({
            ...p,
            subject: { ...p.subject, [card.subjectId]: { rowId: row.id, teacher: teacherId } },
          }));
        }
      },
    );
  };

  const unassign = async (card: Card) => {
    if (!mayEdit || busy[card.key]) return;
    const previous = holderOf(card);
    if (previous === null) return;
    setPicked(null);
    setAnnounce(`${cardLabel(card)} → ${t('Nobody yet')}`);

    if (card.kind === 'class') {
      await runWrite(
        card,
        (p) => ({ ...p, classTeacher: { ...p.classTeacher, [card.classId]: null } }),
        async () => {
          await apiClient.patch<AcademicClass>('/classes/', card.classId, { class_teacher: null });
        },
      );
      return;
    }

    const existing = place.subject[card.subjectId];
    await runWrite(
      card,
      (p) => ({ ...p, subject: { ...p.subject, [card.subjectId]: undefined } }),
      async () => {
        // Deleting the row rather than blanking the teacher: an assignment with
        // no teacher is an access grant to nobody, which the model cannot
        // express and the D6 scope query would read as a class with a hole.
        if (existing?.rowId != null) await apiClient.destroy('/subject-assignments/', existing.rowId);
      },
    );
  };

  // ── Input paths ──────────────────────────────────────────────────────────

  const pick = (card: Card) => {
    if (!mayEdit) return;
    if (picked === card.key) {
      setPicked(null);
      setAnnounce(t('Cancelled.'));
      return;
    }
    setPicked(card.key);
    setAnnounce(`${cardLabel(card)} — ${t('picked up. Choose a teacher.')}`);
  };

  const onCardKey = (e: KeyboardEvent, card: Card) => {
    if (e.key === 'Escape') {
      setPicked(null);
      return;
    }
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      pick(card);
    }
  };

  const onDropTeacher = (e: DragEvent, teacherId: number) => {
    e.preventDefault();
    setHover(null);
    const key = e.dataTransfer.getData('text/plain') || picked;
    const card = key ? cardByKey.get(key) : undefined;
    if (card) void assign(card, teacherId);
  };

  const onDropPool = (e: DragEvent) => {
    e.preventDefault();
    setHover(null);
    const key = e.dataTransfer.getData('text/plain') || picked;
    const card = key ? cardByKey.get(key) : undefined;
    if (card) void unassign(card);
  };

  const pickedCard = picked ? cardByKey.get(picked) : undefined;

  // Escape cancels wherever focus happens to be — a picked card whose chip has
  // just re-rendered elsewhere may no longer hold it.
  useEffect(() => {
    if (!picked) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') setPicked(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [picked]);

  if (!mayView) {
    return (
      <p className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
        {t('You do not have permission to do this.')}
      </p>
    );
  }

  const subjectTotal = subjects.length;
  const subjectAssigned = subjects.filter((s) => place.subject[s.id]).length;
  const withoutClassTeacher = sessionClasses.filter((c) => !place.classTeacher[c.id]);

  const dragProps = (card: Card) =>
    mayEdit
      ? {
          draggable: true,
          onDragStart: (e: DragEvent) => {
            e.dataTransfer.setData('text/plain', card.key);
            e.dataTransfer.effectAllowed = 'move';
            setPicked(card.key);
          },
          onDragEnd: () => {
            setHover(null);
            setPicked(null);
          },
        }
      : {};

  /** The card as it sits in the pool, and the same card as a chip on a teacher.
   *  One renderer, so the two never drift apart in what they let you do. */
  const renderCard = (card: Card, onTeacher: boolean) => {
    const isPicked = picked === card.key;
    const isBusy = !!busy[card.key];
    const tone =
      card.kind === 'class'
        ? 'border-amber-200 bg-amber-50 text-amber-900'
        : 'border-blue-200 bg-blue-50 text-blue-900';
    return (
      <div
        key={card.key}
        {...dragProps(card)}
        role={mayEdit ? 'button' : undefined}
        tabIndex={mayEdit ? 0 : undefined}
        aria-grabbed={mayEdit ? isPicked : undefined}
        aria-label={cardLabel(card)}
        onClick={(e) => {
          // With a card in hand the whole teacher card is the drop zone,
          // chips included — at 360px a teacher's card is mostly chips, and a
          // tap that lands on one and quietly swaps what you were holding is
          // the bug this screen exists to avoid. Otherwise the chip is its own
          // control and must not also drop whatever the teacher card would.
          if (onTeacher && picked && picked !== card.key) return;
          e.stopPropagation();
          pick(card);
        }}
        onKeyDown={(e) => {
          if (onTeacher && picked && picked !== card.key) return;
          e.stopPropagation();
          onCardKey(e, card);
        }}
        className={[
          'flex min-h-[44px] items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm',
          tone,
          mayEdit ? 'cursor-pointer touch-manipulation' : '',
          isPicked ? 'ring-2 ring-offset-1 ring-blue-500 shadow-md' : '',
          isBusy ? 'opacity-60' : '',
        ].join(' ')}
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">{card.title}</span>
          <span className="block truncate text-xs opacity-75">{card.detail}</span>
        </span>
        {onTeacher && mayEdit && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              void unassign(card);
            }}
            aria-label={`${t('Remove')} — ${cardLabel(card)}`}
            className="tap -mr-2 shrink-0 rounded-md text-lg leading-none opacity-70 hover:opacity-100"
          >
            ×
          </button>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <p className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm leading-relaxed text-blue-900">
        {t('An assignment is what a teacher can reach: attendance and marks are limited to the classes named here.')}
      </p>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t('Session')}>
          <Picker
            value={sessionId}
            onChange={setSessionChoice}
            options={sessions.map((s) => ({ value: String(s.id), label: s.name }))}
          />
        </Field>
      </div>

      {error && <FormError message={error} />}

      <div className="flex flex-wrap gap-2 text-xs">
        <span className="rounded-full bg-blue-50 px-3 py-1.5 font-medium text-blue-900">
          {`${t('Subjects')}: ${subjectAssigned} / ${subjectTotal} ${t('assigned')}`}
        </span>
        <span
          className={`rounded-full px-3 py-1.5 font-medium ${
            withoutClassTeacher.length
              ? 'bg-amber-50 text-amber-900'
              : 'bg-green-50 text-green-800'
          }`}
        >
          {withoutClassTeacher.length
            ? `${t('No class teacher yet')}: ${withoutClassTeacher.map((c) => c.name_bn || c.name).join(', ')}`
            : t('Every class has a class teacher.')}
        </span>
      </div>

      {mayEdit && (
        <p className="text-xs text-gray-500">
          {t('Drag a card onto a teacher — or tap the card, then tap the teacher.')}
        </p>
      )}

      {/* The picked card follows the screen on a phone, so the teacher list can
          be scrolled without losing sight of what is in hand. */}
      {pickedCard && (
        <div className="sticky top-2 z-20 flex items-center gap-3 rounded-lg border border-blue-300 bg-white px-3 py-2 shadow-md">
          <span className="min-w-0 flex-1 truncate text-sm text-gray-900">
            <span className="font-medium">{cardLabel(pickedCard)}</span>
            <span className="block text-xs text-gray-500">{t('Now tap a teacher.')}</span>
          </span>
          <button type="button" onClick={() => setPicked(null)} className="tap px-2 text-sm text-gray-600">
            {t('Cancel')}
          </button>
        </div>
      )}

      <p aria-live="polite" className="sr-only">
        {announce}
      </p>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <section
          onDragOver={(e) => {
            if (!mayEdit) return;
            e.preventDefault();
            setHover('pool');
          }}
          onDragLeave={() => setHover((h) => (h === 'pool' ? null : h))}
          onDrop={onDropPool}
          className={`rounded-xl border bg-white p-4 shadow-sm ${
            hover === 'pool' ? 'border-blue-400 ring-2 ring-blue-200' : 'border-gray-100'
          }`}
        >
          <h3 className="text-sm font-semibold text-gray-900">{t('Unassigned work')}</h3>
          <p className="mb-3 mt-1 text-xs text-gray-500">{t('Nobody covers these yet.')}</p>
          {unplaced.length === 0 ? (
            <p className="py-6 text-center text-sm text-gray-500">
              {loading ? t('Loading…') : t('Everything is assigned.')}
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1">
              {unplaced.map((c) => renderCard(c, false))}
            </div>
          )}
        </section>

        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-gray-900">{t('Teachers')}</h3>
          {teachers.length === 0 ? (
            <p className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
              {loading ? t('Loading…') : t('No teachers yet.')}
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {teachers.map((teacher) => {
                const held = byTeacher.get(teacher.id) ?? [];
                const isTarget = hover === teacher.id;
                return (
                  <div
                    key={teacher.id}
                    data-teacher={teacher.id}
                    role={mayEdit ? 'button' : undefined}
                    tabIndex={mayEdit ? 0 : undefined}
                    aria-dropeffect={mayEdit && picked ? 'move' : undefined}
                    aria-label={`${teacher.name_bn || teacher.name}${picked ? ` — ${t('assign here')}` : ''}`}
                    onDragOver={(e) => {
                      if (!mayEdit) return;
                      e.preventDefault();
                      e.dataTransfer.dropEffect = 'move';
                      setHover(teacher.id);
                    }}
                    onDragLeave={() => setHover((h) => (h === teacher.id ? null : h))}
                    onDrop={(e) => onDropTeacher(e, teacher.id)}
                    onClick={() => {
                      const card = picked ? cardByKey.get(picked) : undefined;
                      if (card) void assign(card, teacher.id);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Escape') return setPicked(null);
                      if (e.key !== ' ' && e.key !== 'Enter') return;
                      e.preventDefault();
                      const card = picked ? cardByKey.get(picked) : undefined;
                      if (card) void assign(card, teacher.id);
                    }}
                    className={[
                      'rounded-xl border p-4 shadow-sm transition-colors',
                      isTarget || (picked && mayEdit)
                        ? 'border-blue-400 ring-2 ring-blue-200'
                        : 'border-gray-100',
                      // Not `bg-white` in the base and `bg-blue-50` here: two
                      // utilities of equal specificity are decided by their
                      // order in the stylesheet, not in the attribute, so the
                      // highlight would silently never win.
                      isTarget ? 'bg-blue-50' : 'bg-white',
                      mayEdit ? 'cursor-pointer' : '',
                    ].join(' ')}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold text-gray-900">
                          {teacher.name_bn || teacher.name}
                        </span>
                        <span className="block truncate text-xs text-gray-500">
                          {teacher.designation || t('Teacher')}
                        </span>
                      </span>
                      <span className="shrink-0 text-xs text-gray-400">{held.length}</span>
                    </div>

                    {picked && mayEdit && (
                      <p className="mt-2 rounded-md bg-blue-50 px-2 py-1 text-center text-xs font-medium text-blue-700">
                        {t('assign here')}
                      </p>
                    )}

                    <div className="mt-3 space-y-2">
                      {held.length === 0 ? (
                        <p className="text-xs text-gray-400">{t('Nothing assigned yet.')}</p>
                      ) : (
                        held.map((c) => renderCard(c, true))
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
