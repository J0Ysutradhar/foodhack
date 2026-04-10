from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify

from .constants import (
	ACTIVITY_LEVEL_CHOICES,
	DIETARY_RESTRICTION_CHOICES,
	FITNESS_GOAL_CHOICES,
	GENDER_CHOICES,
)


class CustomUserManager(UserManager):
	"""User manager that treats email as the primary login identifier."""

	use_in_migrations = True

	def _build_unique_username(self, email: str) -> str:
		base = slugify(email.split("@")[0]).replace("-", "")[:24] or "foodguard"
		candidate = base
		counter = 1
		while self.model.objects.filter(username=candidate).exists():
			candidate = f"{base}{counter}"
			counter += 1
		return candidate

	def _create_user(self, email, password, **extra_fields):
		if not email:
			raise ValueError("Email is required")
		email = self.normalize_email(email)
		extra_fields.setdefault("username", self._build_unique_username(email))
		user = self.model(email=email, **extra_fields)
		user.set_password(password)
		user.save(using=self._db)
		return user

	def create_user(self, email, password=None, **extra_fields):
		extra_fields.setdefault("is_staff", False)
		extra_fields.setdefault("is_superuser", False)
		return self._create_user(email, password, **extra_fields)

	def create_superuser(self, email, password=None, **extra_fields):
		extra_fields.setdefault("is_staff", True)
		extra_fields.setdefault("is_superuser", True)

		if extra_fields.get("is_staff") is not True:
			raise ValueError("Superuser must have is_staff=True.")
		if extra_fields.get("is_superuser") is not True:
			raise ValueError("Superuser must have is_superuser=True.")

		return self._create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
	email = models.EmailField(unique=True)

	USERNAME_FIELD = "email"
	REQUIRED_FIELDS = []

	objects = CustomUserManager()

	def save(self, *args, **kwargs):
		if not self.username and self.email:
			self.username = self.__class__.objects._build_unique_username(self.email)
		super().save(*args, **kwargs)

	def __str__(self):
		return self.email


class UserProfile(models.Model):
	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="profile",
	)
	full_name = models.CharField(max_length=100)
	age = models.PositiveIntegerField(null=True, blank=True)
	gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True)
	weight_kg = models.FloatField(null=True, blank=True)
	height_cm = models.FloatField(null=True, blank=True)
	area_in_dhaka = models.CharField(max_length=100, blank=True)
	health_conditions = models.JSONField(default=list, blank=True)
	allergies = models.JSONField(default=list, blank=True)
	dietary_restrictions = models.CharField(
		max_length=30,
		choices=DIETARY_RESTRICTION_CHOICES,
		default="Halal Only",
	)
	fitness_goal = models.CharField(max_length=30, choices=FITNESS_GOAL_CHOICES, blank=True)
	activity_level = models.CharField(max_length=20, choices=ACTIVITY_LEVEL_CHOICES, blank=True)
	profile_complete = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-updated_at"]

	def _required_fields(self):
		return [
			self.full_name,
			self.age,
			self.gender,
			self.area_in_dhaka,
			self.dietary_restrictions,
			self.fitness_goal,
			self.activity_level,
		]

	@property
	def completion_percentage(self) -> int:
		required = self._required_fields()
		completed = sum(1 for item in required if item not in (None, ""))
		return int(round((completed / len(required)) * 100))

	def save(self, *args, **kwargs):
		self.profile_complete = self.completion_percentage == 100
		super().save(*args, **kwargs)

	def __str__(self):
		return f"{self.user.email} profile"


class FoodAnalysis(models.Model):
	SAFETY_VERDICT_CHOICES = [
		("Safe", "Safe"),
		("Caution", "Caution"),
		("Avoid", "Avoid"),
	]

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="food_analyses",
	)
	image = models.ImageField(upload_to="food_images/%Y/%m/%d/")
	user_note = models.TextField(blank=True)
	food_name_detected = models.CharField(max_length=200)
	safety_score = models.IntegerField(
		validators=[MinValueValidator(0), MaxValueValidator(100)],
	)
	safety_verdict = models.CharField(max_length=10, choices=SAFETY_VERDICT_CHOICES)
	analysis_json = models.JSONField(default=dict)
	is_halal_flagged = models.BooleanField(default=False)
	is_allergen_flagged = models.BooleanField(default=False)
	processing_time_ms = models.PositiveIntegerField(default=0)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return f"{self.food_name_detected} ({self.safety_score})"
