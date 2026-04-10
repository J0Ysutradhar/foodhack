import logging
import json
import time
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from .forms import AnalyzeFoodForm, EmailLoginForm, HistoryFilterForm, ProfileForm, SignUpForm
from .models import FoodAnalysis, UserProfile
from .services import GeminiFoodAnalyzer


logger = logging.getLogger(__name__)


def _user_profile(user):
	profile, _ = UserProfile.objects.get_or_create(
		user=user,
		defaults={"full_name": user.username or "FoodGuard User"},
	)
	return profile


def _normalize_verdict(value: str) -> str:
	mapping = {
		"safe": "Safe",
		"caution": "Caution",
		"avoid": "Avoid",
	}
	return mapping.get(str(value).strip().lower(), "Caution")


def _greeting() -> str:
	hour = timezone.localtime().hour
	if hour < 12:
		return "Good morning"
	if hour < 18:
		return "Good afternoon"
	return "Good evening"


def _build_health_alerts(analyses: list[FoodAnalysis], profile: UserProfile) -> list[str]:
	alerts = []
	conditions = {item.lower() for item in (profile.health_conditions or [])}

	high_sodium_count = 0
	high_carb_count = 0
	for item in analyses:
		nutrition = (item.analysis_json or {}).get("estimated_nutrition", {})
		sodium = nutrition.get("sodium_mg")
		carbs = nutrition.get("carbs_g")
		if isinstance(sodium, (int, float)) and sodium >= 900:
			high_sodium_count += 1
		if isinstance(carbs, (int, float)) and carbs >= 65:
			high_carb_count += 1

	if {"high bp", "heart disease"} & conditions and high_sodium_count >= 3:
		alerts.append("You had 3+ high-sodium meals this week. Please watch your blood pressure.")
	if "diabetes" in conditions and high_carb_count >= 3:
		alerts.append("Your recent meals are high in carbs. Consider portion control for glucose balance.")
	if not alerts and analyses:
		avg_score = sum(item.safety_score for item in analyses) / len(analyses)
		if avg_score < 55:
			alerts.append("Your weekly average safety score is low. Try choosing less oily and lower-sodium meals.")
	if not alerts:
		alerts.append("No major warning trends found this week. Keep making balanced food choices.")

	return alerts


class LandingView(TemplateView):
	template_name = "landing.html"


class SignUpView(FormView):
	template_name = "auth/signup.html"
	form_class = SignUpForm
	success_url = reverse_lazy("foodguardapp:profile_setup")

	def form_valid(self, form):
		user = form.save()
		login(
			self.request,
			user,
			backend="foodguardapp.auth_backends.EmailOrUsernameModelBackend",
		)
		messages.success(self.request, "Welcome to FoodGuard AI. Please complete your profile.")
		return redirect(self.get_success_url())


class LoginView(FormView):
	template_name = "auth/login.html"
	form_class = EmailLoginForm
	success_url = reverse_lazy("foodguardapp:dashboard")

	def dispatch(self, request, *args, **kwargs):
		if request.user.is_authenticated:
			return redirect("foodguardapp:dashboard")
		return super().dispatch(request, *args, **kwargs)

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["request"] = self.request
		return kwargs

	def form_valid(self, form):
		user = form.get_user()
		login(self.request, user)
		if not form.cleaned_data.get("remember_me"):
			self.request.session.set_expiry(0)

		next_url = self.request.GET.get("next")
		return redirect(next_url or self.get_success_url())


class LogoutView(View):
	def post(self, request, *args, **kwargs):
		logout(request)
		return redirect("foodguardapp:landing")

	def get(self, request, *args, **kwargs):
		return HttpResponseNotAllowed(["POST"])


class ProfileSetupView(LoginRequiredMixin, FormView):
	template_name = "profile/setup.html"
	form_class = ProfileForm
	success_url = reverse_lazy("foodguardapp:dashboard")

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["instance"] = _user_profile(self.request.user)
		return kwargs

	def form_valid(self, form):
		profile = form.save(commit=False)
		profile.user = self.request.user
		profile.save()
		messages.success(self.request, "Your profile has been saved successfully.")
		return super().form_valid(form)


class ProfileEditView(LoginRequiredMixin, FormView):
	template_name = "profile/edit.html"
	form_class = ProfileForm
	success_url = reverse_lazy("foodguardapp:dashboard")

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["instance"] = _user_profile(self.request.user)
		return kwargs

	def form_valid(self, form):
		profile = form.save(commit=False)
		profile.user = self.request.user
		profile.save()
		messages.success(self.request, "Profile updated.")
		return super().form_valid(form)


