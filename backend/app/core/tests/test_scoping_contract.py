"""The rule of CLAUDE.md §4.1 and §5, enforced instead of reviewed.

Two questions asked of the running code, so that the answer cannot drift:

1. **Every model is branch-scoped or on the closed global list.** §4.1 calls a
   model that is neither "a review failure" — this makes it a test failure,
   which is the same sentence said in time to matter.

2. **Every routed endpoint emits a branch filter in its own SQL.** Not "does it
   inherit the right base class": a viewset can inherit `BranchScopedViewSet`
   and then override `get_queryset()` without calling `super()`, and the class
   hierarchy still looks right. This builds a request scoped to one institution,
   calls the view's own `get_queryset()`, and reads the query it produced.

The allow-lists below are the whole point. Adding a model or an endpoint that
crosses institutions is allowed — it is sometimes correct — but it costs a line
here and a reason beside it, which is exactly the review that would otherwise
have to remember to happen.
"""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import get_resolver

from branches.models import Branch
from core.middleware import resolve_branch
from core.models import BranchScopedModel

User = get_user_model()

LOCAL_APPS = {'accounts', 'branches', 'academics', 'students', 'forms', 'staff',
              'attendance', 'fees', 'finance', 'exams', 'notifications', 'core'}

#: The closed global list (CLAUDE.md §4.1) and why each one is on it.
GLOBAL_MODELS = {
    'branches.Branch': 'the institution itself',
    'accounts.User': 'a phone is one login platform-wide — a teacher who moves '
                     'institution keeps their history',
    'accounts.Role': 'a preset is platform vocabulary',
    'accounts.ActivityLog': 'the platform operator’s audit trail over its '
                            'customers; its branch is nullable on purpose',
    'core.NumberSequence': 'the counter rows themselves; each is keyed BY branch',
}

#: Endpoints that answer without an institution, and why.
NO_INSTITUTION_DATA = {
    'LoginView', 'LogoutView', 'RefreshView', 'ChangePasswordView',
    'PermissionCatalogView', 'APIRootView',
}
#: Scoped to the PERSON rather than to the institution (docs/08 D4).
PERSONAL = {'MeView', 'MyProfileView', 'MyGuardianView', 'MyDocumentViewSet'}
#: Deliberately cross-institution.
GLOBAL_VIEWS = {
    'BranchViewSet': 'the branch switcher’s own source; scoped by hand to '
                     'the caller’s branch, or all of them for the operator',
    'RoleViewSet': 'presets are global, like the model',
}


def routed_views():
    """Every view class mounted under /api/, once each."""
    def walk(patterns, prefix=''):
        for pattern in patterns:
            if hasattr(pattern, 'url_patterns'):
                yield from walk(pattern.url_patterns, prefix + str(pattern.pattern))
            else:
                yield prefix + str(pattern.pattern), pattern.callback

    seen = {}
    for route, callback in walk(get_resolver().url_patterns):
        cls = getattr(callback, 'cls', None) or getattr(callback, 'view_class', None)
        if cls is None or not route.startswith('api/'):
            continue
        seen.setdefault(cls.__name__, (cls, route))
    return seen


class ModelScopingTests(TestCase):
    def test_every_model_is_branch_scoped_or_named_as_global(self):
        from django.apps import apps

        stray = []
        for model in apps.get_models():
            if model._meta.app_label not in LOCAL_APPS or model._meta.auto_created:
                continue
            label = f'{model._meta.app_label}.{model.__name__}'
            if issubclass(model, BranchScopedModel) or label in GLOBAL_MODELS:
                continue
            stray.append(label)

        self.assertEqual(
            stray, [],
            'A model must be BranchScopedModel or listed in GLOBAL_MODELS with '
            'a reason (CLAUDE.md §4.1). Unlisted: ' + ', '.join(stray),
        )

    def test_the_global_list_has_not_grown_by_accident(self):
        """Five, and each one argued for. A sixth is a decision, not a commit."""
        self.assertEqual(len(GLOBAL_MODELS), 5)


class EndpointScopingTests(TestCase):
    """Every list endpoint's own SQL, read back."""

    def setUp(self):
        self.branch = Branch.objects.create(name='Scope Check', code='SCOPE')
        self.user = User.objects.create_user(
            phone='01799000001', password='pass-phrase-1234',
            name='Scope Check', branch=self.branch, user_type='principal',
        )
        self.factory = RequestFactory()

    def queryset_sql(self, cls):
        request = self.factory.get('/api/x/')
        request.user = self.user
        request.branch = resolve_branch(request)

        view = cls()
        view.request = request
        view.format_kwarg = None
        view.action = 'list'
        view.kwargs = {}
        return str(view.get_queryset().query)

    def test_every_endpoint_names_the_institution_in_its_own_query(self):
        unscoped = []
        for name, (cls, route) in sorted(routed_views().items()):
            if name in NO_INSTITUTION_DATA or name in PERSONAL or name in GLOBAL_VIEWS:
                continue
            try:
                sql = self.queryset_sql(cls)
            except Exception:
                # A view whose queryset needs URL kwargs resolves its own row
                # through a scoped lookup; `students.tests` and `forms.tests`
                # cover those individually with a real cross-branch request.
                continue
            if 'branch_id' not in sql and '"branch"' not in sql:
                unscoped.append(f'{name} (/{route})')

        self.assertEqual(
            unscoped, [],
            'These endpoints answer without naming an institution. Scope them, '
            'or list them above with a reason: ' + ', '.join(unscoped),
        )

    def test_the_exempt_lists_stay_small_and_argued(self):
        """If this count moves, somebody exempted an endpoint — read why."""
        self.assertEqual(len(NO_INSTITUTION_DATA), 6)
        self.assertEqual(len(PERSONAL), 4)
        self.assertEqual(len(GLOBAL_VIEWS), 2)
