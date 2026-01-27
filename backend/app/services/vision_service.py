"""
Vision Service - Handles image analysis using Gemini Vision API.

LLM Usage Rules:
- LLM calls are owned by this service
- Agents request reasoning via service interface
- Falls back to simulated responses if no API key

Failure Handling:
- Vision Failure: Fall back to previous valid state
- User is informed of degraded confidence
"""

import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class VisionService:
    """
    Vision service for analyzing fridge images.

    Uses Gemini Vision API when available, falls back to simulation.
    """

    def __init__(self):
        self._model = None
        self._initialized = False
        self._last_valid_analysis: Optional[Dict[str, Any]] = None

    async def initialize(self):
        """Initialize the Gemini model if API key is available."""
        if self._initialized:
            return

        if settings.has_gemini_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.gemini_api_key)
                # Use gemini-2.5-flash-lite model
                self._model = genai.GenerativeModel("gemini-2.5-flash-lite")
                self._initialized = True
                logger.info("Gemini Vision API initialized with gemini-2.5-flash-lite")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}")
                self._model = None
        else:
            logger.info("No Gemini API key - using simulated responses")

    async def analyze_fridge_image(
        self,
        image_path: str,
        household_id: str,
    ) -> Dict[str, Any]:
        """
        Analyze a fridge image and extract inventory.

        Args:
            image_path: Path to the image file
            household_id: Household ID for context

        Returns:
            Analysis result with detected items
        """
        await self.initialize()

        # Validate image first
        is_valid, validation_result = await self.validate_fridge_image(image_path)

        if not is_valid:
            return {
                "success": False,
                "error": "Image validation failed",
                "validation": validation_result,
                "items": [],
                "confidence": 0.0,
            }

        try:
            if self._model:
                result = await self._analyze_with_gemini(image_path)
            else:
                result = await self._simulate_analysis(image_path)

            # Cache successful analysis
            self._last_valid_analysis = result
            return result

        except Exception as e:
            error_str = str(e)
            logger.error(f"Vision analysis failed: {error_str}")

            # If quota exceeded or rate limited, fall back to simulation
            if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                logger.info("API quota exceeded - falling back to simulated analysis")
                result = await self._simulate_analysis(image_path)
                result["degraded"] = True
                result["degradation_reason"] = "API quota exceeded - using simulated data"
                return result

            # Fall back to last valid state
            if self._last_valid_analysis:
                logger.info("Falling back to last valid analysis")
                return {
                    **self._last_valid_analysis,
                    "degraded": True,
                    "degradation_reason": error_str,
                }

            # Ultimate fallback - use simulation
            logger.info("No cached analysis - falling back to simulation")
            result = await self._simulate_analysis(image_path)
            result["degraded"] = True
            result["degradation_reason"] = error_str
            return result

    async def validate_fridge_image(
        self,
        image_path: str
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Validate that an image is actually a fridge.

        Binary classifier: "Is this a fridge?"

        Returns:
            (is_valid, validation_details)
        """
        await self.initialize()

        try:
            if self._model:
                return await self._validate_with_gemini(image_path)
            else:
                return await self._simulate_validation(image_path)
        except Exception as e:
            logger.error(f"Image validation failed: {e}")
            return False, {"error": str(e)}

    async def _analyze_with_gemini(self, image_path: str) -> Dict[str, Any]:
        """Analyze image using Gemini Vision API."""
        import google.generativeai as genai

        # Read and encode image
        image_data = Path(image_path).read_bytes()
        image_part = {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(image_data).decode("utf-8")
        }

        prompt = """Analyze this refrigerator image and identify all visible food items.

For each item, provide:
1. name: The name of the food item
2. category: One of [dairy, produce, meat, seafood, beverages, condiments, leftovers, frozen, other]
3. quantity: Estimated count (default 1)
4. location: Where in the fridge (top shelf, middle shelf, bottom shelf, door, drawer)
5. confidence: Your confidence in this detection (0.0 to 1.0)

Also estimate expiration status if visible or inferable.

Return ONLY a JSON object in this exact format:
{
    "items": [
        {
            "name": "Item Name",
            "category": "category",
            "quantity": 1,
            "location": "location",
            "confidence": 0.9,
            "expiration_estimate": "YYYY-MM-DD or null"
        }
    ],
    "overall_confidence": 0.85,
    "fridge_fullness": "empty|sparse|moderate|full",
    "notes": "Any relevant observations"
}"""

        response = await self._model.generate_content_async([prompt, image_part])

        # Parse JSON from response
        response_text = response.text
        # Extract JSON from markdown code blocks if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        try:
            analysis = json.loads(response_text.strip())
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse Gemini response as JSON: {response_text}")
            analysis = {
                "items": [],
                "overall_confidence": 0.5,
                "notes": response_text
            }

        return {
            "success": True,
            "items": analysis.get("items", []),
            "confidence": analysis.get("overall_confidence", 0.8),
            "fullness": analysis.get("fridge_fullness", "unknown"),
            "notes": analysis.get("notes", ""),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _validate_with_gemini(self, image_path: str) -> tuple[bool, Dict[str, Any]]:
        """Validate image using Gemini."""
        import google.generativeai as genai

        try:
            image_data = Path(image_path).read_bytes()
            image_part = {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(image_data).decode("utf-8")
            }

            prompt = """Is this an image of the inside of a refrigerator or fridge? Look for shelves, food items, containers, or typical fridge contents.
Answer with ONLY a JSON object:
{
    "is_fridge": true or false,
    "confidence": 0.0 to 1.0,
    "reason": "brief explanation"
}"""

            response = await self._model.generate_content_async([prompt, image_part])
            response_text = response.text
            logger.info(f"Gemini validation response: {response_text[:200]}")

            # Extract JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            try:
                result = json.loads(response_text.strip())
                is_valid = result.get("is_fridge", False) and result.get("confidence", 0) > 0.5
                return is_valid, result
            except json.JSONDecodeError:
                # If JSON parsing fails, try to detect keywords in response
                lower_text = response_text.lower()
                if "true" in lower_text or "yes" in lower_text or "fridge" in lower_text:
                    logger.info("JSON parse failed but detected positive keywords - accepting image")
                    return True, {"is_fridge": True, "confidence": 0.7, "reason": "Keyword detection fallback"}
                logger.warning(f"Failed to parse validation response: {response_text}")
                # Default to accepting the image if we can't parse the response
                return True, {"is_fridge": True, "confidence": 0.6, "reason": "Parse fallback - accepting image"}
        except Exception as e:
            logger.error(f"Gemini validation error: {e}")
            # On any error, default to accepting the image
            return True, {"is_fridge": True, "confidence": 0.5, "reason": f"Error fallback: {str(e)}"}

    async def _simulate_analysis(self, image_path: str) -> Dict[str, Any]:
        """
        Simulate fridge analysis when no API key is available.

        Returns realistic mock data for development.
        """
        logger.info("Using simulated vision analysis")

        # Simulated items for testing
        simulated_items = [
            {
                "name": "Milk",
                "category": "dairy",
                "quantity": 1,
                "location": "door",
                "confidence": 0.95,
                "expiration_estimate": "2025-02-01"
            },
            {
                "name": "Eggs",
                "category": "dairy",
                "quantity": 12,
                "location": "top shelf",
                "confidence": 0.92,
                "expiration_estimate": "2025-02-10"
            },
            {
                "name": "Cheese",
                "category": "dairy",
                "quantity": 1,
                "location": "middle shelf",
                "confidence": 0.88,
                "expiration_estimate": "2025-01-28"
            },
            {
                "name": "Lettuce",
                "category": "produce",
                "quantity": 1,
                "location": "drawer",
                "confidence": 0.85,
                "expiration_estimate": "2025-01-29"
            },
            {
                "name": "Chicken Breast",
                "category": "meat",
                "quantity": 2,
                "location": "bottom shelf",
                "confidence": 0.90,
                "expiration_estimate": "2025-01-27"
            },
            {
                "name": "Orange Juice",
                "category": "beverages",
                "quantity": 1,
                "location": "door",
                "confidence": 0.93,
                "expiration_estimate": "2025-02-15"
            },
            {
                "name": "Ketchup",
                "category": "condiments",
                "quantity": 1,
                "location": "door",
                "confidence": 0.97,
                "expiration_estimate": "2025-06-01"
            },
            {
                "name": "Yogurt",
                "category": "dairy",
                "quantity": 4,
                "location": "top shelf",
                "confidence": 0.91,
                "expiration_estimate": "2025-01-30"
            },
        ]

        return {
            "success": True,
            "items": simulated_items,
            "confidence": 0.88,
            "fullness": "moderate",
            "notes": "Simulated analysis - connect Gemini API for real detection",
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "simulated": True,
        }

    async def _simulate_validation(self, image_path: str) -> tuple[bool, Dict[str, Any]]:
        """Simulate image validation."""
        # In simulation mode, accept all images
        return True, {
            "is_fridge": True,
            "confidence": 0.95,
            "reason": "Simulated validation - all images accepted in dev mode"
        }


# Global vision service instance
vision_service = VisionService()
