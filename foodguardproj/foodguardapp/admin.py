from django.contrib import admin

from .models import CustomUser, FoodAnalysis, UserProfile


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
	ordering = ("-date_joined",)
	list_display = ("email", "username", "is_staff", "is_active", "date_joined")
	list_filter = ("is_staff", "is_active", "date_joined")
	search_fields = ("email", "username")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
	list_display = (
		"user",
		"full_name",
		"area_in_dhaka",
		"dietary_restrictions",
		"profile_complete",
		"updated_at",
	)
	list_filter = ("dietary_restrictions", "profile_complete", "activity_level")
	search_fields = ("user__email", "full_name", "area_in_dhaka")


@admin.register(FoodAnalysis)
class FoodAnalysisAdmin(admin.ModelAdmin):
	list_display = (
		"user",
		"food_name_detected",
		"safety_score",
		"safety_verdict",
		"is_halal_flagged",
		"created_at",
	)
	list_filter = ("safety_verdict", "is_halal_flagged", "is_allergen_flagged", "created_at")
	search_fields = ("user__email", "food_name_detected")
