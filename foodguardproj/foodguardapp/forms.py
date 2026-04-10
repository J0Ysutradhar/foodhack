import json

from PIL import Image, UnidentifiedImageError
from django import forms
from django.conf import settings
from django.contrib.auth import authenticate

from .constants import (
    ACTIVITY_LEVEL_CHOICES,
    COMMON_ALLERGY_CHOICES,
    DHAKA_AREAS,
    DIETARY_RESTRICTION_CHOICES,
    FITNESS_GOAL_CHOICES,
    GENDER_CHOICES,
    HEALTH_CONDITION_CHOICES,
)
from .models import CustomUser, UserProfile


BASE_INPUT_CLASS = (
    "w-full rounded-xl border border-gray-200 bg-white px-3 py-3 text-sm "
    "text-gray-900 focus:border-teal-700 focus:outline-none focus:ring-2 "
    "focus:ring-teal-700/20"
)


class SignUpForm(forms.ModelForm):
    full_name = forms.CharField(max_length=100)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ["full_name", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = BASE_INPUT_CLASS

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        email = self.cleaned_data["email"]
        password = self.cleaned_data["password1"]
        full_name = self.cleaned_data["full_name"].strip()
        user = CustomUser.objects.create_user(email=email, password=password)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.full_name = full_name
        profile.save()
        return user


class EmailLoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    remember_me = forms.BooleanField(required=False)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} {BASE_INPUT_CLASS}".strip()

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")
        if not email or not password:
            return cleaned_data

        self.user_cache = authenticate(
            self.request,
            username=email,
            password=password,
        )
        if self.user_cache is None:
            raise forms.ValidationError("Invalid email or password.")
        if not self.user_cache.is_active:
            raise forms.ValidationError("This account is disabled.")
        return cleaned_data

    def get_user(self):
        return self.user_cache


class ProfileForm(forms.ModelForm):
    area_in_dhaka = forms.ChoiceField(
        required=False,
        choices=[],
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS}),
    )
    health_conditions = forms.MultipleChoiceField(
        choices=HEALTH_CONDITION_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    allergies_common = forms.MultipleChoiceField(
        choices=COMMON_ALLERGY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    allergies_other = forms.CharField(required=False, max_length=200)

    class Meta:
        model = UserProfile
        fields = [
            "full_name",
            "age",
            "gender",
            "weight_kg",
            "height_cm",
            "area_in_dhaka",
            "health_conditions",
            "dietary_restrictions",
            "fitness_goal",
            "activity_level",
        ]

        widgets = {
            "full_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS}),
            "age": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0}),
            "gender": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "weight_kg": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "step": "0.1", "min": 0}),
            "height_cm": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "step": "0.1", "min": 0}),
            "area_in_dhaka": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "dietary_restrictions": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "fitness_goal": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "activity_level": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["gender"].choices = [("", "Select gender")] + list(GENDER_CHOICES)
        self.fields["area_in_dhaka"].choices = [
            ("", "Select your area")
        ] + [(item, item) for item in DHAKA_AREAS]
        self.fields["dietary_restrictions"].choices = list(DIETARY_RESTRICTION_CHOICES)
        self.fields["fitness_goal"].choices = [
            ("", "Select fitness goal")
        ] + list(FITNESS_GOAL_CHOICES)
        self.fields["activity_level"].choices = [
            ("", "Select activity level")
        ] + list(ACTIVITY_LEVEL_CHOICES)

        self.fields["allergies_other"].widget.attrs.update({
            "class": BASE_INPUT_CLASS,
            "placeholder": "Other allergies (optional)",
        })

        if self.instance and self.instance.pk:
            health_conditions = self._ensure_list(self.instance.health_conditions)
            allergies = self._ensure_list(self.instance.allergies)
            self.initial["health_conditions"] = health_conditions

            allergy_defaults = []
            allergy_other = []
            known_values = {choice[0] for choice in COMMON_ALLERGY_CHOICES}
            for item in allergies:
                if item in known_values:
                    allergy_defaults.append(item)
                else:
                    allergy_other.append(item.replace("Other: ", ""))
            self.initial["allergies_common"] = allergy_defaults
            self.initial["allergies_other"] = ", ".join(allergy_other)

    @staticmethod
    def _ensure_list(value):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
                if isinstance(decoded, list):
                    return decoded
            except json.JSONDecodeError:
                pass
            return [part.strip() for part in value.split(",") if part.strip()]
        return []

    def clean_health_conditions(self):
        conditions = self.cleaned_data.get("health_conditions", [])
        if "None" in conditions and len(conditions) > 1:
            conditions = ["None"]
        return conditions

    def clean_allergies_other(self):
        raw = self.cleaned_data.get("allergies_other", "")
        return ", ".join([item.strip() for item in raw.split(",") if item.strip()])

    def save(self, commit=True):
        instance = super().save(commit=False)
        allergies = list(self.cleaned_data.get("allergies_common", []))
        other = self.cleaned_data.get("allergies_other")
        if other:
            allergies.extend([f"Other: {item.strip()}" for item in other.split(",") if item.strip()])

        instance.health_conditions = self.cleaned_data.get("health_conditions", [])
        instance.allergies = allergies
        if commit:
            instance.save()
        return instance


class AnalyzeFoodForm(forms.Form):
    image = forms.ImageField()
    user_note = forms.CharField(
        required=False,
        max_length=400,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": BASE_INPUT_CLASS,
                "placeholder": "Add a note about this food (optional)",
            }
        ),
    )

    def clean_image(self):
        image = self.cleaned_data["image"]
        max_upload = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if image.size > max_upload:
            raise forms.ValidationError(
                f"Image exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit."
            )

        try:
            uploaded = Image.open(image)
            image_format = (uploaded.format or "").upper()
            if image_format not in {"JPEG", "PNG", "WEBP"}:
                raise forms.ValidationError("Only JPEG, PNG, and WEBP images are allowed.")
        except UnidentifiedImageError as exc:
            raise forms.ValidationError("The uploaded file is not a valid image.") from exc
        finally:
            image.seek(0)

        return image


class HistoryFilterForm(forms.Form):
    verdict = forms.ChoiceField(
        required=False,
        choices=[("", "All verdicts"), ("Safe", "Safe"), ("Caution", "Caution"), ("Avoid", "Avoid")],
    )
    period = forms.ChoiceField(
        required=False,
        choices=[("", "Any period"), ("week", "This week"), ("month", "This month")],
    )
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} {BASE_INPUT_CLASS}".strip()
