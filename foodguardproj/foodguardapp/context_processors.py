def profile_status(request):
    if not request.user.is_authenticated:
        return {
            "profile_completion": 0,
            "profile_incomplete": False,
        }

    profile = getattr(request.user, "profile", None)
    completion = profile.completion_percentage if profile else 0
    return {
        "profile_completion": completion,
        "profile_incomplete": completion < 100,
    }
