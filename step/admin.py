"""Admin registration.

Until the STEP interface is built this is the only view onto the data, so every
model is registered. Passport numbers and PINFL are deliberately kept out of
list displays and search fields — search terms reach query strings and server
logs, and these are regulated identifiers (spec §4.4).
"""

from django.contrib import admin

from step.models import (
    AcademicYear, Activity, ActivityParticipant, ActivityPlan, AliasMapping,
    Announcement, AnnouncementResponse, District, Educator, Evidence, Obligation,
    ObligationType, PendingSignup, ProgressEntry, Region, RosterImport, School,
    SchoolStaff, Session, SessionAttendance, Student, Submission, TeachingClass,
    Term, UnresolvedRow,
)


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "name_uz", "code", "is_city")
    search_fields = ("name", "name_uz", "code")


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "code")
    list_filter = ("region",)
    search_fields = ("name", "name_uz", "code")


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "district", "external_id")
    list_filter = ("district__region",)
    search_fields = ("name", "external_id")


@admin.register(Educator)
class EducatorAdmin(admin.ModelAdmin):
    # No passport_no or pinfl here, deliberately — spec §4.4.
    list_display = ("full_name", "email", "region", "school", "is_active", "missing_from_last_import")
    list_filter = ("region", "is_active", "missing_from_last_import")
    search_fields = ("full_name", "email")
    readonly_fields = ("created_at", "updated_at")


class UnresolvedRowInline(admin.TabularInline):
    model = UnresolvedRow
    extra = 0


@admin.register(RosterImport)
class RosterImportAdmin(admin.ModelAdmin):
    list_display = ("id", "imported_at", "row_count", "created_count", "updated_count", "unresolved_count")
    inlines = [UnresolvedRowInline]
    readonly_fields = ("imported_at",)


@admin.register(UnresolvedRow)
class UnresolvedRowAdmin(admin.ModelAdmin):
    list_display = ("roster_import", "row_number", "reason", "resolved")
    list_filter = ("resolved",)


@admin.register(AliasMapping)
class AliasMappingAdmin(admin.ModelAdmin):
    list_display = ("kind", "raw_value", "region", "district", "school")
    list_filter = ("kind",)
    search_fields = ("raw_value", "normalised")


@admin.register(PendingSignup)
class PendingSignupAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "submitted_at", "resolved")
    list_filter = ("resolved",)
    search_fields = ("full_name", "email")


class TermInline(admin.TabularInline):
    model = Term
    extra = 0


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("label", "start", "end", "is_current")
    inlines = [TermInline]


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ("name", "year", "sequence", "start", "end")
    list_filter = ("year",)


@admin.register(ObligationType)
class ObligationTypeAdmin(admin.ModelAdmin):
    list_display = ("name_template", "category", "cadence", "evidence_spec", "requires_review", "is_active")
    list_filter = ("category", "cadence", "requires_review", "is_active")
    search_fields = ("name_template",)


@admin.register(Obligation)
class ObligationAdmin(admin.ModelAdmin):
    list_display = ("display_name", "educator", "due_date", "status", "due_date_overridden")
    list_filter = ("status", "type__category", "period_kind", "educator__region")
    search_fields = ("educator__full_name",)
    date_hierarchy = "due_date"


class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("obligation", "revision", "submitted_at", "director_rating", "outcome", "reviewed_at")
    list_filter = ("outcome", "director_rating")
    inlines = [EvidenceInline]
    readonly_fields = ("submitted_at",)


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ("submission", "kind", "caption", "uploaded_at")
    list_filter = ("kind",)


class StudentInline(admin.TabularInline):
    model = Student
    extra = 0


@admin.register(TeachingClass)
class TeachingClassAdmin(admin.ModelAdmin):
    list_display = ("display_name", "grade", "slot", "educator")
    list_filter = ("grade", "slot")
    search_fields = ("display_name", "educator__full_name")
    inlines = [StudentInline]


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "teaching_class")
    list_filter = ("teaching_class__grade",)
    search_fields = ("full_name",)


@admin.register(ProgressEntry)
class ProgressEntryAdmin(admin.ModelAdmin):
    list_display = ("student", "checkpoint", "score", "skill", "created_at")
    list_filter = ("checkpoint", "skill")
    search_fields = ("student__full_name", "comment")
    readonly_fields = ("created_at",)


@admin.register(SchoolStaff)
class SchoolStaffAdmin(admin.ModelAdmin):
    list_display = ("full_name", "school", "created_at")
    list_filter = ("school",)
    search_fields = ("full_name",)
    readonly_fields = ("created_at",)


class SessionInline(admin.TabularInline):
    model = Session
    extra = 0


class ActivityParticipantInline(admin.TabularInline):
    model = ActivityParticipant
    extra = 0


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "educator", "school", "started_on", "archived_on")
    list_filter = ("kind", "school")
    search_fields = ("title", "educator__full_name")
    inlines = [ActivityParticipantInline, SessionInline]


@admin.register(ActivityParticipant)
class ActivityParticipantAdmin(admin.ModelAdmin):
    list_display = ("full_name", "activity", "student", "staff")
    list_filter = ("activity",)
    search_fields = ("full_name",)


class SessionAttendanceInline(admin.TabularInline):
    model = SessionAttendance
    extra = 0


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("activity", "scheduled_for", "held_on", "status", "recorded_at")
    list_filter = ("status", "activity")
    inlines = [SessionAttendanceInline]
    readonly_fields = ("recorded_at",)


@admin.register(SessionAttendance)
class SessionAttendanceAdmin(admin.ModelAdmin):
    list_display = ("session", "participant")
    list_filter = ("session__activity",)


@admin.register(ActivityPlan)
class ActivityPlanAdmin(admin.ModelAdmin):
    list_display = ("activity", "period", "created_at", "updated_at")
    list_filter = ("activity",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "requires_response", "is_active", "published_at", "respond_by")
    list_filter = ("requires_response", "is_active")
    readonly_fields = ("published_at",)


@admin.register(AnnouncementResponse)
class AnnouncementResponseAdmin(admin.ModelAdmin):
    list_display = ("announcement", "educator", "attending", "responded_at")
    list_filter = ("announcement", "attending")
    readonly_fields = ("responded_at",)
