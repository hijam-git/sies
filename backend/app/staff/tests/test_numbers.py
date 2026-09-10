"""Number issuing — gapless, unique, and correct under concurrency.

CLAUDE.md §8 lists receipt-number concurrency as one of the six things tests are
*required* for, and this is that mechanism: `next_number()` is what every
sequence in the project — admission numbers, rolls, receipts, vouchers — is built
on. `max() + 1` passes every single-threaded test ever written and double-issues
the first time two clerks work at once.
"""

import threading

from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase

from core.models import NumberSequence
from staff.models import Teacher
from staff.services import generate_employee_id, generate_teacher_id, next_number

from .factories import make_branch


class SequenceTests(TestCase):
    def setUp(self):
        self.branch = make_branch(code='DHK')

    def test_numbers_start_at_one_and_have_no_gaps(self):
        with transaction.atomic():
            issued = [
                next_number(branch=self.branch, kind=NumberSequence.Kind.ADMISSION,
                            scope='7')[0]
                for _ in range(5)
            ]
        self.assertEqual(issued, [1, 2, 3, 4, 5])

    def test_each_scope_counts_independently(self):
        """Admission numbers reset per session, so session 7 and session 8 are
        two counters and neither one's numbering depends on the other."""
        with transaction.atomic():
            first, _ = next_number(branch=self.branch,
                                   kind=NumberSequence.Kind.ADMISSION, scope='7')
            other, _ = next_number(branch=self.branch,
                                   kind=NumberSequence.Kind.ADMISSION, scope='8')
        self.assertEqual((first, other), (1, 1))

    def test_each_branch_counts_independently(self):
        other_branch = make_branch(code='CTG', name='Chittagong Madrasah')
        with transaction.atomic():
            mine, _ = next_number(branch=self.branch,
                                  kind=NumberSequence.Kind.ADMISSION, scope='7')
            theirs, _ = next_number(branch=other_branch,
                                    kind=NumberSequence.Kind.ADMISSION, scope='7')
        self.assertEqual((mine, theirs), (1, 1))

    def test_only_one_counter_row_is_ever_created(self):
        with transaction.atomic():
            for _ in range(3):
                next_number(branch=self.branch,
                            kind=NumberSequence.Kind.ADMISSION, scope='7')

        rows = NumberSequence.objects.filter(
            branch=self.branch, kind=NumberSequence.Kind.ADMISSION, scope='7',
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().last_number, 3)

    def test_teacher_and_employee_ids_are_formatted_for_a_human(self):
        self.assertEqual(generate_teacher_id(self.branch), 'TCH-DHK-0001')
        self.assertEqual(generate_employee_id(self.branch), 'EMP-DHK-0001')

    def test_the_two_staff_counters_do_not_share_a_row(self):
        generate_teacher_id(self.branch)
        generate_teacher_id(self.branch)
        self.assertEqual(generate_employee_id(self.branch), 'EMP-DHK-0001')


class ConcurrentIssueTests(TransactionTestCase):
    """The case `max() + 1` gets wrong.

    `TransactionTestCase` and not `TestCase`: the threads below open their own
    connections, and a `TestCase`'s outer transaction would hide the fixture from
    every one of them. Real connections also mean `SELECT … FOR UPDATE` actually
    blocks, which is the whole thing being tested.
    """

    # `reset_sequences` is not set: nothing here asserts on primary keys.
    available_apps = None

    def test_eight_threads_issue_eight_distinct_consecutive_ids(self):
        branch = make_branch(code='DHK')
        issued = []
        lock = threading.Lock()
        ready = threading.Barrier(8)

        def issue():
            try:
                # Every thread waits for the others before touching the counter,
                # so they contend rather than politely queueing by startup time.
                ready.wait(timeout=10)
                teacher_id = generate_teacher_id(branch)
                with lock:
                    issued.append(teacher_id)
            finally:
                # Django opens a connection per thread and does not close it;
                # leaving them open makes the test database undroppable.
                connections.close_all()

        threads = [threading.Thread(target=issue) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(len(issued), 8)
        # Distinct AND gapless: eight ids, 0001 through 0008, in some order.
        self.assertEqual(
            sorted(issued),
            [f'TCH-DHK-{n:04d}' for n in range(1, 9)],
        )

    def test_a_failed_write_does_not_burn_a_number(self):
        """The reservation and the row it belongs to commit or roll back together.

        This is why `next_number()` must be called inside the caller's
        transaction: a number reserved by a save that then failed would leave a
        hole, and gapless is the requirement.
        """
        branch = make_branch(code='CTG', name='Chittagong Madrasah')

        try:
            with transaction.atomic():
                number, _ = next_number(branch=branch,
                                        kind=NumberSequence.Kind.TEACHER, width=4)
                self.assertEqual(number, 1)
                raise RuntimeError('the enrolment failed after the number was taken')
        except RuntimeError:
            pass

        self.assertEqual(generate_teacher_id(branch), 'TCH-CTG-0001')
        connection.close()

    def test_teacher_ids_are_globally_unique_at_the_database(self):
        branch = make_branch(code='DHK')
        Teacher.objects.create(branch=branch, name='First', teacher_id='TCH-DHK-0001')

        with self.assertRaises(Exception):
            with transaction.atomic():
                Teacher.objects.create(branch=branch, name='Second',
                                       teacher_id='TCH-DHK-0001')
