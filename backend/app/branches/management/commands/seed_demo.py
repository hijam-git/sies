"""Build one complete institution that exercises the whole yearly loop.

This is the demo an owner opens to judge the system by using it, so it is not a
handful of rows — it is a madrasah that has actually been running: classes with
timetables, teachers assigned to them, students enrolled with guardians and
addresses, a month of attendance already marked, fees raised with some paid and
some overdue, an exam with marks, and applications waiting at every stage so the
printed admission form has something real to print.

**Not for tests to depend on** (`CLAUDE.md` §4a). Tests build their own small
fixtures; a shared demo dataset that tests assert against becomes a thing nobody
dares change. This exists so a person can look at the app.

Idempotent. Everything is `get_or_create` on a natural key, so re-running fills
gaps and never duplicates. The counts it prints are what it *created*, so a
second run printing zeros is the correct output, not a failure.
"""

import datetime as dt
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

CODE = 'DEMO'
PASSWORD = 'sies@2026'

# A fixed seed, so two people running this see the same madrasah and can talk
# about "Abdullah in Class 5" and mean the same student.
RNG = random.Random(1447)

FIRST_NAMES = [
    ('Abdullah', 'আব্দুল্লাহ'), ('Bilal', 'বিলাল'), ('Umar', 'উমর'),
    ('Yusuf', 'ইউসুফ'), ('Ibrahim', 'ইব্রাহিম'), ('Hamza', 'হামজা'),
    ('Musa', 'মুসা'), ('Zakariya', 'যাকারিয়া'), ('Anas', 'আনাস'),
    ('Talha', 'তালহা'), ('Suhail', 'সুহাইল'), ('Rayhan', 'রায়হান'),
    ('Sayeed', 'সাঈদ'), ('Noman', 'নোমান'), ('Arif', 'আরিফ'),
    ('Sakib', 'সাকিব'), ('Tanvir', 'তানভীর'), ('Mahdi', 'মাহদী'),
]
LAST_NAMES = [
    ('Rahman', 'রহমান'), ('Hossain', 'হোসাইন'), ('Islam', 'ইসলাম'),
    ('Karim', 'করিম'), ('Chowdhury', 'চৌধুরী'), ('Molla', 'মোল্লা'),
]
UPAZILAS = [
    ('Sarishabari', 'সরিষাবাড়ী', 'Jamalpur', 'জামালপুর'),
    ('Madarganj', 'মাদারগঞ্জ', 'Jamalpur', 'জামালপুর'),
    ('Melandaha', 'মেলান্দহ', 'Jamalpur', 'জামালপুর'),
]
VILLAGES = [('Dasherbari', 'দাসেরবাড়ী'), ('Chowdhurypara', 'চৌধুরীপাড়া'),
            ('Noyapara', 'নয়াপাড়া'), ('Uttarpara', 'উত্তরপাড়া')]


