"""Initial exams schema — Exam, ExamClass, ExamSchedule, Mark (docs/03 §9).

Hand-written rather than generated, and it matches `models.py` field for field.
`GradeScale`, `GradeBand` and `Result` are absent because they are V2
(docs/05 §5.4); V1 stores marks and computes totals and grades on read.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('branches', '0001_initial'),
        ('academics', '0003_initial'),
        ('staff', '0001_initial'),
        ('students', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Exam',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('name_bn', models.CharField(blank=True, max_length=100, verbose_name='নাম')),
                ('exam_type', models.CharField(choices=[('monthly', 'Monthly · মাসিক'), ('half_yearly', 'Half-yearly · অর্ধবার্ষিক'), ('annual', 'Annual · বার্ষিক'), ('test', 'Test · টেস্ট'), ('sabaq', 'Sabaq · সবক'), ('board', 'Board · বোর্ড পরীক্ষা')], default='monthly', max_length=20, verbose_name='type · ধরন')),
                ('starts_on', models.DateField(verbose_name='starts on · শুরু')),
                ('ends_on', models.DateField(verbose_name='ends on · শেষ')),
                ('status', models.CharField(choices=[('draft', 'Draft · খসড়া'), ('scheduled', 'Scheduled · সময়সূচি হয়েছে'), ('ongoing', 'Ongoing · চলমান'), ('marks_entry', 'Marks entry · নম্বর এন্ট্রি'), ('published', 'Published · ফল প্রকাশিত')], db_index=True, default='draft', max_length=20, verbose_name='status · অবস্থা')),
                ('published_at', models.DateTimeField(blank=True, null=True, verbose_name='published at · প্রকাশের সময়')),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='branches.branch')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('published_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='published by · প্রকাশক')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='exams', to='branches.session', verbose_name='session · শিক্ষাবর্ষ')),
                ('stream', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='exams', to='branches.stream', verbose_name='stream · বিভাগ')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'exam · পরীক্ষা',
                'verbose_name_plural': 'exams · পরীক্ষাসমূহ',
                'ordering': ['branch', '-starts_on', 'name'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ExamClass',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('academic_class', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='exam_classes', to='academics.academicclass', verbose_name='class · শ্রেণি')),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='branches.branch')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_classes', to='exams.exam', verbose_name='exam · পরীক্ষা')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'exam class · পরীক্ষার শ্রেণি',
                'verbose_name_plural': 'exam classes · পরীক্ষার শ্রেণিসমূহ',
                'ordering': ['branch', 'exam', 'academic_class'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ExamSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('date', models.DateField(verbose_name='date · তারিখ')),
                ('start_time', models.TimeField(verbose_name='starts · শুরু')),
                ('end_time', models.TimeField(verbose_name='ends · শেষ')),
                ('full_marks', models.DecimalField(decimal_places=2, max_digits=6, verbose_name='full marks · পূর্ণমান')),
                ('pass_marks', models.DecimalField(decimal_places=2, max_digits=6, verbose_name='pass marks · পাস নম্বর')),
                ('room', models.CharField(blank=True, max_length=40, verbose_name='room · কক্ষ')),
                ('academic_class', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='exam_schedules', to='academics.academicclass', verbose_name='class · শ্রেণি')),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='branches.branch')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedules', to='exams.exam', verbose_name='exam · পরীক্ষা')),
                ('invigilator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invigilations', to='staff.teacher', verbose_name='invigilator · পরিদর্শক')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='exam_schedules', to='academics.subject', verbose_name='subject · বিষয়')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'exam schedule · পরীক্ষার সময়সূচি',
                'verbose_name_plural': 'exam schedules · পরীক্ষার সময়সূচি',
                'ordering': ['branch', 'exam', 'date', 'start_time'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Mark',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('obtained', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='obtained · প্রাপ্ত নম্বর')),
                ('practical_obtained', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='practical · ব্যবহারিক')),
                ('is_absent', models.BooleanField(default=False, verbose_name='absent · অনুপস্থিত')),
                ('entered_at', models.DateTimeField(verbose_name='entered at · এন্ট্রির সময়')),
                ('is_active', models.BooleanField(default=True, verbose_name='active · সক্রিয়')),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='branches.branch')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('enrolment', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='marks', to='academics.enrolment', verbose_name='enrolment · ভর্তি')),
                ('entered_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='entered by · এন্ট্রিকারী')),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='marks', to='exams.exam', verbose_name='exam · পরীক্ষা')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='marks', to='students.student', verbose_name='student · শিক্ষার্থী')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='marks', to='academics.subject', verbose_name='subject · বিষয়')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'mark · নম্বর',
                'verbose_name_plural': 'marks · নম্বরসমূহ',
                'ordering': ['branch', 'exam', 'student', 'subject'],
                'abstract': False,
            },
        ),
        migrations.AddConstraint(
            model_name='exam',
            constraint=models.UniqueConstraint(fields=('branch', 'session', 'stream', 'name'), name='exam_unique_name_per_session_stream'),
        ),
        migrations.AddConstraint(
            model_name='exam',
            constraint=models.CheckConstraint(condition=models.Q(('ends_on__gte', models.F('starts_on'))), name='exam_ends_after_start'),
        ),
        migrations.AddConstraint(
            model_name='exam',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status', 'published'), _negated=True), ('published_at__isnull', False), _connector='OR'), name='exam_published_has_timestamp'),
        ),
        migrations.AddIndex(
            model_name='exam',
            index=models.Index(fields=['branch', 'session', 'status'], name='exam_branch_session_status_idx'),
        ),
        migrations.AddConstraint(
            model_name='examclass',
            constraint=models.UniqueConstraint(fields=('exam', 'academic_class'), name='examclass_unique_per_exam'),
        ),
        migrations.AddConstraint(
            model_name='examschedule',
            constraint=models.UniqueConstraint(fields=('exam', 'academic_class', 'subject'), name='examschedule_unique_paper'),
        ),
        migrations.AddConstraint(
            model_name='examschedule',
            constraint=models.CheckConstraint(condition=models.Q(('end_time__gt', models.F('start_time'))), name='examschedule_ends_after_start'),
        ),
        migrations.AddConstraint(
            model_name='examschedule',
            constraint=models.CheckConstraint(condition=models.Q(('pass_marks__lte', models.F('full_marks'))), name='examschedule_pass_within_full'),
        ),
        migrations.AddIndex(
            model_name='examschedule',
            index=models.Index(fields=['branch', 'exam', 'academic_class'], name='examsched_exam_class_idx'),
        ),
        migrations.AddConstraint(
            model_name='mark',
            constraint=models.UniqueConstraint(fields=('exam', 'student', 'subject'), name='mark_unique_per_paper'),
        ),
        migrations.AddConstraint(
            model_name='mark',
            constraint=models.CheckConstraint(condition=models.Q(('is_absent', False), models.Q(('obtained__isnull', True), ('practical_obtained__isnull', True)), _connector='OR'), name='mark_absent_has_no_score'),
        ),
        migrations.AddConstraint(
            model_name='mark',
            constraint=models.CheckConstraint(condition=models.Q(('obtained__isnull', True), ('obtained__gte', 0), _connector='OR'), name='mark_obtained_not_negative'),
        ),
        migrations.AddConstraint(
            model_name='mark',
            constraint=models.CheckConstraint(condition=models.Q(('practical_obtained__isnull', True), ('practical_obtained__gte', 0), _connector='OR'), name='mark_practical_not_negative'),
        ),
        migrations.AddIndex(
            model_name='mark',
            index=models.Index(fields=['branch', 'exam', 'subject'], name='mark_exam_subject_idx'),
        ),
        migrations.AddIndex(
            model_name='mark',
            index=models.Index(fields=['branch', 'student'], name='mark_student_idx'),
        ),
    ]
