from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import UserAccount


@admin.register(UserAccount)
class UserAccountAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "is_active", "is_staff", "is_superuser", "date_joined")
    search_fields = ("email",)
    list_filter = ("is_active", "is_staff", "is_superuser")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "is_active", "is_staff", "is_superuser"),
            },
        ),
    )
    readonly_fields = ("last_login", "date_joined")
