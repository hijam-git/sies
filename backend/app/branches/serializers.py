"""Shape and validation for the branches API (CLAUDE.md §4.3).

`branch` is never a writable field on anything here. `BranchScopedViewSet`
stamps it server-side from `request.branch`, and leaving it off the serializer is
the second of the two independent reasons a `branch` in a POST body does nothing
(docs/02 §3).
"""

from rest_framework import serializers

from core.middleware import get_branch

from .models import Branch, Session, Stream


class BranchSerializer(serializers.ModelSerializer):
    """The institution, as the SPA's `Branch` interface expects it.

    `lib/api.ts` reads `id, name, name_bn, name_ar, code, institution_type,
    address, phone, email, logo, established_year, is_active` — those are the
    branch-switcher fields. The policy columns are here too, because the
    institution-settings screen edits them and there is no second endpoint.
    """

    institution_type_display = serializers.CharField(
        source='get_institution_type_display', read_only=True,
    )

    class Meta:
        model = Branch
        fields = [
            'id',
            'name', 'name_bn', 'name_ar',
            'institution_type', 'institution_type_display',
            'code', 'established_year',
            'address', 'address_bn', 'district', 'thana',
            'phone', 'alt_phone', 'email', 'logo',
            'head', 'current_session',
            'fine_rule',
            'attendance_window_minutes',
            'restrict_teachers_to_assigned_classes',
            'activity_retention_days',
            'weekly_off_days',
            'sms_enabled', 'sms_sender_id', 'default_language',
            'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_code(self, value):
        """Unique case-insensitively, because `Branch.save()` upper-cases it.

        Without this the model would raise the uniqueness error from the database
        after the serializer had already said the payload was fine, and the SPA
        would get a generic integrity message instead of a field error on `code`.
        """
        code = (value or '').strip().upper()
        if not code:
            raise serializers.ValidationError('A code is required · কোড দিতে হবে।')

        clash = Branch.objects.filter(code=code)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(
                f'The code "{code}" is already used by another institution · '
                f'এই কোডটি অন্য প্রতিষ্ঠান ব্যবহার করছে।'
            )
        return code

    def validate_current_session(self, value):
        """A branch's current session must be one of its own.

        Nothing else stops it: `current_session` is a plain FK to a
        branch-scoped table, so without this an admin could point Dhaka at
        Chittagong's academic year and every default on every new record would
        follow it.
        """
        if value is not None and self.instance is not None and value.branch_id != self.instance.pk:
            raise serializers.ValidationError(
                'That session belongs to another institution · '
                'ওই শিক্ষাবর্ষ অন্য প্রতিষ্ঠানের।'
            )
        return value

    def validate_weekly_off_days(self, value):
        """A list of three-letter day names, lower-cased.

        The month attendance grid reads this on every render; a dict or a
        stray integer would break the grid rather than the settings form, which
        is a long way from where the mistake was made.
        """
        if not isinstance(value, list):
            raise serializers.ValidationError(
                'Expected a list of days like ["fri"] · ["fri"] আকারে তালিকা দিন।'
            )

        valid = {'sat', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri'}
        days = [str(day).strip().lower() for day in value]
        unknown = sorted(set(days) - valid)
        if unknown:
            raise serializers.ValidationError(
                f'Not day names: {", ".join(unknown)} · অজানা দিন।'
            )
        return days


class StreamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stream
        fields = ['id', 'code', 'name', 'name_bn', 'order', 'is_active',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_code(self, value):
        """Unique within the branch, checked here so the caller gets a field error.

        `Meta.constraints` is the real guarantee — this only makes the common
        case a 400 on `code` rather than an integrity error the form cannot
        attach to an input.
        """
        code = (value or '').strip().lower()
        if not code:
            raise serializers.ValidationError('A code is required · কোড দিতে হবে।')

        branch = get_branch(self.context['request'])
        clash = Stream.objects.filter(code=code)
        # A platform admin without ?branch= cannot create anything anyway —
        # BranchScopedMixin.perform_create answers that with a 400 — so scoping
        # the check to a real branch is the only case worth checking.
        if hasattr(branch, 'pk'):
            clash = clash.filter(branch=branch)
        elif self.instance is not None:
            clash = clash.filter(branch=self.instance.branch_id)
        else:
            return code

        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(
                f'The stream code "{code}" already exists here · '
                f'এই শাখা কোড আগে থেকেই আছে।'
            )
        return code


class SessionSerializer(serializers.ModelSerializer):
    """An academic year and the streams it covers.

    `streams` is writable as a list of ids and validated against the caller's own
    branch — a scoped queryset filters what you can *read*, and nothing else
    would stop a session pointing at another institution's stream.
    """

    streams = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Stream.objects.all(), required=False,
    )

    class Meta:
        model = Session
        fields = ['id', 'name', 'streams', 'starts_on', 'ends_on', 'is_current',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_streams(self, value):
        branch = get_branch(self.context['request'])
        branch_id = getattr(branch, 'pk', None)
        if branch_id is None and self.instance is not None:
            branch_id = self.instance.branch_id
        if branch_id is None:
            return value

        foreign = [stream for stream in value if stream.branch_id != branch_id]
        if foreign:
            raise serializers.ValidationError(
                'Those streams belong to another institution · '
                'ওই শাখাগুলো অন্য প্রতিষ্ঠানের।'
            )
        return value

    def validate(self, attrs):
        """A session must end after it starts.

        `Meta.constraints` enforces it in the database; repeating it here turns
        a 500-shaped integrity error into a 400 the form can point at.
        """
        starts_on = attrs.get('starts_on', getattr(self.instance, 'starts_on', None))
        ends_on = attrs.get('ends_on', getattr(self.instance, 'ends_on', None))
        if starts_on and ends_on and ends_on <= starts_on:
            raise serializers.ValidationError({
                'ends_on': 'The session must end after it starts · '
                           'শিক্ষাবর্ষ শুরুর পরে শেষ হতে হবে।',
            })
        return attrs
