"""Give every existing institution a grading scale per বিভাগ.

New institutions get theirs from `branches.seeding.seed_branch()`. This covers
the ones created before grading existed, with the same presets — copied here
rather than imported, because a migration must keep meaning what it meant on
the day it ran even after `exams/grading.py` changes.

A stream that already has a scale is left alone, so re-running does nothing.
"""

from decimal import Decimal

from django.db import migrations

DIVISION_STREAM_CODES = {'hifz', 'qaumi'}

PRESETS = {
    'gpa': ('GPA (board)', 'জিপিএ পদ্ধতি (বোর্ড)', (
        ('80', 'A+', 'এ+', '5.00', False),
        ('70', 'A', 'এ', '4.00', False),
        ('60', 'A-', 'এ-', '3.50', False),
        ('50', 'B', 'বি', '3.00', False),
        ('40', 'C', 'সি', '2.00', False),
        ('33', 'D', 'ডি', '1.00', False),
        ('0', 'F', 'এফ', '0.00', True),
    )),
    'division': ('Qawmi grades', 'কওমি পদ্ধতি (মুমতাজ–রাসিব)', (
        ('80', 'Mumtaz', 'মুমতাজ', '0.00', False),
        ('65', 'Jayyid Jiddan', 'জায়্যিদ জিদ্দান', '0.00', False),
        ('50', 'Jayyid', 'জায়্যিদ', '0.00', False),
        ('33', 'Maqbul', 'মাকবুল', '0.00', False),
        ('0', 'Rasib', 'রাসিব', '0.00', True),
    )),
}


def seed(apps, schema_editor):
    Stream = apps.get_model('branches', 'Stream')
    GradeScale = apps.get_model('exams', 'GradeScale')
    GradeBand = apps.get_model('exams', 'GradeBand')

    for stream in Stream.objects.all():
        if GradeScale.objects.filter(branch_id=stream.branch_id, stream=stream).exists():
            continue
        method = 'division' if stream.code in DIVISION_STREAM_CODES else 'gpa'
        name, name_bn, bands = PRESETS[method]
        scale = GradeScale.objects.create(
            branch_id=stream.branch_id, stream=stream,
            name=name, name_bn=name_bn, method=method,
        )
        GradeBand.objects.bulk_create([
            GradeBand(branch_id=stream.branch_id, scale=scale,
                      min_percent=Decimal(floor), grade=grade, grade_bn=grade_bn,
                      point=Decimal(point), is_fail=is_fail)
            for floor, grade, grade_bn, point, is_fail in bands
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0002_grade_scales_and_results'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
