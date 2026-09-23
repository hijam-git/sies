"""The permission catalogue, the role presets, and the rule that resolves them.

Ported from `awliaa/backend/app/accounts/permissions.py`, which is the strongest
idea in the reference project (CLAUDE.md §3.2). The domain is replaced; the
mechanism is not:

> A **role** ticks a set of boxes. The **boxes** are what gets enforced.

Fixed roles cannot express "runs admissions but must never see the accounts",
and every institution eventually needs exactly that (docs/02 §2). So `Role` is a
named preset, `User.permissions` is a flat list of `"resource.action"` strings,
and an empty list falls back to the preset.

The catalogue is served to the SPA at `GET /api/accounts/permission-catalog/`,
so the checkbox screen is generated from this file and cannot drift from what
the backend enforces. One source of truth, not two copies that agree until the
day they do not.

`core/permissions.py` holds the *mechanism* half — `HasPermission('fees.collect')`
and the resolver hook — and deliberately knows nothing about this catalogue, so
`core` keeps depending on no app (docs/06 §2). This module supplies the resolver
that core calls; nothing here imports core's models.
"""

from rest_framework.permissions import BasePermission

# ─────────────────────────────────────────────────────────────────────────────
# The catalogue — docs/02 §2.1, exactly. Order is display order in the SPA.
#
# Three separations are deliberate and carry Awliaa's `purchasing` reasoning:
#
#   * `income` is not `expenses`. The person at the counter who writes up a
#     donation is not thereby trusted to pay bills out of the same cash, and an
#     institution that wants one clerk per side has to be able to say so.
#     `create` is recording an entry; `update` is correcting or reversing one
#     and managing the heads entries are filed under.
#   * `salary` is not income or expenses. Letting an accountant post the electricity bill
#     is a much smaller decision than letting them see what every teacher earns.
#   * `marks.enter` is not `exams.publish`. A teacher enters their subject's
#     marks; only the principal publishes, and publishing is the moment results
#     become visible and the rank is computed.
#
# `marks` carries a `view` action even though "any action implies view" would
# have covered the nav gate. A fallback that says so is the kind of rule that
# later hides a real bug (docs/WORKLOG F12).
# ─────────────────────────────────────────────────────────────────────────────
PERMISSION_CATALOG = [
    {
        'resource': 'dashboard',
        'label': 'Dashboard', 'label_bn': 'ড্যাশবোর্ড',
        'actions': ['view'],
        'hint': 'The overview page and its numbers',
        'hint_bn': 'ওভারভিউ পাতা ও তার সংখ্যাগুলো',
    },
    {
        'resource': 'branches',
        'label': 'Institutions', 'label_bn': 'প্রতিষ্ঠান',
        'actions': ['view', 'create', 'update'],
        'hint': 'Institution list and settings (platform admin)',
        'hint_bn': 'প্রতিষ্ঠানের তালিকা ও সেটিংস (প্ল্যাটফর্ম অ্যাডমিন)',
    },
    {
        'resource': 'academics',
        'label': 'Academics', 'label_bn': 'শিক্ষা কার্যক্রম',
        'actions': ['view', 'create', 'update', 'delete'],
        'hint': 'Classes, sections, subjects, sessions, streams and the routine',
        'hint_bn': 'শ্রেণি, শাখা, বিষয়, শিক্ষাবর্ষ, বিভাগ ও রুটিন',
    },
    {
        'resource': 'students',
        'label': 'Students', 'label_bn': 'শিক্ষার্থী',
        'actions': ['view', 'create', 'update', 'delete'],
        'hint': 'Student records and profiles',
        'hint_bn': 'শিক্ষার্থীর তথ্য ও প্রোফাইল',
    },
    {
        'resource': 'admissions',
        'label': 'Admissions', 'label_bn': 'ভর্তি',
        'actions': ['view', 'create', 'update'],
        'hint': 'Applications, admission and enrolment',
        'hint_bn': 'আবেদন, ভর্তি ও নিবন্ধন',
    },
    {
        'resource': 'teachers',
        'label': 'Teachers', 'label_bn': 'শিক্ষক',
        'actions': ['view', 'create', 'update', 'delete'],
        'hint': 'Teacher profiles and assignments',
        'hint_bn': 'শিক্ষকের প্রোফাইল ও দায়িত্ব বণ্টন',
    },
    {
        'resource': 'employees',
        'label': 'Employees', 'label_bn': 'কর্মচারী',
        'actions': ['view', 'create', 'update', 'delete'],
        'hint': 'Non-teaching staff',
        'hint_bn': 'শিক্ষকতা ছাড়া অন্যান্য কর্মচারী',
    },
    {
        'resource': 'attendance',
        'label': 'Attendance', 'label_bn': 'উপস্থিতি',
        'actions': ['view', 'take', 'update'],
        'hint': 'Taking and correcting attendance',
        'hint_bn': 'উপস্থিতি নেওয়া ও সংশোধন করা',
    },
    {
        # Its own resource and not a corner of `attendance`: the same teacher
        # does both, but an institution that wants the নামাজ register filled by
        # the hall supervisor and attendance by the class teacher can say so.
        # What is ON the sheet is `settings`, because deciding what the
        # institution observes is the office's act, not the observer's.
        'resource': 'conduct',
        'label': 'Conduct report', 'label_bn': 'আমল ও আদব',
        'actions': ['view', 'take', 'update'],
        'hint': 'Filling and correcting the observation sheet (নামাজ, তিলাওয়াত, আদব)',
        'hint_bn': 'আমল-আদবের রিপোর্ট পূরণ ও সংশোধন',
    },
    {
        'resource': 'fees',
        'label': 'Fees', 'label_bn': 'ফি',
        'actions': ['view', 'create', 'update', 'collect', 'waive'],
        'hint': 'Invoices, collection and discounts',
        'hint_bn': 'বিল, আদায় ও ছাড়',
    },
    {
        'resource': 'income',
        'label': 'Income', 'label_bn': 'আয়',
        'actions': ['view', 'create', 'update'],
        'hint': 'Recording income. Update also corrects entries and manages income '
                'heads. Fee receipts post here on their own',
        'hint_bn': 'আয় লেখা। সংশোধন অনুমতিতে এন্ট্রি ঠিক করা ও আয়ের খাত সম্পাদনা। '
                   'ফি আদায় নিজে থেকেই এখানে যোগ হয়',
    },
    {
        'resource': 'expenses',
        'label': 'Expenses', 'label_bn': 'ব্যয়',
        'actions': ['view', 'create', 'update'],
        'hint': 'Recording expenses. Update also corrects entries and manages '
                'expense heads',
        'hint_bn': 'ব্যয় লেখা। সংশোধন অনুমতিতে এন্ট্রি ঠিক করা ও ব্যয়ের খাত সম্পাদনা',
    },
    {
        'resource': 'salary',
        'label': 'Salary & payroll', 'label_bn': 'বেতন',
        'actions': ['view', 'manage'],
        'hint': 'Payroll. Separate from income & expense on purpose — what every '
                'teacher earns is not the electricity bill',
        'hint_bn': 'বেতন-ভাতা। আয়-ব্যয় থেকে আলাদা রাখা হয়েছে ইচ্ছাকৃতভাবে — '
                   'কে কত বেতন পান তা বিদ্যুৎ বিলের মতো নয়',
    },
    {
        'resource': 'exams',
        'label': 'Exams', 'label_bn': 'পরীক্ষা',
        'actions': ['view', 'create', 'update', 'publish'],
        'hint': 'Exams, schedules and publishing results',
        'hint_bn': 'পরীক্ষা, সময়সূচি ও ফল প্রকাশ',
    },
    {
        'resource': 'marks',
        'label': 'Marks entry', 'label_bn': 'নম্বর এন্ট্রি',
        'actions': ['view', 'enter', 'update'],
        'hint': 'Entering marks. A teacher gets this without being able to '
                'create an exam or publish a result',
        'hint_bn': 'নম্বর তোলা। শিক্ষক এটি পান, কিন্তু পরীক্ষা তৈরি বা ফল প্রকাশ নয়',
    },
    {
        'resource': 'reports',
        'label': 'Reports', 'label_bn': 'রিপোর্ট',
        'actions': ['view', 'export'],
        'hint': 'Reports and their exports',
        'hint_bn': 'রিপোর্ট ও তা ডাউনলোড করা',
    },
    {
        'resource': 'notices',
        'label': 'Notice board', 'label_bn': 'নোটিশ বোর্ড',
        'actions': ['view', 'create', 'delete'],
        'hint': 'The notice board',
        'hint_bn': 'নোটিশ বোর্ড',
    },
    {
        'resource': 'documents',
        'label': 'Documents', 'label_bn': 'কাগজপত্র',
        'actions': ['view', 'upload', 'delete'],
        'hint': 'Certificates, testimonials and student files',
        'hint_bn': 'সনদ, প্রশংসাপত্র ও শিক্ষার্থীর ফাইল',
    },
    {
        'resource': 'settings',
        'label': 'Settings', 'label_bn': 'সেটিংস',
        'actions': ['view', 'update'],
        'hint': 'Institution settings, fee categories and form templates',
        'hint_bn': 'প্রতিষ্ঠানের সেটিংস, ফি খাত ও ফরম টেমপ্লেট',
    },
    {
        'resource': 'users',
        'label': 'Users & roles', 'label_bn': 'ব্যবহারকারী ও ভূমিকা',
        'actions': ['view', 'create', 'update'],
        'hint': 'Accounts, roles and permission assignment',
        'hint_bn': 'অ্যাকাউন্ট, ভূমিকা ও অনুমতি প্রদান',
    },
    {
        'resource': 'activity',
        'label': 'Activity log', 'label_bn': 'কার্যক্রমের লগ',
        'actions': ['view'],
        'hint': 'The live activity feed and its history',
        'hint_bn': 'সরাসরি কার্যক্রমের তালিকা ও ইতিহাস',
    },
]