class DashboardView(LoginRequiredMixin, TemplateView):
	template_name = "dashboard.html"

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		user = self.request.user
		profile = _user_profile(user)
		analyses_qs = FoodAnalysis.objects.filter(user=user)

		today = timezone.localdate()
		week_start = today - timedelta(days=6)
		week_qs = analyses_qs.filter(created_at__date__gte=week_start)
		week_analyses = list(week_qs)

		total_analyses = analyses_qs.count()
		avg_week_score = week_qs.aggregate(avg=Avg("safety_score"))["avg"] or 0
		analyses_today = analyses_qs.filter(created_at__date=today).count()
		recent_analyses = analyses_qs[:5]

		trend_rows = (
			week_qs.annotate(day=TruncDate("created_at"))
			.values("day")
			.annotate(avg_score=Avg("safety_score"), total=Count("id"))
			.order_by("day")
		)
		trend_map = {row["day"]: row for row in trend_rows}

		weekly_summary = []
		for offset in range(7):
			day = week_start + timedelta(days=offset)
			row = trend_map.get(day)
			weekly_summary.append(
				{
					"day_name": day.strftime("%a"),
					"date": day,
					"count": row["total"] if row else 0,
					"avg_score": round(row["avg_score"], 1) if row and row["avg_score"] else None,
				}
			)

		foods_to_avoid = list(
			analyses_qs.values("food_name_detected")
			.annotate(avg_score=Avg("safety_score"), total=Count("id"))
			.filter(total__gte=2, avg_score__lt=50)
			.order_by("avg_score")[:5]
		)

		context.update(
			{
				"greeting": _greeting(),
				"profile": profile,
				"total_analyses": total_analyses,
				"avg_week_score": round(avg_week_score, 1),
				"analyses_today": analyses_today,
				"recent_analyses": recent_analyses,
				"health_alerts": _build_health_alerts(week_analyses, profile),
				"foods_to_avoid": foods_to_avoid,
				"weekly_summary": weekly_summary,
			}
		)
		return context


class DashboardStatsAPI(LoginRequiredMixin, View):
	def get(self, request, *args, **kwargs):
		today = timezone.localdate()
		week_start = today - timedelta(days=6)
		analyses = FoodAnalysis.objects.filter(
			user=request.user,
			created_at__date__gte=week_start,
		)

		trend_rows = (
			analyses.annotate(day=TruncDate("created_at"))
			.values("day")
			.annotate(avg_score=Avg("safety_score"))
			.order_by("day")
		)
		trend_map = {row["day"]: row["avg_score"] for row in trend_rows}

		labels = []
		values = []
		for offset in range(7):
			day = week_start + timedelta(days=offset)
			labels.append(day.strftime("%a"))
			score = trend_map.get(day)
			values.append(round(score, 1) if score is not None else 0)

		return JsonResponse({"labels": labels, "scores": values})


class AnalyzerView(LoginRequiredMixin, TemplateView):
	template_name = "analyzer.html"

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["form"] = AnalyzeFoodForm()
		context["profile"] = _user_profile(self.request.user)
		return context


