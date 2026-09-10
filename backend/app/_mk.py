from datetime import date
from decimal import Decimal
from branches.models import Branch, Session
from academics.models import AcademicClass, Enrolment
from students.models import Student
from fees.models import FeeCategory
from fees.services import raise_fee
from accounts.models import User

b = Branch.objects.get(code='DEMO')
s = Session.objects.filter(branch=b, is_current=True).first()
print('session', s)
cls = AcademicClass.objects.filter(branch=b).first()
print('class', cls)
if cls is None:
    cls = AcademicClass.objects.create(branch=b, session=s, name='ZZTEST Class', name_bn='ZZ', level_order=99, capacity=10, monthly_fee=Decimal('500.00'))
    print('created class', cls.id)
st = Student.objects.create(branch=b, name='ZZTEST Student', name_bn='জেডজেড', phone='01999000111', admitted_on=date.today())
en = Enrolment.objects.create(branch=b, student=st, session=s, academic_class=cls, roll=999, admission_number='ZZTEST-1', enrolled_on=date.today())
cat = FeeCategory.objects.get(branch=b, code='MON')
u = User.objects.get(phone='01700000000')
f = raise_fee(branch=b, student=st, category=cat, session=s, amount=Decimal('1200.00'), due_date=date.today(), period='2026-09', enrolment=en, actor=u)
print('STUDENT', st.id, st.student_id, 'ENROL', en.id, 'FEE', f.id, f.invoice_no, 'CLASS', cls.id)