# Flat set of valid "resource.action" strings, for validating what the API is
# asked to store — a typo must not become a permission that never matches.
VALID_PERMISSIONS = {
    f"{entry['resource']}.{action}"
    for entry in PERMISSION_CATALOG
    for action in entry['actions']
}

# Every action of every resource, keyed by resource. Used to expand the `'*'`
# shorthand in the presets below, so a preset never restates the catalogue and
# adding an action to a resource widens the presets that already grant all of it.
ALL_ACTIONS = {entry['resource']: list(entry['actions']) for entry in PERMISSION_CATALOG}


def flatten(matrix):
    """`{'fees': ['view']}` → `{'fees.view'}`.

    Accepts `'*'` in place of an action list, meaning every action the catalogue
    defines for that resource. Role rows in the database never contain `'*'` —
    they are expanded when the preset is written — so this shorthand is a
    convenience for `ROLE_PRESETS` alone.
    """
    out = set()
    for resource, actions in (matrix or {}).items():
        if actions == '*':
            actions = ALL_ACTIONS.get(resource, [])
        if not isinstance(actions, (list, tuple, set)):
            continue
        for action in actions:
            if isinstance(action, str):
                out.add(f'{resource}.{action}')
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Role presets — docs/02 §2.2. A preset is a starting point, never a cage: any
# individual box can be ticked or unticked per person (§2.3).
# ─────────────────────────────────────────────────────────────────────────────
ROLE_PRESETS = {
    # Everything, across every institution.
    'Platform Admin': {resource: '*' for resource in ALL_ACTIONS},

    # Everything inside their own institution. Two exclusions, both deliberate:
    # creating an institution is the platform operator's act, and the activity
    # feed is the platform's audit trail over its customers.
    'Principal': {
        **{resource: '*' for resource in ALL_ACTIONS},
        'branches': ['view', 'update'],
        'activity': [],
    },

    # Consolidated income and expense across institutions, and nothing that
    # touches a student record. docs/02 §1 lists this actor but §2.2 gives it no
    # preset; this is that gap filled rather than left to per-person ticks.
    'Platform Accountant': {
        'dashboard': ['view'],
        'branches': ['view'],
        'fees': ['view'],
        'income': '*',
        'expenses': '*',
        'reports': ['view', 'export'],
    },

    'Accountant': {
        'dashboard': ['view'],
        'fees': '*',
        'income': '*',
        'expenses': '*',
        'reports': ['view', 'export'],
        'students': ['view'],
        'academics': ['view'],
        # Not salary. An accountant who posts the bills is not thereby entitled
        # to the payroll; an institution that wants both ticks salary.view on
        # that one person.
    },

    # One side of the ledger each, and input only: they record entries and
    # read the list they are adding to, but cannot correct or reverse an entry,
    # add a head, or see the other side at all. The accountant above does those.
    'Income Clerk': {
        'dashboard': ['view'],
        'income': ['view', 'create'],
    },

    'Expense Clerk': {
        'dashboard': ['view'],
        'expenses': ['view', 'create'],
    },

    'Admission Officer': {
        'dashboard': ['view'],
        'admissions': '*',
        'students': ['view', 'create', 'update'],
        # create, not collect: they raise the admission invoice, the counter
        # takes the money.
        'fees': ['view', 'create'],
        'documents': ['upload'],
    },

    'Teacher': {
        'dashboard': ['view'],
        'academics': ['view'],
        # take, not update. Correcting yesterday's register is the class
        # teacher's call — the next preset down.
        'attendance': ['view', 'take'],
        # Same split, same reason: today's sheet is the teacher's, yesterday's
        # correction is the class teacher's.
        'conduct': ['view', 'take'],
        'marks': ['view', 'enter', 'update'],
        'students': ['view'],
        'exams': ['view'],
    },

    'Class Teacher': {
        'dashboard': ['view'],
        'academics': ['view'],
        'attendance': ['view', 'take', 'update'],
        'conduct': ['view', 'take', 'update'],
        'marks': ['view', 'enter', 'update'],
        'students': ['view'],
        'exams': ['view'],
        'documents': ['view'],
    },

    'Hostel Warden': {
        'dashboard': ['view'],
        'students': ['view'],
        'attendance': ['view', 'take'],
        # The warden sees নামাজ and আদব at closer range than anyone.
        'conduct': ['view', 'take'],
    },

    'Office Assistant': {
        'dashboard': ['view'],
        'students': ['view'],
        'documents': ['view', 'upload'],
        'notices': ['view'],
    },

    # Non-teaching staff differ from each other more than teachers do: a warden
    # takes attendance, a librarian does not, a cook needs nothing but their own
    # payslip. One thin preset plus per-person ticks covers all of them without
    # inventing a role per job title. Self-service (/api/me/) is not a
    # permission and so is not listed here (docs/02 §2.5).
    'General Employee': {
        'dashboard': ['view'],
    },
}

