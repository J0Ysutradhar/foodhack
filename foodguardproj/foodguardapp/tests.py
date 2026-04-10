from django.test import TestCase
from django.urls import reverse

from .forms import ProfileForm
from .models import CustomUser, UserProfile


class FoodGuardAppTests(TestCase):
	def setUp(self):
		self.password = "SafePassword123!"
		self.user = CustomUser.objects.create_user(
			email="tester@example.com",
			password=self.password,
		)

	def test_landing_page_loads(self):
		response = self.client.get(reverse("foodguardapp:landing"))
		self.assertEqual(response.status_code, 200)

	def test_signup_creates_user(self):
		response = self.client.post(
			reverse("foodguardapp:signup"),
			{
				"full_name": "New User",
				"email": "new@example.com",
				"password1": "TestPass123!",
				"password2": "TestPass123!",
			},
		)
		self.assertEqual(response.status_code, 302)
		self.assertTrue(CustomUser.objects.filter(email="new@example.com").exists())

	def test_profile_completion_calculation(self):
		profile = UserProfile.objects.get(user=self.user)
		profile.full_name = "Test User"
		profile.age = 30
		profile.gender = "Male"
		profile.area_in_dhaka = "Mirpur"
		profile.dietary_restrictions = "Halal Only"
		profile.fitness_goal = "Maintain"
		profile.activity_level = "Moderate"
		profile.save()
		self.assertEqual(profile.completion_percentage, 100)
		self.assertTrue(profile.profile_complete)

	def test_dashboard_requires_login(self):
		response = self.client.get(reverse("foodguardapp:dashboard"))
		self.assertEqual(response.status_code, 302)

	def test_analyze_requires_complete_profile(self):
		self.client.login(username=self.user.email, password=self.password)
		response = self.client.post(reverse("foodguardapp:analyze_process"), {})
		self.assertEqual(response.status_code, 400)

	def test_profile_form_contains_dhaka_area_choices(self):
		form = ProfileForm()
		choices = list(form.fields["area_in_dhaka"].choices)
		self.assertGreater(len(choices), 1)
		self.assertIn(("Mirpur", "Mirpur"), choices)
