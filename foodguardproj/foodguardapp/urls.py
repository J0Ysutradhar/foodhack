from django.urls import path

from .views import (
	AnalyzeProcessView,
	AnalyzerView,
	DashboardStatsAPI,
	DashboardView,
	HistoryDeleteView,
	HistoryDetailView,
	HistoryListView,
	LandingView,
	LoginView,
	LogoutView,
	ProfileEditView,
	ProfileSetupView,
	SignUpView,
)

app_name = "foodguardapp"

urlpatterns = [
	path("", LandingView.as_view(), name="landing"),
	path("accounts/signup/", SignUpView.as_view(), name="signup"),
	path("accounts/login/", LoginView.as_view(), name="login"),
	path("accounts/logout/", LogoutView.as_view(), name="logout"),
	path("profile/setup/", ProfileSetupView.as_view(), name="profile_setup"),
	path("profile/edit/", ProfileEditView.as_view(), name="profile_edit"),
	path("dashboard/", DashboardView.as_view(), name="dashboard"),
	path("analyze/", AnalyzerView.as_view(), name="analyzer"),
	path("analyze/process/", AnalyzeProcessView.as_view(), name="analyze_process"),
	path("history/", HistoryListView.as_view(), name="history_list"),
	path("history/<int:pk>/", HistoryDetailView.as_view(), name="history_detail"),
	path("history/<int:pk>/delete/", HistoryDeleteView.as_view(), name="history_delete"),
	path("api/dashboard-stats/", DashboardStatsAPI.as_view(), name="dashboard_stats_api"),
]
