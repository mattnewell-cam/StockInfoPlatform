from django.contrib import admin
from .models import Company, Follow, Filing, Financial

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("ticker", "exchange", "currency", "name", "description", "special_sits", "writeups")
    search_fields = ("ticker", "name")
    list_filter = ("exchange", "currency")

@admin.register(Financial)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("company", "period_end_date", "statement", "metric", "value")
    search_fields = ("period_end_date", "metric")
    list_filter = ("company", "statement")


admin.site.register(Follow)
admin.site.register(Filing)
