"""Initial forms schema — FormTemplate, Question, AdmissionAnswer, PrintedForm
(docs/07 §6). Hand-written, and it matches `models.py` field for field."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('branches', '0001_initial'),
        ('students', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FormTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100, verbose_name='name · নাম')),
                ('name_bn', models.CharField(blank=True, max_length=100, verbose_name='নাম')),
                ('form_type', models.CharField(choices=[('admission', 'Admission form · ভর্তি ফরম'), ('undertaking', 'Undertaking · অঙ্গিকারনামা'), ('id_card', 'ID card · পরিচয়পত্র'), ('certificate', 'Certificate · সনদ')], default='admission', max_length=20, verbose_name='type · ধরন')),
                ('blocks', models.JSONField(blank=True, default=list, help_text='Ordered list of blocks. Validated on save.', verbose_name='blocks · ব্লক')),
                ('paper', models.CharField(choices=[('A4', 'A4'), ('Legal', 'Legal')], default='A4', max_length=10, verbose_name='paper · কাগজ')),
                ('margins', models.CharField(default='12mm 14mm', max_length=40, verbose_name='margins · মার্জিন')),
                ('is_default', models.BooleanField(default=False, verbose_name='default · ডিফল্ট')),
                ('is_active', models.BooleanField(default=True, verbose_name='active · সক্রিয়')),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='branches.branch')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'form template · ফরম টেমপ্লেট',
                'verbose_name_plural': 'form templates · ফরম টেমপ্লেট',
                'ordering': ['branch', 'form_type', 'name'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Question',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('section', models.CharField(default='general', max_length=60, verbose_name='section · অংশ')),
                ('text', models.CharField(max_length=300, verbose_name='question')),
                ('text_bn', models.CharField(blank=True, max_length=300, verbose_name='প্রশ্ন')),
                ('type', models.CharField(choices=[('single_choice', 'Single choice · একটি বাছাই'), ('multi_choice', 'Multiple choice · একাধিক বাছাই'), ('description', 'Description · বর্ণনা'), ('short_text', 'Short text · সংক্ষিপ্ত উত্তর'), ('number', 'Number · সংখ্যা'), ('date', 'Date · তারিখ'), ('yes_no', 'Yes / no · হ্যাঁ / না')], default='short_text', max_length=20, verbose_name='type · ধরন')),
                ('options', models.JSONField(blank=True, default=list, help_text='[{value, label, label_bn}] — required for the choice types.', verbose_name='options · বিকল্প')),
                ('is_required', models.BooleanField(default=False, verbose_name='required · আবশ্যক')),
                ('print_style', models.CharField(choices=[('inline', 'Inline · এক লাইনে'), ('block', 'Block · নিচে লাইনসহ'), ('checkbox', 'Checkbox · ☐ ঘর')], default='inline', max_length=20, verbose_name='print style · ছাপার ধরন')),
                ('answer_lines', models.PositiveSmallIntegerField(default=1, verbose_name='answer lines · উত্তরের লাইন')),
                ('maps_to', models.CharField(blank=True, help_text='A student field this answer writes instead of being stored.', max_length=40, verbose_name='maps to · যে ফিল্ডে যায়')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order · ক্রম')),
                ('is_active', models.BooleanField(default=True, verbose_name='active · সক্রিয়')),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='branches.branch')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('template', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='questions', to='forms.formtemplate', verbose_name='template · টেমপ্লেট')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'question · প্রশ্ন',
                'verbose_name_plural': 'questions · প্রশ্নসমূহ',
                'ordering': ['branch', 'section', 'order', 'id'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='AdmissionAnswer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('value', models.JSONField(blank=True, null=True, verbose_name='answer · উত্তর')),
                ('answered_at', models.DateTimeField(auto_now=True, verbose_name='answered at · উত্তরের সময়')),
                ('admission', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='form_answers', to='students.admission', verbose_name='admission · ভর্তির আবেদন')),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='branches.branch')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='answers', to='forms.question', verbose_name='question · প্রশ্ন')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'admission answer · আবেদনের উত্তর',
                'verbose_name_plural': 'admission answers · আবেদনের উত্তরসমূহ',
                'ordering': ['branch', 'admission', 'question'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PrintedForm',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('form_no', models.CharField(max_length=40, verbose_name='form no · ফরম নং')),
                ('snapshot', models.JSONField(default=dict, verbose_name='snapshot · সংরক্ষিত অনুলিপি')),
                ('printed_at', models.DateTimeField(verbose_name='printed at · মুদ্রণের সময়')),
                ('reprint_count', models.PositiveIntegerField(default=0, verbose_name='reprints · পুনর্মুদ্রণ')),
                ('admission', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='printed_forms', to='students.admission', verbose_name='admission · ভর্তির আবেদন')),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='branches.branch')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('printed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='printed by · মুদ্রণকারী')),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='printed_forms', to='forms.formtemplate', verbose_name='template · টেমপ্লেট')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'printed form · মুদ্রিত ফরম',
                'verbose_name_plural': 'printed forms · মুদ্রিত ফরম',
                'ordering': ['branch', '-printed_at'],
                'abstract': False,
            },
        ),
        migrations.AddConstraint(
            model_name='formtemplate',
            constraint=models.UniqueConstraint(fields=('branch', 'form_type', 'name'), name='formtemplate_unique_name_per_type'),
        ),
        migrations.AddConstraint(
            model_name='formtemplate',
            constraint=models.UniqueConstraint(condition=models.Q(('is_default', True)), fields=('branch', 'form_type'), name='formtemplate_one_default_per_type'),
        ),
        migrations.AddIndex(
            model_name='question',
            index=models.Index(fields=['branch', 'section', 'order'], name='question_section_order_idx'),
        ),
        migrations.AddConstraint(
            model_name='admissionanswer',
            constraint=models.UniqueConstraint(fields=('admission', 'question'), name='admissionanswer_unique_per_question'),
        ),
        migrations.AddConstraint(
            model_name='printedform',
            constraint=models.UniqueConstraint(fields=('branch', 'form_no'), name='printedform_unique_form_no'),
        ),
        migrations.AddIndex(
            model_name='printedform',
            index=models.Index(fields=['branch', 'admission'], name='printedform_admission_idx'),
        ),
    ]
