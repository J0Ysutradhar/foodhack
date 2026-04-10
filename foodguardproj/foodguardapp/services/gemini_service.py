import json
import time
from typing import Any

from django.conf import settings

SYSTEM_PROMPT = """
You are FoodGuard AI, an expert food safety analyst specialised in Bangladeshi
and South Asian cuisine. You analyse food photographs and provide detailed,
personalised safety assessments.

RULES:
1. Always respond ONLY in valid JSON. No markdown, no prose, no backticks.
2. Base your analysis on both the image and the user's health profile.
3. Be precise, practical, and culturally sensitive to Bangladeshi food culture.
4. For halal assessment, apply strict Hanafi fiqh standards used in Bangladesh.
5. Safety score must be calculated against the user's specific health profile,
   NOT a generic standard.
6. Suggestions must be specific and actionable - not generic advice.
7. If the image is not a food item, set food_detected: false and explain.
""".strip()

USER_MESSAGE_TEMPLATE = """
Analyse this food image and respond in the exact JSON format below.

USER HEALTH PROFILE:
Name: {name}
Age: {age}, Gender: {gender}
Weight: {weight_kg}kg, Height: {height_cm}cm
Area: {area_in_dhaka}, Dhaka
Health conditions: {health_conditions}
Allergies: {allergies}
Dietary restriction: {dietary_restrictions}
Fitness goal: {fitness_goal}
Activity level: {activity_level}

USER NOTE: {user_note}

RESPOND IN THIS EXACT JSON STRUCTURE:
{{
  "food_detected": true,
  "food_name": "Beef Kacchi Biryani",
  "confidence": "high",
  "safety_score": 58,
  "safety_verdict": "caution",
  "halal_status": "halal",
  "halal_note": "Beef is halal. No pork or alcohol detected.",
  "estimated_nutrition": {{
    "calories": 620,
    "protein_g": 28,
    "carbs_g": 72,
    "fat_g": 22,
    "sodium_mg": 980,
    "fiber_g": 3
  }},
  "ingredients_detected": ["beef", "basmati rice", "saffron", "onion", "ghee", "yogurt"],
  "profile_flags": [
    {{"flag": "High carbohydrate content", "reason": "Risky for your Type 2 Diabetes"}},
    {{"flag": "High sodium (980mg)", "reason": "Exceeds safe limit for your hypertension"}}
  ],
  "health_warnings": [
    "This meal contains ~72g of carbs - significantly above your recommended per-meal limit.",
    "The sodium content may spike your blood pressure. Avoid if you have not taken your medication."
  ],
  "suggestions": [
    "Eat only half the rice portion to halve the carb load.",
    "Drink a full glass of water before eating to slow glucose absorption.",
    "Consider pairing with a cucumber salad to add fibre."
  ],
  "freshness_assessment": "fresh",
  "freshness_note": "Food appears freshly prepared, good colour and texture visible.",
  "food_safety_concerns": [],
  "overall_summary": "Kacchi Biryani is a rich, high-calorie dish that poses specific risks for your diabetes and blood pressure. Enjoy in moderation with portion control."
}}
""".strip()