class Command(BaseCommand):
    help = 'Seed one complete demo institution. Idempotent.'

    def add_arguments(self, parser):
        parser.add_argument('--students', type=int, default=24,
                            help='Students per class (default 24).')
        parser.add_argument('--attendance-days', type=int, default=20,
                            help='School days of attendance to mark (default 20).')
        parser.add_argument('--fresh', action='store_true',
                            help='Delete the demo institution first and rebuild it.')

    def handle(self, *args, **options):
        self.made = {}
        self.per_class = options['students']
        self.att_days = options['attendance_days']

        if options['fresh']:
            self.wipe()
        branch = self.institution()
        session = self.session(branch)
        classes = self.classes(branch, session)
        periods = self.periods(branch)
        teachers = self.teachers(branch)
        self.employees(branch)
        self.routine(branch, session, classes, teachers, periods)
        students = self.students(branch, session, classes)
        self.applications(branch, session, classes)
        self.attendance(branch, session, classes, students, teachers)
        self.money(branch, session, classes, students)
        self.exam(branch, session, classes, students, teachers)
        self.logins(branch, teachers, students)

        self.report(branch)


    def wipe(self):
        """Delete the demo institution and everything under it.

        Deletion order is the reverse of the PROTECT graph: the constraints are
        real, so this cannot be a blanket delete and the order below is the
        proof that the foreign keys mean what they say.
        """
        from accounts.models import ActivityLog, User
        from branches.models import Branch, Session, Stream

        branch = Branch.objects.filter(code=CODE).first()
        if branch is None:
            self.stdout.write('  nothing to wipe')
            return

        from academics.models import (AcademicClass, ClassRoutine, Enrolment,
                                      Period, Section, Subject, SubjectAssignment)
        from attendance.models import ClassAttendance, DailyAttendance
        from exams.models import Exam, ExamSchedule, Mark
        from fees.models import Fee, FeeCategory, Payment
        from finance.models import Expense, ExpenseCategory, Income, IncomeCategory
        from forms.models import AdmissionAnswer, FormTemplate, PrintedForm, Question
        from staff.models import Employee, Teacher, TeacherQualification
        from students.models import (Admission, Document, Guardian, Student,
                                     StudentGuardian)

        # Payment.income and Income.payment PROTECT each other, so neither can
        # be deleted first and no ordering exists. That is not a mistake in the
        # models: a receipt is REVERSED, never deleted, and the pair is meant to
        # be undeletable. Breaking the back-link is therefore something only this
        # demo-teardown does, and it says so rather than the constraint being
        # loosened to make an operation nobody should perform convenient.
        Payment.objects.filter(branch=branch).update(income=None)

        order = [
            AdmissionAnswer, PrintedForm, Question, FormTemplate,
            Mark, ExamSchedule, Exam,
            ClassAttendance, DailyAttendance,
            # Income before Payment: Income.payment is PROTECT, so a receipt
            # cannot vanish while its posted income row still points at it.
            Income, Expense, Payment, Fee,
            IncomeCategory, ExpenseCategory, FeeCategory,
            Document, StudentGuardian, Admission, Enrolment, Student, Guardian,
            SubjectAssignment, ClassRoutine, Subject, Section,
            TeacherQualification,
        ]
        for model in order:
            model.objects.filter(branch=branch).delete()

        AcademicClass.objects.filter(branch=branch).update(class_teacher=None)
        Section.objects.filter(branch=branch).update(in_charge=None)
        Teacher.objects.filter(branch=branch).delete()
        Employee.objects.filter(branch=branch).delete()
        AcademicClass.objects.filter(branch=branch).delete()
        Period.objects.filter(branch=branch).delete()
        ActivityLog.objects.filter(branch=branch).delete()
        User.objects.filter(branch=branch).delete()
        # The counters go last and are deliberately PROTECTed by the branch:
        # dropping an institution while its receipt counter survives would let a
        # fresh one restart at 1 and re-issue numbers already printed on paper
        # people are holding. A demo teardown is the one case where that is fine.
        from core.models import NumberSequence
        NumberSequence.objects.filter(branch=branch).delete()

        Branch.objects.filter(pk=branch.pk).update(current_session=None, head=None)
        Session.objects.filter(branch=branch).delete()
        Stream.objects.filter(branch=branch).delete()
        Branch.objects.filter(pk=branch.pk).delete()
        self.stdout.write(self.style.WARNING(f'  wiped the {CODE} institution'))

    # ── The institution ─────────────────────────────────────────────────────
    def institution(self):
        from branches.models import Branch
        from branches.services import create_branch

        existing = Branch.objects.filter(code=CODE).first()
        if existing:
            self.stdout.write(f'  institution {CODE} already exists — filling gaps')
            return existing

        branch = create_branch(
            name='Islamic Education Center Dasherbari',
            name_bn='ইসলামিক এডুকেশন সেন্টার দাসেরবাড়ী',
            name_ar='مركز التعليم الاسلامي داشرباري',
            code=CODE,
            institution_type='madrasah',
            established_year=1985,
            address='Dasherbari, Sarishabari, Jamalpur',
            address_bn='দাসেরবাড়ী, সরিষাবাড়ী, জামালপুর',
            district='Jamalpur', thana='Sarishabari',
            phone='01711000000',
            default_language='bn',
            # A modest fine so the overdue invoices below actually show one.
            fine_rule={'per_day': 5, 'grace_days': 5, 'max': 200},
        )
        self.count('institution', 1)
        return branch

    def session(self, branch):
        from branches.models import Session, Stream
        from branches.services import set_current_session

        session, made = Session.objects.get_or_create(
            branch=branch, name='2026',
            defaults={'starts_on': dt.date(2026, 1, 1), 'ends_on': dt.date(2026, 12, 31)},
        )
        if made:
            session.streams.set(Stream.objects.filter(branch=branch))
            set_current_session(session)
            self.count('session', 1)
        return session

    # ── Academics ───────────────────────────────────────────────────────────
    def classes(self, branch, session):
        """Classes across all three streams, each with a section and subjects."""
        from academics.models import AcademicClass, Section, Subject
        from branches.models import Stream

        plan = [
            ('hifz', 'Nazera', 'নাযেরা', 10, 300,
             [('Qur\'an Nazera', 'কুরআন নাযেরা'), ('Tajweed', 'তাজবীদ'),
              ('Masail', 'মাসায়েল')]),
            ('hifz', 'Hifz', 'হিফজ', 20, 300,
             [('Hifz Sabaq', 'হিফজ সবক'), ('Sabqi & Manzil', 'সবকী ও মানজিল'),
              ('Tajweed', 'তাজবীদ')]),
            ('qaumi', 'Ibtidaiyyah', 'ইবতিদাইয়্যাহ', 30, 400,
             [('Arabic', 'আরবি'), ('Fiqh', 'ফিকহ'), ('Aqidah', 'আকীদা'),
              ('Bangla', 'বাংলা')]),
            ('qaumi', 'Mizan', 'মিযান', 40, 450,
             [('Nahw', 'নাহু'), ('Sarf', 'সরফ'), ('Hadith', 'হাদীস'),
              ('Fiqh', 'ফিকহ')]),
            ('general', 'Class 5', 'পঞ্চম শ্রেণি', 50, 500,
             [('Bangla', 'বাংলা'), ('English', 'ইংরেজি'),
              ('Mathematics', 'গণিত'), ('Religion', 'ধর্ম')]),
            ('general', 'Class 6', 'ষষ্ঠ শ্রেণি', 60, 550,
             [('Bangla', 'বাংলা'), ('English', 'ইংরেজি'),
              ('Mathematics', 'গণিত'), ('Science', 'বিজ্ঞান')]),
        ]

        out = []
        for code, name, name_bn, order, fee, subjects in plan:
            stream = Stream.objects.get(branch=branch, code=code)
            klass, made = AcademicClass.objects.get_or_create(
                branch=branch, session=session, stream=stream, name=name,
                defaults={'name_bn': name_bn, 'year': 2026, 'level_order': order,
                          'capacity': 40, 'monthly_fee': Decimal(fee)},
            )
            self.count('classes', int(made))

            section, made = Section.objects.get_or_create(
                branch=branch, academic_class=klass, name='A',
                defaults={'capacity': 40, 'room': f'Room {order // 10}'},
            )
            self.count('sections', int(made))

            subject_rows = []
            for i, (sname, sname_bn) in enumerate(subjects):
                subject, made = Subject.objects.get_or_create(
                    branch=branch, academic_class=klass, name=sname,
                    defaults={'name_bn': sname_bn, 'stream': stream,
                              'code': f'{code[:3].upper()}{order}{i}',
                              'full_marks': 100, 'pass_marks': 33},
                )
                self.count('subjects', int(made))
                subject_rows.append(subject)

            out.append({'class': klass, 'section': section, 'subjects': subject_rows})
        return out

    def periods(self, branch):
        """The bell schedule. Fajr-adjacent start, as a hifz madrasah runs."""
        from academics.models import Period

        plan = [
            ('1st Period', 'প্রথম ঘণ্টা', 1, (7, 30), (8, 15), False),
            ('2nd Period', 'দ্বিতীয় ঘণ্টা', 2, (8, 15), (9, 0), False),
            ('3rd Period', 'তৃতীয় ঘণ্টা', 3, (9, 0), (9, 45), False),
            ('Break', 'বিরতি', 4, (9, 45), (10, 15), True),
            ('4th Period', 'চতুর্থ ঘণ্টা', 5, (10, 15), (11, 0), False),
            ('5th Period', 'পঞ্চম ঘণ্টা', 6, (11, 0), (11, 45), False),
        ]
        out = []
        for name, name_bn, order, start, end, is_break in plan:
            period, made = Period.objects.get_or_create(
                branch=branch, stream=None, order=order,
                defaults={'name': name, 'name_bn': name_bn,
                          'start_time': dt.time(*start), 'end_time': dt.time(*end),
                          'is_break': is_break},
            )
            self.count('periods', int(made))
            out.append(period)
        return [p for p in out if not p.is_break]

    def teachers(self, branch):
        from staff.models import Teacher
        from staff.services import create_teacher

        plan = [
            ('Mufti Abdul Karim', 'মুফতি আব্দুল করিম', 'Muhtamim', '01711000101'),
            ('Hafiz Yusuf Ali', 'হাফিজ ইউসুফ আলী', 'Hafiz', '01711000102'),
            ('Maulana Nurul Islam', 'মাওলানা নুরুল ইসলাম', 'Mudarris', '01711000103'),
            ('Maulana Sirajul Haque', 'মাওলানা সিরাজুল হক', 'Mudarris', '01711000104'),
            ('Md Kamal Uddin', 'মোঃ কামাল উদ্দীন', 'Assistant Teacher', '01711000105'),
            ('Md Shahidul Alam', 'মোঃ শহীদুল আলম', 'Assistant Teacher', '01711000106'),
        ]
        out = []
        for name, name_bn, designation, phone in plan:
            existing = Teacher.objects.filter(branch=branch, phone=phone).first()
            if existing:
                out.append(existing)
                continue
            teacher = create_teacher(
                branch=branch, name=name, name_bn=name_bn,
                designation=designation, phone=phone,
                joining_date=dt.date(2020, 1, 1),
                gender='male',
                basic_salary=Decimal('18000.00'),
                village='Dasherbari', post_office='Sarishabari',
                upazila='Sarishabari', district='Jamalpur',
            )
            self.count('teachers', 1)
            out.append(teacher)
        return out

    def employees(self, branch):
        from staff.models import Employee
        from staff.services import create_employee

        plan = [
            ('Md Jalal Mia', 'মোঃ জালাল মিয়া', 'Accountant', 'Office', '01711000201'),
            ('Md Rafiq', 'মোঃ রফিক', 'Cook', 'Kitchen', '01711000202'),
            ('Md Selim', 'মোঃ সেলিম', 'Guard', 'Security', '01711000203'),
        ]
        for name, name_bn, designation, department, phone in plan:
            if Employee.objects.filter(branch=branch, phone=phone).exists():
                continue
            create_employee(
                branch=branch, name=name, name_bn=name_bn, gender='male',
                designation=designation, department=department, phone=phone,
                joining_date=dt.date(2021, 6, 1),
                basic_salary=Decimal('12000.00'),
            )
            self.count('employees', 1)

    def routine(self, branch, session, classes, teachers, periods):
        """A clash-free week. The teacher constraint refuses double-booking, so
        this walks a teacher cursor rather than assigning at random and retrying."""
        from academics.models import ClassRoutine, SubjectAssignment

        # 0 = Saturday … 4 = Wednesday. Thursday and Friday are the weekend here.
        for day in range(0, 5):
            cursor = 0
            for slot, period in enumerate(periods):
                for entry in classes:
                    subjects = entry['subjects']
                    subject = subjects[(day + slot) % len(subjects)]
                    teacher = teachers[cursor % len(teachers)]
                    cursor += 1

                    _, made = ClassRoutine.objects.get_or_create(
                        branch=branch, session=session,
                        academic_class=entry['class'], section=entry['section'],
                        day_of_week=day, period=period,
                        defaults={'subject': subject, 'teacher': teacher,
                                  'room': entry['section'].room},
                    )
                    self.count('routine slots', int(made))

                    _, made = SubjectAssignment.objects.get_or_create(
                        branch=branch, session=session, teacher=teacher,
                        subject=subject, academic_class=entry['class'],
                        defaults={'section': entry['section']},
                    )
                    self.count('subject assignments', int(made))

        # Every class needs someone in charge — that is half of D6's scope.
        for i, entry in enumerate(classes):
            klass = entry['class']
            if klass.class_teacher_id is None:
                klass.class_teacher = teachers[i % len(teachers)]
                klass.save(update_fields=['class_teacher', 'updated_at'])

    # ── People ──────────────────────────────────────────────────────────────
    def students(self, branch, session, classes):
        """Students, each with a guardian and an enrolment."""
        from students.models import Student

        out = []
        serial = 0
        for entry in classes:
            klass, section = entry['class'], entry['section']

            # Idempotency is by SHORTFALL, not by matching names. Two generated
            # students can share a name, and a name-based check then treats the
            # second as already present and the class quietly ends up one short —
            # or, worse, grows by one on every run.
            existing = list(
                Student.objects.filter(branch=branch,
                                       enrolments__academic_class=klass).distinct()
            )
            for student in existing:
                out.append((student, klass, section))
            shortfall = max(0, self.per_class - len(existing))

            for _ in range(shortfall):
                serial += 1
                first, first_bn = RNG.choice(FIRST_NAMES)
                last, last_bn = RNG.choice(LAST_NAMES)
                village, _village_bn = RNG.choice(VILLAGES)
                upazila, _u_bn, district, _d_bn = RNG.choice(UPAZILAS)
                name = f'{first} {last}'

                if True:
                    # One transaction per student. The id and the roll come from
                    # two counters, and a number reserved by a block that then
                    # fails leaves a hole in a series whose only promise is that
                    # it has none.
                    with transaction.atomic():
                        student = self._make_student(
                            branch=branch, session=session, klass=klass,
                            section=section, name=name,
                            name_bn=f'{first_bn} {last_bn}', surname=last,
                            serial=serial, village=village,
                            upazila=upazila, district=district,
                        )
                out.append((student, klass, section))
        return out

    def _make_student(self, *, branch, session, klass, section, name, name_bn,
                      surname, serial, village, upazila, district):
        from academics.services import enrol_student
        from students.models import Student
        from students.services import allocate_student_id, link_guardian

        student = Student.objects.create(
            branch=branch, stream=klass.stream,
            # The real allocator, not a hand-rolled string: the series is
            # platform-wide and shared with everything else that admits a
            # student, so inventing numbers here collides with it.
            student_id=allocate_student_id(),
            name=name, name_bn=name_bn,
            date_of_birth=dt.date(2026 - (6 + serial % 8),
                                  1 + serial % 12, 1 + serial % 27),
            gender='male',
            village=village, post_office='Sarishabari',
            upazila=upazila, district=district,
            admitted_on=dt.date(2026, 1, 5),
        )
        self.count('students', 1)

        link_guardian(
            student=student,
            name=f'{RNG.choice(FIRST_NAMES)[0]} {surname}',
            phone=f'018{serial:08d}'[:11],
            relation='father',
        )
        enrol_student(
            branch=branch, student=student, session=session,
            academic_class=klass, section=section,
            enrolled_on=dt.date(2026, 1, 5),
        )
        self.count('enrolments', 1)
        return student

    def applications(self, branch, session, classes):
        """Applications at every stage — this is what the printed form prints.

        Deliberately left UNADMITTED: a pending application is the state the
        admission form exists for, and an owner opening the demo wants something
        to print, not a list of people already admitted.
        """
        from students.models import Admission
        from students.services import create_application

        plan = [
            ('Sayeed Ahmed', 'সাঈদ আহমেদ', 'Abdul Hannan', 'আব্দুল হান্নান', 'pending'),
            ('Nafis Iqbal', 'নাফিস ইকবাল', 'Iqbal Hossain', 'ইকবাল হোসাইন', 'pending'),
            ('Raihan Kabir', 'রায়হান কবির', 'Kabir Mia', 'কবির মিয়া', 'interview'),
            ('Tanzim Hasan', 'তানজিম হাসান', 'Hasan Ali', 'হাসান আলী', 'accepted'),
        ]
        target = classes[0]['class']
        for i, (name, name_bn, guardian, guardian_bn, status) in enumerate(plan):
            if Admission.objects.filter(branch=branch, applicant_name=name).exists():
                continue
            village, village_bn = VILLAGES[i % len(VILLAGES)]
            upazila, _, district, _ = UPAZILAS[i % len(UPAZILAS)]
            create_application(
                branch=branch, session=session,
                stream=target.stream, academic_class=target,
                applicant_name=name, applicant_name_bn=name_bn,
                dob=dt.date(2017, 3 + i, 12), gender='male',
                guardian_name=guardian, guardian_phone=f'0191100{i:04d}',
                village=village, post_office='Sarishabari',
                upazila=upazila, district=district,
                previous_institution='Local Maktab' if i % 2 else '',
                previous_class='Nazera' if i % 2 else '',
                status=status,
            )
            self.count('applications', 1)

    # ── The daily and monthly loop ──────────────────────────────────────────
    def attendance(self, branch, session, classes, students, teachers):
        """A month of marked attendance, mostly present with a believable few
        absences — a register of all-present teaches an owner nothing."""
        from attendance.models import DailyAttendance

        by_class = {}
        for student, klass, section in students:
            by_class.setdefault(klass.pk, []).append((student, klass, section))

        taker = teachers[0].user if teachers[0].user_id else None
        today = timezone.localdate()
        marked = 0
        day = today - dt.timedelta(days=1)
        days_done = 0

        while days_done < self.att_days:
            # Thursday(3)/Friday(4) are the weekend; weekday() has Monday=0.
            if day.weekday() in (3, 4):
                day -= dt.timedelta(days=1)
                continue
            for rows in by_class.values():
                for student, klass, section in rows:
                    enrolment = student.enrolments.filter(session=session).first()
                    roll = RNG.random()
                    status = 'present'
                    if roll > 0.94:
                        status = 'absent'
                    elif roll > 0.90:
                        status = 'late'
                    _, made = DailyAttendance.objects.get_or_create(
                        branch=branch, date=day, person_type='student',
                        student=student,
                        defaults={'enrolment': enrolment, 'status': status,
                                  'taken_by': taker, 'taken_at': timezone.now(),
                                  'source': 'web'},
                    )
                    marked += int(made)
            days_done += 1
            day -= dt.timedelta(days=1)
        self.count('attendance marks', marked)

    def money(self, branch, session, classes, students):
        """Fees raised, most collected, a few left overdue and accruing a fine.

        The point is the ledger: every collection posts its own Income row, so
        Accounts agrees with the receipts without anyone typing it twice.
        """
        from fees.models import FeeCategory
        from fees.services import collect_fee, generate_monthly_fees, raise_fee
        from fees.services import current_period

        # Give the seeded heads a price. Without one, raise_fee refuses rather
        # than writing a ৳0 invoice that reads as already paid (worklog F34).
        prices = {'ADM': 1500, 'SES': 1000, 'MON': None, 'EXM': 300,
                  'BOK': 800, 'UNI': 600, 'TRN': 400, 'HOS': 2500,
                  'FOD': 1800, 'ACT': 200, 'OTH': 0}
        for code, amount in prices.items():
            if amount is None:
                continue
            FeeCategory.objects.filter(branch=branch, code=code, default_amount__isnull=True)\
                .update(default_amount=Decimal(amount))

        period = current_period()
        created = generate_monthly_fees(branch, period=period)
        self.count('monthly invoices', created if isinstance(created, int) else 0)

        admission = FeeCategory.objects.filter(branch=branch, code='ADM').first()
        collected = 0
        for i, (student, klass, section) in enumerate(students):
            if admission and i % 3 == 0:
                # raise_fee returns (fee, created) — the idempotency contract:
                # a second run gets the existing row back rather than a duplicate.
                fee, _created = raise_fee(
                    branch=branch, student=student, category=admission,
                    session=session, amount=admission.default_amount,
                    due_date=dt.date(2026, 1, 15),
                )
                # Two in three of those get paid, so Dues has something real in it.
                if i % 9 != 0 and fee.paid_amount < fee.payable:
                    collect_fee(fee=fee, amount=fee.payable - fee.paid_amount,
                                method='cash')
                    collected += 1
        self.count('fees collected', collected)

    def exam(self, branch, session, classes, students, teachers):
        from exams.models import Exam, ExamSchedule, Mark

        exam, made = Exam.objects.get_or_create(
            branch=branch, session=session, name='Half-Yearly 2026',
            defaults={'stream': classes[0]['class'].stream,
                      'exam_type': 'half_yearly',
                      'starts_on': dt.date(2026, 6, 1),
                      'ends_on': dt.date(2026, 6, 10),
                      'status': 'marks_entry'},
        )
        self.count('exams', int(made))

        entry = classes[4]                      # Class 5 — the general stream
        marks_made = 0
        for i, subject in enumerate(entry['subjects']):
            ExamSchedule.objects.get_or_create(
                exam=exam, academic_class=entry['class'], subject=subject,
                defaults={'branch': branch, 'date': dt.date(2026, 6, 1 + i),
                          'start_time': dt.time(9, 0), 'end_time': dt.time(12, 0),
                          'full_marks': 100, 'pass_marks': 33,
                          'invigilator': teachers[i % len(teachers)]},
            )
            for student, klass, section in students:
                if klass.pk != entry['class'].pk:
                    continue
                enrolment = student.enrolments.filter(session=session).first()
                _, made = Mark.objects.get_or_create(
                    branch=branch, exam=exam, student=student, subject=subject,
                    defaults={'enrolment': enrolment,
                              'obtained': Decimal(RNG.randint(35, 98)),
                              'entered_at': timezone.now()},
                )
                marks_made += int(made)
        self.count('marks', marks_made)

    # ── Logins ──────────────────────────────────────────────────────────────
    def logins(self, branch, teachers, students):
        """A principal, a teacher and a student — so the demo can be judged from
        each seat, not only from the platform admin's."""
        from accounts.models import Role, User

        def make(phone, name, name_bn, user_type, role_name):
            user = User.objects.filter(phone=phone).first()
            if user:
                return user
            user = User.objects.create_user(
                phone=phone, password=PASSWORD, name=name, name_bn=name_bn,
                user_type=user_type, branch=branch, language='bn',
            )
            role = Role.objects.filter(name=role_name).first()
            if role:
                user.role = role
                user.save(update_fields=['role'])
            self.count('logins', 1)
            return user

        principal = make('01700000001', 'Mufti Abdul Karim', 'মুফতি আব্দুল করিম',
                         'principal', 'Principal')
        if branch.head_id is None:
            branch.head = principal
            branch.save(update_fields=['head', 'updated_at'])

        teacher_user = make('01700000002', teachers[1].name, teachers[1].name_bn,
                            'teacher', 'Teacher')
        if teachers[1].user_id is None:
            teachers[1].user = teacher_user
            teachers[1].save(update_fields=['user', 'updated_at'])

        make('01700000003', 'Md Jalal Mia', 'মোঃ জালাল মিয়া',
             'accountant', 'Accountant')

        # Deterministic: the list order varies between a fresh build and a
        # top-up run, so picking students[0] gave a different student each time
        # and the second run tried to re-create a phone that already existed.
        if students and not User.objects.filter(phone='01700000004').exists():
            from students.services import enable_student_login
            student = sorted((s for s, _k, _sec in students),
                             key=lambda s: s.student_id)[0]
            if student.user_id is None:
                enable_student_login(student, phone='01700000004', password=PASSWORD)
                self.count('logins', 1)

    # ── Output ──────────────────────────────────────────────────────────────
    def count(self, what, n):
        if n:
            self.made[what] = self.made.get(what, 0) + n

    def report(self, branch):
        self.stdout.write('')
        if self.made:
            self.stdout.write(self.style.SUCCESS('Created:'))
            for what, n in sorted(self.made.items()):
                self.stdout.write(f'  {n:>6}  {what}')
        else:
            self.stdout.write('Nothing to create — the demo is already seeded.')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'{branch.name} ({branch.code}) is ready.'))
        self.stdout.write('')
        self.stdout.write('  Logins — all with password ' + self.style.WARNING(PASSWORD))
        for phone, who in [
            ('01700000000', 'Platform admin  · every institution'),
            ('01700000001', 'Principal       · this institution'),
            ('01700000002', 'Teacher         · only their assigned classes'),
            ('01700000003', 'Accountant      · fees and accounts'),
            ('01700000004', 'Student         · their own record only'),
        ]:
            self.stdout.write(f'    {phone}   {who}')
        self.stdout.write('')
        self.stdout.write('  Open http://localhost:5000/myadmin')
