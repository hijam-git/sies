"""The outbox and the templates behind it (docs/02 §4.9, docs/03 §19).

Two tables and no more, because docs/02 asked for exactly that: **one outbox
table and one adapter interface**. A message is a row before it is a request to
a gateway, and it stays a row afterwards carrying what the gateway said.

Why an outbox at all, rather than calling the gateway and logging the result:

* **Money leaves the institution on every row.** A guardian ringing to say the
  result SMS never arrived is answered from this table — what was sent, to which
  number, when, and what the provider's code was — or it is not answered at all.
* **Sending twice is the failure that matters.** Results go out to every
  guardian of a class at once; a second click must not mean a second SMS to four
  hundred people. The unique constraint below is what makes the send idempotent,
  the same way `fee_unique_per_student_category_period` makes the monthly job
  safe to run twice.
* **Delivery is asynchronous and fallible.** A task that dies mid-fan-out leaves
  the rows it had already written, so the retry can tell what is still owed.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BranchScopedModel


class NotificationEvent(models.TextChoices):
    """What happened that is worth telling somebody about.

    `docs/03` §19 lists six: fee_due, fee_received, absent, result_published,
    notice, admission. Only the result is wired up — the others are declared
    here because the template table is keyed by event, and an institution that
    writes its fee-reminder wording before the reminder exists has lost nothing.
    """

    RESULT_PUBLISHED = 'result_published', _('Result published · ফল প্রকাশ')
    FEE_DUE = 'fee_due', _('Fee due · ফি বকেয়া')
    FEE_RECEIVED = 'fee_received', _('Fee received · ফি জমা')
    ABSENT = 'absent', _('Absent · অনুপস্থিত')
    NOTICE = 'notice', _('Notice · নোটিশ')
    ADMISSION = 'admission', _('Admission · ভর্তি')


class NotificationChannel(models.TextChoices):
    """docs/03 §19's `channel`. SMS is the only one V1 delivers.

    Email is declared and not implemented on purpose: a guardian in a village
    has a phone number and no mailbox, which is the whole reason this module
    starts with SMS (docs/01 §4).
    """

    SMS = 'sms', _('SMS · এসএমএস')
    EMAIL = 'email', _('Email · ইমেইল')


class Language(models.TextChoices):
    BANGLA = 'bn', _('Bangla · বাংলা')
    ENGLISH = 'en', _('English · ইংরেজি')


class NotificationTemplate(BranchScopedModel):
    """What one event's message says, in one language, for one institution.

    Per branch rather than platform-wide because the wording is the
    institution's voice: a madrasah writes ফলাফল and a college writes Result,
    and neither should have to accept the other's. A branch that has written no
    template falls back to the built-in default in `services.DEFAULT_BODIES`,
    so SMS works on the day the feature is switched on and the template screen
    is an improvement rather than a prerequisite.
    """

    event = models.CharField(_('event · ঘটনা'), max_length=24,
                             choices=NotificationEvent.choices)
    channel = models.CharField(_('channel · মাধ্যম'), max_length=10,
                               choices=NotificationChannel.choices,
                               default=NotificationChannel.SMS)
    language = models.CharField(_('language · ভাষা'), max_length=2,
                                choices=Language.choices, default=Language.BANGLA)
    body = models.TextField(_('body · বার্তা'))
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('notification template · বার্তার নমুনা')
        verbose_name_plural = _('notification templates · বার্তার নমুনা')
        ordering = ['branch', 'event', 'language']
        constraints = [
            # One wording per (event, channel, language) per institution. Two
            # active templates for the same event would make which one a
            # guardian receives depend on row order.
            models.UniqueConstraint(
                fields=['branch', 'event', 'channel', 'language'],
                name='template_one_per_event_channel_language',
            ),
        ]

    def __str__(self):
        return f'{self.event} · {self.language} · {self.branch_id}'


class SmsStatus(models.TextChoices):
    """The life of one row.

    `SKIPPED` is a first-class outcome and not a failure: a student with no
    guardian phone on file is the commonest reason an SMS does not go, and the
    office needs to see that as a list of names to fix rather than as an error
    nobody can act on.
    """

    QUEUED = 'queued', _('Queued · সারিতে')
    SENT = 'sent', _('Sent · পাঠানো হয়েছে')
    FAILED = 'failed', _('Failed · ব্যর্থ')
    SKIPPED = 'skipped', _('Skipped · বাদ')


class SkipReason(models.TextChoices):
    NO_PHONE = 'no_phone', _('No phone number · ফোন নম্বর নেই')
    ALREADY_SENT = 'already_sent', _('Already sent · আগেই পাঠানো হয়েছে')
    SMS_OFF = 'sms_off', _('SMS is switched off · এসএমএস বন্ধ')


class SmsMessage(BranchScopedModel):
    """One message: what was sent, to whom, and what the gateway said back."""

    event = models.CharField(_('event · ঘটনা'), max_length=24,
                             choices=NotificationEvent.choices)

    #: What this message is ABOUT, as `<kind>:<id>` — `exam:12`. Together with
    #: the recipient it is the idempotency key, so "send the results" twice
    #: sends once. A plain FK cannot do this job: the next event is a fee
    #: reminder pointing at an invoice, and the one after a notice pointing at
    #: nothing, and three nullable FKs on an outbox row is three ways to be
    #: wrong about which one is set.
    reference = models.CharField(_('reference · সূত্র'), max_length=40, blank=True)

    #: Who it was about. SET_NULL for the usual audit reason (CLAUDE.md §4.2) —
    #: the record of an SMS having been sent must outlive a student row being
    #: deactivated, and it is PROTECTed from deletion elsewhere anyway.
    student = models.ForeignKey(
        'students.Student', verbose_name=_('student · শিক্ষার্থী'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='sms_messages',
    )
    #: Who it actually went to — a guardian, or the student themselves. Stored
    #: as a label rather than a second FK because the answer is printed on a
    #: screen ("father · 01711…") and never queried.
    recipient_label = models.CharField(_('recipient · প্রাপক'), max_length=80, blank=True)
    to_phone = models.CharField(_('phone · ফোন'), max_length=20, blank=True)

    body = models.TextField(_('body · বার্তা'))
    #: Billing arithmetic, computed at queue time by `parts.sms_parts()`. Stored
    #: rather than recomputed because the body may be edited on the template
    #: afterwards, and a bill has to match the message that was actually sent.
    parts = models.PositiveSmallIntegerField(_('parts · খণ্ড'), default=1)

    status = models.CharField(_('status · অবস্থা'), max_length=10,
                              choices=SmsStatus.choices, default=SmsStatus.QUEUED)
    skip_reason = models.CharField(_('skip reason · বাদ দেওয়ার কারণ'), max_length=20,
                                   choices=SkipReason.choices, blank=True)

    provider = models.CharField(_('provider · সরবরাহকারী'), max_length=20, blank=True)
    provider_code = models.CharField(_('provider code · কোড'), max_length=10, blank=True)
    provider_message = models.CharField(_('provider message · বার্তা'), max_length=200,
                                        blank=True)
    sent_at = models.DateTimeField(_('sent at · পাঠানোর সময়'), null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(_('attempts · চেষ্টা'), default=0)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('SMS message · এসএমএস')
        verbose_name_plural = _('SMS messages · এসএমএস')
        ordering = ['-created_at']
        constraints = [
            # **This is what makes a send safe to repeat.** One live message per
            # (event, reference, number): pressing "send results" twice, or a
            # retried task finishing a half-done fan-out, writes the rows that
            # are missing and skips the ones already there.
            #
            # Partial, on the two statuses that mean the message exists: a
            # FAILED row must not block a resend (the point of retrying), and a
            # SKIPPED one must not block the send that follows the office
            # putting the missing phone number on file.
            models.UniqueConstraint(
                fields=['branch', 'event', 'reference', 'to_phone'],
                condition=models.Q(status__in=['queued', 'sent']),
                name='sms_one_live_message_per_recipient',
            ),
        ]
        indexes = [
            # The outbox screen: this institution's messages, newest first.
            models.Index(fields=['branch', '-created_at'], name='sms_branch_recent'),
            # "Did this exam's results go out?" — the question the send screen
            # asks before it offers to send again.
            models.Index(fields=['branch', 'event', 'reference'], name='sms_branch_event_ref'),
        ]

    def __str__(self):
        return f'{self.event} → {self.to_phone} ({self.status})'
