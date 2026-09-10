"""Django admin registrations — for debugging, not for daily use.

The institution's own people work in the SPA; this is where a developer looks
when something is wrong with the data itself. So the list views are tuned for
"find the row", not for data entry.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import ActivityLog, Role, User


class SiesUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('phone', 'name')


class SiesUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = '__all__'


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Django's UserAdmin, retargeted at a phone login.

    Subclassed rather than written fresh so the password widget stays the
    hashed-field one: a plain ModelAdmin renders `password` as a text input and
    saves whatever is typed as the hash, producing an account nobody can log in
    to and no error anywhere.
    """

    add_form = SiesUserCreationForm
    form = SiesUserChangeForm
    model = User

    list_display = ('phone', 'name', 'user_type', 'branch', 'role',
                    'is_active', 'must_change_password', 'last_login')
    list_filter = ('user_type', 'is_active', 'is_staff', 'is_superuser',
                   'must_change_password', 'language', 'branch', 'role')
    search_fields = ('phone', 'name', 'name_bn', 'email')
    ordering = ('name', 'phone')
    list_select_related = ('branch', 'role')
    readonly_fields = ('last_login', 'last_login_ip', 'created_at', 'updated_at')
    autocomplete_fields = ('role',)

    fieldsets = (
        (None, {'fields': ('phone', 'password')}),
        ('Person', {'fields': ('name', 'name_bn', 'email', 'photo', 'language')}),
        ('Placement', {'fields': ('user_type', 'branch', 'role')}),
        # Free text, and deliberately so: it is a list of catalogue strings and
        # the SPA's checkbox screen is the tool for editing it. Anyone here is
        # debugging and wants to see the literal value.
        ('Access', {
            'fields': ('permissions', 'is_active', 'must_change_password',
                       'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('History', {'fields': ('last_login', 'last_login_ip',
                                'created_at', 'updated_at')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone', 'name', 'user_type', 'branch', 'role',
                       'password1', 'password2'),
        }),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'name_bn', 'is_system', 'is_active', 'user_count')
    list_filter = ('is_system', 'is_active')
    search_fields = ('name', 'name_bn')
    ordering = ('name',)

    @admin.display(description='users')
    def user_count(self, obj):
        return obj.users.count()


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """Read-only in the admin too, because the model refuses writes.

    Leaving it editable would produce a form that always fails to save, with the
    refusal surfacing as an unhandled ValidationError rather than as the rule it
    is.
    """

    list_display = ('created_at', 'user_label', 'action', 'model',
                    'object_label', 'branch', 'ip')
    list_filter = ('action', 'branch', 'model')
    search_fields = ('user_label', 'object_label', 'summary', 'object_id', 'ip')
    date_hierarchy = 'created_at'
    list_select_related = ('user', 'branch')
    ordering = ('-id',)

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
