from django.contrib import admin

from .models import Material, MaterialRate


class MaterialRateInline(admin.TabularInline):
    model = MaterialRate
    extra = 1
    ordering = ["-effective_date"]
    fields = ["city", "price_per_kg", "effective_date", "published_at"]


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ["id", "name_en", "name_ne", "abbr", "category", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name_en", "name_ne", "abbr"]
    inlines = [MaterialRateInline]


@admin.register(MaterialRate)
class MaterialRateAdmin(admin.ModelAdmin):
    """To change a price, add a new row with today's effective date."""

    list_display = ["material", "city", "price_per_kg", "effective_date", "published_at"]
    list_filter = ["city", "material__category", "effective_date"]
    date_hierarchy = "effective_date"
    list_select_related = ["material"]