class AnalyzeProcessView(LoginRequiredMixin, View):
	def handle_no_permission(self):
		if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
			return JsonResponse(
				{
					"success": False,
					"message": "Your session expired. Please log in again.",
				},
				status=401,
			)
		return super().handle_no_permission()

	def post(self, request, *args, **kwargs):
		profile = _user_profile(request.user)
		if not profile.profile_complete:
			return JsonResponse(
				{
					"success": False,
					"message": "Complete your profile setup before analyzing food.",
				},
				status=400,
			)

		rate_key = f"foodguard-rate-limit-{request.user.pk}"
		now_ts = time.time()
		last_ts = cache.get(rate_key)
		if last_ts and (now_ts - float(last_ts)) < settings.ANALYSIS_RATE_LIMIT_SECONDS:
			wait_for = settings.ANALYSIS_RATE_LIMIT_SECONDS - int(now_ts - float(last_ts))
			return JsonResponse(
				{
					"success": False,
					"message": f"Please wait {max(wait_for, 1)} seconds before the next analysis.",
				},
				status=429,
			)

		form = AnalyzeFoodForm(request.POST, request.FILES)
		if not form.is_valid():
			return JsonResponse(
				{
					"success": False,
					"errors": form.errors.get_json_data(),
				},
				status=400,
			)

		try:
			analyzer = GeminiFoodAnalyzer()
			start_time = time.monotonic()
			result_payload = analyzer.analyze(
				image_file=form.cleaned_data["image"],
				profile=profile,
				user_note=form.cleaned_data.get("user_note", ""),
			)
			processing_ms = int((time.monotonic() - start_time) * 1000)
			cache.set(rate_key, now_ts, timeout=settings.ANALYSIS_RATE_LIMIT_SECONDS)

			score = result_payload.get("safety_score", 50)
			try:
				score = int(score)
			except (TypeError, ValueError):
				score = 50
			score = max(0, min(100, score))

			verdict = _normalize_verdict(result_payload.get("safety_verdict", "caution"))
			halal_status = str(result_payload.get("halal_status", "uncertain")).lower()
			is_halal_flagged = halal_status in {"not halal", "haram", "uncertain", "unknown"}

			allergy_terms = [item.replace("Other: ", "").lower() for item in (profile.allergies or [])]
			searchable = json.dumps(
				{
					"flags": result_payload.get("profile_flags", []),
					"ingredients": result_payload.get("ingredients_detected", []),
					"warnings": result_payload.get("health_warnings", []),
				}
			).lower()
			is_allergen_flagged = any(term and term in searchable for term in allergy_terms)

			saved = FoodAnalysis.objects.create(
				user=request.user,
				image=form.cleaned_data["image"],
				user_note=form.cleaned_data.get("user_note", ""),
				food_name_detected=result_payload.get("food_name", "Unknown food"),
				safety_score=score,
				safety_verdict=verdict,
				analysis_json=result_payload,
				is_halal_flagged=is_halal_flagged,
				is_allergen_flagged=is_allergen_flagged,
				processing_time_ms=processing_ms,
			)
		except Exception:
			logger.exception("Analyze process failed for user_id=%s", request.user.pk)
			return JsonResponse(
				{
					"success": False,
					"message": "Unable to process this image right now. Please try again.",
				},
				status=500,
			)

		return JsonResponse(
			{
				"success": True,
				"message": "Saved to your history",
				"analysis": {
					"id": saved.id,
					"food_name": saved.food_name_detected,
					"score": saved.safety_score,
					"verdict": saved.safety_verdict,
					"created_at": timezone.localtime(saved.created_at).strftime("%d %b %Y, %I:%M %p"),
					"image_url": saved.image.url,
					"result": result_payload,
				},
			}
		)

	def get(self, request, *args, **kwargs):
		return HttpResponseNotAllowed(["POST"])


class HistoryListView(LoginRequiredMixin, ListView):
	template_name = "history/list.html"
	context_object_name = "analyses"
	paginate_by = 10

	def get_queryset(self):
		queryset = FoodAnalysis.objects.filter(user=self.request.user)
		self.filter_form = HistoryFilterForm(self.request.GET or None)
		if not self.filter_form.is_valid():
			return queryset

		verdict = self.filter_form.cleaned_data.get("verdict")
		period = self.filter_form.cleaned_data.get("period")
		date_from = self.filter_form.cleaned_data.get("date_from")
		date_to = self.filter_form.cleaned_data.get("date_to")

		if verdict:
			queryset = queryset.filter(safety_verdict=verdict)

		if period == "week":
			queryset = queryset.filter(created_at__date__gte=timezone.localdate() - timedelta(days=6))
		elif period == "month":
			queryset = queryset.filter(created_at__date__gte=timezone.localdate() - timedelta(days=30))

		if date_from:
			queryset = queryset.filter(created_at__date__gte=date_from)
		if date_to:
			queryset = queryset.filter(created_at__date__lte=date_to)

		return queryset

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["filter_form"] = getattr(self, "filter_form", HistoryFilterForm())
		return context


class HistoryDetailView(LoginRequiredMixin, DetailView):
	template_name = "history/detail.html"
	context_object_name = "analysis"

	def get_queryset(self):
		return FoodAnalysis.objects.filter(user=self.request.user)


class HistoryDeleteView(LoginRequiredMixin, View):
	def post(self, request, pk, *args, **kwargs):
		analysis = get_object_or_404(FoodAnalysis, pk=pk, user=request.user)
		analysis.delete()
		messages.success(request, "Analysis deleted.")
		return redirect("foodguardapp:history_list")

	def get(self, request, *args, **kwargs):
		return HttpResponseNotAllowed(["POST"])
