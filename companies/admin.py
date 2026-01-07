from django.contrib import admin
from .models import Company, Follow, Filing, Financial

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("ticker", "exchange", "currency", "name")
    search_fields = ("ticker", "name")
    list_filter = ("exchange", "currency")


admin.site.register(Follow)
admin.site.register(Filing)
admin.site.register(Financial)