# Presets that ship with the system and that an admin may not delete
# (`Role.is_system`). Kept as a name list so `seed_roles` and the admin agree.
SYSTEM_ROLE_NAMES = tuple(ROLE_PRESETS)

# Bangla names for the shipped presets. The SPA renders whichever the user's
# language selects, and a role created by an institution supplies its own.
ROLE_NAMES_BN = {
    'Platform Admin': 'প্ল্যাটফর্ম অ্যাডমিন',
    'Principal': 'অধ্যক্ষ / মুহতামিম',
    'Platform Accountant': 'প্ল্যাটফর্ম হিসাবরক্ষক',
    'Accountant': 'হিসাবরক্ষক',
    'Income Clerk': 'আয় এন্ট্রি সহকারী',
    'Expense Clerk': 'ব্যয় এন্ট্রি সহকারী',
    'Admission Officer': 'ভর্তি কর্মকর্তা',
    'Teacher': 'শিক্ষক',
    'Class Teacher': 'শ্রেণিশিক্ষক',
    'Hostel Warden': 'হোস্টেল সুপার',
    'Office Assistant': 'অফিস সহকারী',
    'General Employee': 'সাধারণ কর্মচারী',
}


def preset_matrix(role_name):
    """A shipped preset expanded into a plain `{resource: [actions]}` matrix.

    `'*'` is resolved here so what lands in `Role.permission_matrix` is literal.
    A row in the database that still said `'*'` would silently widen itself the
    day a new action is added to the catalogue — surprising for a role an admin
    has since edited by hand.
    """
    matrix = ROLE_PRESETS.get(role_name, {})
    return {
        resource: (list(ALL_ACTIONS.get(resource, [])) if actions == '*' else list(actions))
        for resource, actions in matrix.items()
    }


