"""Sending a message, and deciding what it says (CLAUDE.md §4.3).

Everything that decides anything lives here: which number a student's result
goes to, what the message reads, whether it has been sent already, and what it
costs. `tasks.py` is a wrapper and `views.py` calls a service.

**The message is queued, never sent, on this side of the request.** A class of
forty is forty HTTP calls to a gateway in Dhaka, and the principal pressing
"send" must get an answer back in the time it takes to draw a screen. The
outbox row is written synchronously — so the count on screen is the truth — and
delivery happens in the worker.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.phone import normalize_bd_phone

from .models import (NotificationChannel, NotificationEvent, NotificationTemplate,
                     SkipReason, SmsMessage, SmsStatus)
from .parts import sms_parts

logger = logging.getLogger(__name__)

#: BDT, platform-wide. One symbol, one place.
TAKA = '৳'


# ─────────────────────────────────────────────────────────────────────────────
# What a message says
# ─────────────────────────────────────────────────────────────────────────────

#: The wording an institution gets before it writes its own. Bangla first,
#: because the guardian reading it is in a village in Kishoreganj and the
#: English version is the fallback, not the source (CLAUDE.md §8 rule 9).
#:
#: Kept SHORT on purpose: a Bengali SMS is Unicode, so 70 characters is one
#: part and 71 is two (see `parts.py`). Every placeholder that is not worth
#: doubling the institution's bill is left out of the default.
#:
#: **`{institution}` is one of them.** A real pair of names — মোহাম্মদ
#: আব্দুল্লাহ sitting অর্ধবার্ষিক পরীক্ষা — already spends sixty of the
#: seventy, and appending ঢাকা মাদ্রাসা took the default to 75 characters:
#: two parts, and every institution's results-day bill doubled by a line
#: nobody chose. The handset already says who it is from — that is what
#: `Branch.sms_sender_id` is — so the name is left to institutions that want
#: it and know what it costs. `test_parts.py` holds the default to one part
#: with a long name, so this cannot drift back.
DEFAULT_BODIES = {
    (NotificationEvent.RESULT_PUBLISHED, 'bn'): (
        '{student} ({roll}) — {exam}: {grade}, {result}'
    ),
    (NotificationEvent.RESULT_PUBLISHED, 'en'): (
        '{student} ({roll}) — {exam}: {grade}, {result}'
    ),
    # Admission. The two numbers the guardian will be asked for at every
    # counter from now on — the student id and the roll — and nothing else.
    (NotificationEvent.ADMISSION, 'bn'): (
        '{student} ভর্তি হয়েছে। আইডি {student_id}, রোল {roll}'
    ),
    (NotificationEvent.ADMISSION, 'en'): (
        '{student} admitted. ID {student_id}, roll {roll}'
    ),
    # A receipt. `{balance}` is the whole point of sending it: a guardian who
    # paid ৳500 of a ৳1,500 invoice in cash has the paper slip and nothing else
    # that says what is left, and that is what they ring the office to ask.
    (NotificationEvent.FEE_RECEIVED, 'bn'): (
        '{student}: {amount} জমা, বাকি {balance}। রসিদ {receipt}'
    ),
    (NotificationEvent.FEE_RECEIVED, 'en'): (
        '{student}: {amount} paid, {balance} due. Receipt {receipt}'
    ),
}

#: What a template writer may use, and what each one means. Served to the
#: template screen so the field list is not documentation somebody has to keep
#: in step by hand.
PLACEHOLDERS = {
    NotificationEvent.RESULT_PUBLISHED: [
        ('student', 'Student name · শিক্ষার্থীর নাম'),
        ('roll', 'Roll · রোল'),
        ('class', 'Class · শ্রেণি'),
        ('exam', 'Exam · পরীক্ষা'),
        ('grade', 'Grade · গ্রেড'),
        ('gpa', 'GPA · জিপিএ'),
        ('percentage', 'Percentage · শতকরা'),
        ('rank', 'Class rank · মেধাক্রম'),
        ('result', 'Passed or failed · উত্তীর্ণ/অকৃতকার্য'),
        ('institution', 'Institution name · প্রতিষ্ঠানের নাম'),
    ],
    NotificationEvent.ADMISSION: [
        ('student', 'Student name · শিক্ষার্থীর নাম'),
        ('student_id', 'Student ID · শিক্ষার্থী আইডি'),
        ('admission_no', 'Admission number · ভর্তি নম্বর'),
        ('roll', 'Roll · রোল'),
        ('class', 'Class · শ্রেণি'),
        ('session', 'Session · শিক্ষাবর্ষ'),
        ('institution', 'Institution name · প্রতিষ্ঠানের নাম'),
    ],
    NotificationEvent.FEE_RECEIVED: [
        ('student', 'Student name · শিক্ষার্থীর নাম'),
        ('amount', 'Amount paid · জমার পরিমাণ'),
        ('balance', 'Still owing on this invoice · এই বিলে বাকি'),
        ('receipt', 'Receipt number · রসিদ নম্বর'),
        ('head', 'What it was for · কিসের ফি'),
        ('period', 'Month, where the fee has one · মাস'),
        ('institution', 'Institution name · প্রতিষ্ঠানের নাম'),
    ],
}


class _Blank(dict):
    """A context where a placeholder nobody filled renders as nothing.

    `'{gpa}'.format_map(_Blank())` is `''` rather than a KeyError. The
    alternative is a template screen where one typo stops four hundred results
    going out, at the moment they were promised.
    """

    def __missing__(self, key):  # noqa: D105
        return ''


def render_body(body: str, context: dict) -> str:
    """Fill a template. Never raises on a bad placeholder (see `_Blank`)."""
    try:
        return (body or '').format_map(_Blank(context)).strip()
    except (ValueError, IndexError):
        # A stray brace — `{` with no closing pair. The institution's own text
        # is worth more than the formatting, so it goes out as typed.
        logger.warning('Unparseable template body, sending it verbatim')
        return (body or '').strip()


def body_for(branch, event, *, context, language=None):
    """The wording this institution uses for this event, filled in.

    Its own active template if it has written one, else the built-in default.
    The fallback is what makes SMS work on the day it is switched on rather
    than after somebody remembers to write six templates.
    """
    language = language or getattr(branch, 'default_language', 'bn') or 'bn'
    template = (
        NotificationTemplate.objects
        .filter(branch=branch, event=event, channel=NotificationChannel.SMS,
                language=language, is_active=True)
        .first()
    )
    raw = template.body if template else DEFAULT_BODIES.get(
        (event, language), DEFAULT_BODIES.get((event, 'bn'), ''),
    )
    return render_body(raw, context)


# ─────────────────────────────────────────────────────────────────────────────
# Who it goes to
# ─────────────────────────────────────────────────────────────────────────────

def recipient_for(student):
    """`(phone, label)` — the number a message about this student goes to.

    In order: the **primary** guardian, then any other guardian with a number,
    then the student's own phone (docs/08 D4 gives students a phone login, so
    an older madrasah student often has one and no guardian on file).

    `StudentGuardian.is_primary` exists precisely for this decision — docs/03
    §12 says a student can have a father and a local guardian "and the SMS
    knows which to use". Reading whichever row came back first is what that
    field was added to stop.
    """
    links = (
        student.guardian_links
        .select_related('guardian')
        .order_by('-is_primary', 'guardian__name')
    )
    for link in links:
        phone = normalize_bd_phone(getattr(link.guardian, 'phone', ''))
        if phone:
            relation = link.guardian.get_relation_display() if hasattr(
                link.guardian, 'get_relation_display') else ''
            name = link.guardian.name_bn or link.guardian.name
            return phone, f'{name} ({relation})' if relation else name

    own = normalize_bd_phone(getattr(student, 'phone', ''))
    if own:
        return own, student.name_bn or student.name
    return '', ''


# ─────────────────────────────────────────────────────────────────────────────
# Queueing
# ─────────────────────────────────────────────────────────────────────────────

def sms_is_on(branch) -> bool:
    """Whether this institution wants SMS at all.

    The platform's own switch is the gateway: an install with
    `SMS_PROVIDER=console` writes every message to the log and charges nobody,
    which is what dev, CI and a fresh production install all run on.
    """
    return bool(getattr(branch, 'sms_enabled', True))


@transaction.atomic
def queue_sms(*, branch, event, body, to_phone, reference='', student=None,
              recipient_label='', actor=None):
    """Write one outbox row and hand it to the worker.

    Returns the `SmsMessage`. It is a row in every outcome — including the ones
    that send nothing — because "why did Karim's father not get the result" is
    answered from this table, and an absence of rows answers nothing.
    """
    common = {
        'branch': branch, 'event': event, 'reference': reference,
        'student': student, 'recipient_label': recipient_label,
        'body': body, 'parts': sms_parts(body),
        'created_by': actor, 'updated_by': actor,
    }

    if not to_phone:
        return SmsMessage.objects.create(
            **common, to_phone='', status=SmsStatus.SKIPPED,
            skip_reason=SkipReason.NO_PHONE,
        )

    if not sms_is_on(branch):
        return SmsMessage.objects.create(
            **common, to_phone=to_phone, status=SmsStatus.SKIPPED,
            skip_reason=SkipReason.SMS_OFF,
        )

    try:
        # A savepoint, because the unique constraint below is expected to fire:
        # it is how "send the results twice" sends once. On Postgres an
        # IntegrityError poisons the enclosing transaction, so a fan-out of
        # forty students could not continue past the first duplicate without it.
        with transaction.atomic():
            message = SmsMessage.objects.create(
                **common, to_phone=to_phone, status=SmsStatus.QUEUED,
            )
    except IntegrityError:
        return SmsMessage.objects.create(
            **common, to_phone=to_phone, status=SmsStatus.SKIPPED,
            skip_reason=SkipReason.ALREADY_SENT,
        )

    # After the transaction commits, never inside it: the worker is faster than
    # the commit, and a task that reads the row before it exists fails for a
    # reason nobody can reproduce.
    from .tasks import deliver_sms
    transaction.on_commit(lambda: deliver_sms.delay(message.pk))
    return message


def deliver(message) -> bool:
    """Hand one queued row to the gateway and record what it said.

    Called by the Celery task. Returns True when the provider accepted it;
    False means the caller should retry, and the row already says why.
    """
    from .gateways import get_sms_gateway

    if message.status == SmsStatus.SENT:
        return True   # a retry of a task that had already succeeded

    gateway = get_sms_gateway()
    sender_id = (getattr(message.branch, 'sms_sender_id', '') or '').strip()
    result = gateway.send(to=message.to_phone, body=message.body, sender_id=sender_id)

    message.attempts += 1
    message.provider = gateway.name
    message.provider_code = (result.code or '')[:10]
    message.provider_message = (result.message or '')[:200]
    if result.success:
        message.status = SmsStatus.SENT
        message.sent_at = timezone.now()
    else:
        message.status = SmsStatus.FAILED
    message.save(update_fields=['attempts', 'provider', 'provider_code',
                                'provider_message', 'status', 'sent_at', 'updated_at'])
    return result.success


# ─────────────────────────────────────────────────────────────────────────────
# Results — the event this module was built for
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# The automatic events — admission and payment
# ─────────────────────────────────────────────────────────────────────────────
#
# Unlike the result, nobody presses a button for these: they ride on
# `admit_student()` and `collect_fee()`. Two consequences shape the code below.
#
# **They are opt-in per institution** (`Branch.sms_on_admission`,
# `sms_on_payment`, both default False). A send nobody asked for, happening on
# every admission and every receipt, is money leaving without a decision — and
# the only thing worse than a guardian not getting an SMS is an institution
# finding out from an invoice that it sent four thousand.
#
# **They must never break what they report.** `notify()` swallows everything: a
# gateway outage, a template that will not render, a column that moved. The
# payment is the money; the SMS is a courtesy about the money, and a courtesy
# does not get to roll back a receipt.

def notify(send, *args, **kwargs):
    """Run a sender and swallow whatever it raises, loudly in the log.

    The pattern is awliaa's — every order-SMS call there is wrapped for exactly
    this reason — and it is what lets these two hooks sit inside the money
    transactions at all.
    """
    try:
        return send(*args, **kwargs)
    except Exception:  # noqa: BLE001 — the whole point is that nothing escapes
        logger.exception('Notification failed; the action it reports stands')
        return None


def event_is_on(branch, event) -> bool:
    """Whether this institution has asked for this automatic event.

    The result SMS is not in the table below and never disabled here: it is
    pressed by a person who has already seen what it will cost.
    """
    if not sms_is_on(branch):
        return False
    field = {
        NotificationEvent.ADMISSION: 'sms_on_admission',
        NotificationEvent.FEE_RECEIVED: 'sms_on_payment',
    }.get(event)
    return True if field is None else bool(getattr(branch, field, False))


def send_admission_sms(*, student, enrolment, actor=None):
    """Tell the guardian the child is admitted, with the numbers they will be
    asked for at every counter from now on.

    Called from `students.services.admit_student()` **inside its transaction**,
    so an admission that rolls back takes the message with it: the outbox row
    and the student appear together or not at all.
    """
    branch = student.branch
    if not event_is_on(branch, NotificationEvent.ADMISSION):
        return None

    phone, label = recipient_for(student)
    academic_class = getattr(enrolment, 'academic_class', None)
    context = {
        'student': student.name_bn or student.name,
        'student_id': student.student_id,
        'admission_no': getattr(enrolment, 'admission_number', ''),
        'roll': getattr(enrolment, 'roll', ''),
        'class': (getattr(academic_class, 'name_bn', '')
                  or getattr(academic_class, 'name', '')),
        'session': str(getattr(enrolment, 'session', '') or ''),
        'institution': branch.name_bn or branch.name,
    }
    return queue_sms(
        branch=branch, event=NotificationEvent.ADMISSION,
        body=body_for(branch, NotificationEvent.ADMISSION, context=context),
        to_phone=phone, reference=f'student:{student.pk}',
        student=student, recipient_label=label, actor=actor,
    )


def send_payment_sms(payment, *, actor=None):
    """The receipt, on the guardian's phone.

    The reference is the **payment**, not the invoice: three instalments
    against one invoice are three receipts and three messages, and the
    idempotency key has to let all three through while still refusing to send
    the same receipt twice.
    """
    branch = payment.branch
    if not event_is_on(branch, NotificationEvent.FEE_RECEIVED):
        return None

    fee = payment.fee
    student = payment.student or fee.student
    phone, label = recipient_for(student)
    context = {
        'student': student.name_bn or student.name,
        'amount': f'{TAKA}{payment.amount:,.0f}',
        'balance': f'{TAKA}{fee.balance:,.0f}',
        'receipt': payment.receipt_no,
        'head': fee.category.name_bn or fee.category.name,
        'period': fee.period or '',
        'institution': branch.name_bn or branch.name,
    }
    return queue_sms(
        branch=branch, event=NotificationEvent.FEE_RECEIVED,
        body=body_for(branch, NotificationEvent.FEE_RECEIVED, context=context),
        to_phone=phone, reference=f'payment:{payment.pk}',
        student=student, recipient_label=label, actor=actor,
    )


def result_reference(exam) -> str:
    return f'exam:{exam.pk}'


def result_context(result, *, branch) -> dict:
    """The placeholders a result message can use.

    Read from the **frozen `Result` row**, not recomputed: the SMS a guardian
    keeps on their phone has to agree with the marksheet printed at the counter
    three years later, which is the property `Result` exists to give (docs/06
    #12).
    """
    enrolment = result.enrolment
    student = result.student
    academic_class = getattr(enrolment, 'academic_class', None)
    passed = 'উত্তীর্ণ' if result.is_passed else 'অকৃতকার্য'

    return {
        'student': student.name_bn or student.name,
        'roll': enrolment.roll if enrolment else '',
        'class': (getattr(academic_class, 'name_bn', '')
                  or getattr(academic_class, 'name', '')),
        'exam': result.exam.name_bn or result.exam.name,
        'grade': result.grade_bn or result.grade,
        'gpa': '' if result.gpa is None else f'{result.gpa}',
        'percentage': f'{result.percentage}',
        'rank': result.rank_in_class or '',
        'result': passed,
        'institution': branch.name_bn or branch.name,
    }


def result_recipients(exam, *, academic_class=None):
    """Every frozen result this send would cover, with its recipient resolved.

    Yields `(result, phone, label, context)`. A student with no number on file
    is yielded with an empty phone rather than dropped — the office needs the
    list of who to chase, and `queue_sms` records them as skipped.
    """
    from exams.models import Result

    results = (
        Result.objects
        .filter(exam=exam)
        .select_related('student', 'enrolment', 'enrolment__academic_class', 'exam')
        .prefetch_related('student__guardian_links__guardian')
    )
    if academic_class is not None:
        results = results.filter(enrolment__academic_class=academic_class)

    for result in results.order_by('enrolment__roll'):
        phone, label = recipient_for(result.student)
        yield result, phone, label, result_context(result, branch=exam.branch)


def preview_result_sms(exam, *, academic_class=None):
    """What the send screen shows BEFORE anything is sent.

    The principal is about to spend the institution's money on four hundred
    messages; they get the exact body of the first one, its length in parts, how
    many numbers are on file, and how many have already had this exam's result.
    """
    already = set(
        SmsMessage.objects
        .filter(branch=exam.branch, event=NotificationEvent.RESULT_PUBLISHED,
                reference=result_reference(exam),
                status__in=[SmsStatus.QUEUED, SmsStatus.SENT])
        .values_list('to_phone', flat=True)
    )

    sample, recipients, missing, duplicates, parts_total = '', 0, [], 0, 0
    for result, phone, _label, context in result_recipients(
            exam, academic_class=academic_class):
        body = body_for(exam.branch, NotificationEvent.RESULT_PUBLISHED, context=context)
        if not sample:
            sample = body
        if not phone:
            student = result.student
            missing.append({'student': student.pk,
                            'name': student.name_bn or student.name,
                            'roll': getattr(result.enrolment, 'roll', None)})
            continue
        if phone in already:
            duplicates += 1
            continue
        recipients += 1
        parts_total += sms_parts(body)

    return {
        'exam': exam.pk,
        'academic_class': getattr(academic_class, 'pk', None),
        'sample': sample,
        'recipients': recipients,
        'already_sent': duplicates,
        'missing_phone': missing,
        'parts_total': parts_total,
        'sms_enabled': sms_is_on(exam.branch),
        'sender_id': (getattr(exam.branch, 'sms_sender_id', '') or '').strip(),
    }


def send_result_sms(exam, *, academic_class=None, actor=None):
    """Queue this exam's results to the guardians. Safe to press twice.

    Refuses an unpublished exam: a result that is still being corrected is not
    one to put on four hundred handsets, and unlike a screen an SMS cannot be
    taken back (`exams.services.unpublish_exam` exists precisely because the
    screen can).
    """
    from exams.models import ExamStatus

    if exam.status != ExamStatus.PUBLISHED:
        raise ValueError('publish the results before sending them')

    queued = skipped_no_phone = already = 0
    for result, phone, label, context in result_recipients(
            exam, academic_class=academic_class):
        body = body_for(exam.branch, NotificationEvent.RESULT_PUBLISHED, context=context)
        message = queue_sms(
            branch=exam.branch, event=NotificationEvent.RESULT_PUBLISHED,
            body=body, to_phone=phone, reference=result_reference(exam),
            student=result.student, recipient_label=label, actor=actor,
        )
        if message.status == SmsStatus.QUEUED:
            queued += 1
        elif message.skip_reason == SkipReason.NO_PHONE:
            skipped_no_phone += 1
        elif message.skip_reason == SkipReason.ALREADY_SENT:
            already += 1

    logger.info('Result SMS for exam %s: queued=%d no_phone=%d already=%d',
                exam.pk, queued, skipped_no_phone, already)
    return {'queued': queued, 'missing_phone': skipped_no_phone, 'already_sent': already}
