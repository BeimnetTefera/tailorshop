from django.contrib import admin

from . import models


@admin.register(models.StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone", "language")
    list_filter = ("role",)


class PaymentInline(admin.TabularInline):
    model = models.Payment
    extra = 0


class NoteInline(admin.TabularInline):
    model = models.StageNote
    extra = 0


class TaskInline(admin.TabularInline):
    model = models.WorkerTask
    extra = 0


@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("code", "customer", "style", "stage", "current_worker", "due_date", "total_price")
    list_filter = ("stage", "category", "priority")
    search_fields = ("customer__name", "customer__phone", "style__code", "style__name")
    inlines = [PaymentInline, TaskInline, NoteInline]


@admin.register(models.Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "created_at")
    search_fields = ("name", "phone")


@admin.register(models.Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "phone", "rate_per_task", "is_active")
    list_filter = ("role", "is_active")


class StylePhotoInline(admin.TabularInline):
    model = models.StylePhoto
    extra = 0


@admin.register(models.Style)
class StyleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "gender", "is_popular")
    list_filter = ("category", "gender")
    search_fields = ("code", "name")
    inlines = [StylePhotoInline]


@admin.register(models.Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("name", "material_type", "price", "quantity", "unit")
    list_filter = ("material_type",)
    filter_horizontal = ("used_for",)


@admin.register(models.WorkerTask)
class WorkerTaskAdmin(admin.ModelAdmin):
    list_display = ("worker", "order", "stage", "started_on", "finished_on", "amount", "paid_on")
    list_filter = ("stage", "worker")


@admin.register(models.Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("item", "quantity", "amount", "status", "customer_name", "created_at")
    list_filter = ("status",)


admin.site.register(models.Tibebe)
admin.site.register(models.FreeSizeItem)
admin.site.register(models.Payment)
admin.site.register(models.MaterialUsage)
admin.site.register(models.Activity)
admin.site.site_header = "Tailor shop admin"