def preset_for(role_name):
    """The sorted permission list a named preset ticks. `[]` if unknown."""
    return sorted(flatten(ROLE_PRESETS.get(role_name, {})))


def clean_permissions(raw):
    """Validate a submitted list, dropping anything not in the catalogue.

    A typo in the API must not become a permission string that never matches
    anything: stored, it looks granted on the checkbox screen and silently is
    not. Dropping it at the boundary means what is saved is always what is
    enforced.
    """
    if not isinstance(raw, (list, tuple, set)):
        return []
    return sorted({p for p in raw if isinstance(p, str) and p in VALID_PERMISSIONS})


def effective_permissions(user):
    """Every `"resource.action"` this user actually holds. docs/02 §2.3.

        is_active is False        →  nothing at all
        superuser                 →  everything
        explicit list, non-empty  →  exactly that list, filtered to the catalogue
        explicit list empty       →  the role's preset

    Three things here are load-bearing and none of them are obvious:

    **Inactive means nothing, not the preset.** Awliaa returns `set()` when the
    staff profile is missing or deactivated, deliberately: falling back to the
    role there would leave a dismissed employee with working access, because the
    role outlives the dismissal. A dismissed accountant must not still be able to
    collect at the counter (docs/WORKLOG F1).

    **The saved list is intersected with `VALID_PERMISSIONS`.** A string left
    over from an older release — a resource since renamed, an action since
    removed — drops instead of granting something the catalogue no longer
    describes. The docs described the fallback; the filtering is the safer half.

    **The preset is never merged with the list.** Once an admin customises a
    person, that list is the whole truth for them. Merging would mean unticking a
    box the preset grants does nothing at all, which is the most dangerous kind
    of permission bug: the admin believes they revoked access, and did not.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return set()

    if not getattr(user, 'is_active', False):
        return set()

    # Django's own contract, and how `create_admin` makes the first account on a
    # fresh install — which necessarily exists before any Role does.
    if getattr(user, 'is_superuser', False):
        return set(VALID_PERMISSIONS)

    saved = getattr(user, 'permissions', None) or []
    if saved:
        return {p for p in saved if isinstance(p, str)} & VALID_PERMISSIONS

    role = getattr(user, 'role', None)
    matrix = getattr(role, 'permission_matrix', None)
    if not isinstance(matrix, dict):
        return set()
    return flatten(matrix) & VALID_PERMISSIONS


def permission_resolver(user):
    """The hook `core.permissions` calls, named by `SIES_PERMISSION_RESOLVER`.

    Core owns `HasPermission('fees.collect')` and knows nothing about this
    catalogue; this one function is the whole seam between them, which is what
    keeps `core` importable by every app without importing any (docs/06 §2).
    """
    return effective_permissions(user)


def has_permission(user, resource, action):
    """True if *user* may perform *action* on *resource*."""
    return f'{resource}.{action}' in effective_permissions(user)


# What an unmapped custom `@action` needs, by HTTP method. Deliberately NOT the
# same table as `VIEWSET_ACTION_MAP` below: there, POST on a collection really
# does mean create. On a custom action it almost never does — it hides a row,
# approves it, collects against it, publishes it. Mapping a custom POST to
# `create` would let `fees.create` authorise the `collect` action, which is a
# different and much larger decision (docs/WORKLOG F1).
POST_IS_AN_UPDATE = {
    'GET': 'view',
    'HEAD': 'view',
    'OPTIONS': 'view',
    'POST': 'update',
    'PUT': 'update',
    'PATCH': 'update',
    'DELETE': 'delete',
}

# The standard ModelViewSet actions — the only ones where POST means create,
# because DRF generated them and we know exactly what they do.
VIEWSET_ACTION_MAP = {
    'list': 'view',
    'retrieve': 'view',
    'create': 'create',
    'update': 'update',
    'partial_update': 'update',
    'destroy': 'delete',
}


class HasResourcePermission(BasePermission):
    """Gate a viewset on one catalogue resource.

        class FeeViewSet(BranchScopedViewSet):
            permission_classes = [IsAuthenticated, HasResourcePermission]
            permission_resource = 'fees'
            permission_action_map = {'collect': 'collect'}

    The resource comes from the view; the action from what the view is doing.
    A custom `@action` the method map describes badly names its own action in
    `permission_action_map` — taking money is the case that forces this, since
    `collect` is its own checkbox and inferring `update` would mean an admin who
    ticks `fees.collect` finds it still does not work.
    """

    message = 'You do not have permission to do this.'
    # The SPA switches on this code, not on the sentence (docs/WORKLOG F15).
    code = 'permission_denied'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return False

        resource = getattr(view, 'permission_resource', None)
        if not resource:
            # A view naming no resource is gated by whatever else is in its
            # permission_classes. Returning False here would break every view
            # that deliberately relies on IsAuthenticated alone.
            return True

        declared = getattr(view, 'permission_action_map', None) or {}
        view_action = getattr(view, 'action', None)

        if view_action is not None:
            action = (
                declared.get(view_action)
                or VIEWSET_ACTION_MAP.get(view_action)
                or POST_IS_AN_UPDATE.get(request.method, 'view')
            )
        else:
            # A plain APIView has no `action`. The method is all there is.
            action = POST_IS_AN_UPDATE.get(request.method, 'view')

        return has_permission(user, resource, action)

    def has_object_permission(self, request, view, obj):
        # Object-level access is branch scoping's job: BranchScopedViewSet
        # already made another institution's rows invisible, so a 404 answers
        # before this is ever consulted (CLAUDE.md §5).
        return self.has_permission(request, view)