class GeminiFoodAnalyzer:
    """Wrapper around Gemini 2.5 Flash with strict JSON extraction."""

    def __init__(self):
        self.model_name = "gemini-2.5-flash"

    def analyze(self, image_file, profile, user_note: str = "") -> dict[str, Any]:
        started = time.monotonic()
        if not settings.GEMINI_API_KEY:
            fallback = self._fallback_response(profile)
            fallback["meta"] = {
                "source": "fallback",
                "reason": "missing_gemini_api_key",
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            return fallback

        try:
            import google.generativeai as genai
        except Exception:
            fallback = self._fallback_response(profile)
            fallback["meta"] = {
                "source": "fallback",
                "reason": "google-generativeai-not-installed",
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            return fallback

        prompt = USER_MESSAGE_TEMPLATE.format(
            name=profile.full_name or "User",
            age=profile.age or "Unknown",
            gender=profile.gender or "Unknown",
            weight_kg=profile.weight_kg or "Unknown",
            height_cm=profile.height_cm or "Unknown",
            area_in_dhaka=profile.area_in_dhaka or "Unknown",
            health_conditions=", ".join(profile.health_conditions or ["None"]),
            allergies=", ".join(profile.allergies or ["None"]),
            dietary_restrictions=profile.dietary_restrictions or "No Restriction",
            fitness_goal=profile.fitness_goal or "Maintain",
            activity_level=profile.activity_level or "Moderate",
            user_note=user_note or "No note provided",
        )

        image_file.seek(0)
        image_bytes = image_file.read()
        image_file.seek(0)
        mime_type = getattr(image_file, "content_type", "image/jpeg")

        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=SYSTEM_PROMPT,
            )
            response = model.generate_content(
                [
                    prompt,
                    {
                        "mime_type": mime_type,
                        "data": image_bytes,
                    },
                ],
                request_options={"timeout": 30},
            )
            response_text = getattr(response, "text", "") or ""
            payload = self._extract_json_payload(response_text)
            normalized = self._normalize_payload(payload)
            normalized["meta"] = {
                "source": "gemini",
                "model": self.model_name,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            return normalized
        except Exception:
            fallback = self._fallback_response(profile)
            fallback["meta"] = {
                "source": "fallback",
                "reason": "gemini_request_failed",
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            return fallback

    def _extract_json_payload(self, response_text: str) -> dict[str, Any]:
        cleaned = response_text.strip().replace("```json", "").replace("```", "").strip()
        json_start = cleaned.find("{")
        json_end = cleaned.rfind("}")
        if json_start == -1 or json_end == -1:
            raise ValueError("No JSON object found in model output")

        return json.loads(cleaned[json_start : json_end + 1])

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        score = payload.get("safety_score", 50)
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 50

        score = max(0, min(100, score))
        verdict = str(payload.get("safety_verdict", "caution")).strip().lower()
        if verdict not in {"safe", "caution", "avoid"}:
            verdict = "caution"

        payload["safety_score"] = score
        payload["safety_verdict"] = verdict
        payload.setdefault("food_detected", True)
        payload.setdefault("food_name", "Unknown food")
        payload.setdefault("confidence", "medium")
        payload.setdefault("halal_status", "uncertain")
        payload.setdefault("halal_note", "Unable to fully verify from image.")
        payload.setdefault("estimated_nutrition", {})
        payload.setdefault("ingredients_detected", [])
        payload.setdefault("profile_flags", [])
        payload.setdefault("health_warnings", [])
        payload.setdefault("suggestions", [])
        payload.setdefault("freshness_assessment", "unclear")
        payload.setdefault("freshness_note", "Image quality limits certainty.")
        payload.setdefault("food_safety_concerns", [])
        payload.setdefault("overall_summary", "Result generated with best-effort AI estimate.")
        return payload

    def _fallback_response(self, profile) -> dict[str, Any]:
        warnings = []
        suggestions = [
            "Prefer freshly cooked food from trusted places.",
            "Ask for less oil and salt when possible.",
            "Balance this meal with vegetables and water.",
        ]
        if "Diabetes" in (profile.health_conditions or []):
            warnings.append("Potential high-carb food can raise blood sugar.")
            suggestions.append("Choose smaller rice portions to reduce carb load.")
        if "High BP" in (profile.health_conditions or []):
            warnings.append("Street foods may contain high sodium levels.")
            suggestions.append("Avoid extra sauces and salty sides.")

        return {
            "food_detected": True,
            "food_name": "Food item detected",
            "confidence": "low",
            "safety_score": 55,
            "safety_verdict": "caution",
            "halal_status": "uncertain",
            "halal_note": "Unable to verify ingredients with high confidence.",
            "estimated_nutrition": {
                "calories": 450,
                "protein_g": 14,
                "carbs_g": 58,
                "fat_g": 17,
                "sodium_mg": 700,
                "fiber_g": 3,
            },
            "ingredients_detected": ["rice", "oil", "spices"],
            "profile_flags": [
                {
                    "flag": "Best effort analysis",
                    "reason": "Gemini response unavailable, generated fallback estimate",
                }
            ],
            "health_warnings": warnings,
            "suggestions": suggestions,
            "freshness_assessment": "unclear",
            "freshness_note": "Image details are limited.",
            "food_safety_concerns": [],
            "overall_summary": "This is a fallback estimate. Connect Gemini API key for a full personalized analysis.",
        }
