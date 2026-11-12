import threading
import re

from google import genai
from google.genai import types

from .base import VisionProvider

from .prompt_templates import DETAIL_GUIDANCE, MODE_GUIDANCE

SYSTEM_INSTRUCTION = """You are OtakuAura, an image-to-prompt assistant. Analyze the supplied image and create a usable image-generation prompt for external tools such as Midjourney, Stable Diffusion, and Flux.

Rules:
- Describe only what is visibly supported. Do not invent objects, text, locations, identities, backstories, or hidden details.
- Never identify a real person or guess sensitive personal traits. If a person appears, describe only non-sensitive visible visual elements relevant to composition.
- Include the main subject and its visible attributes, pose/action, clothing only if clearly visible, environment, foreground/background relationships, composition, viewpoint, lighting, colour palette, textures, atmosphere, and visual style when relevant.
- Prioritize image-specific details over generic adjectives. Avoid repeated tags, filler, and contradictory descriptions.
- Preserve the image's actual visual style; do not automatically add anime, photorealism, cinematic, or other styles unless supported.
- Do not guess exact camera/lens settings, brands, identities, locations, or text that cannot be read. If a detail is ambiguous, omit it rather than inventing it.
- Do not mention that you are an AI. Do not add unsupported negative prompts or model parameters.
- Keep descriptions respectful and non-sexual.
"""


class GeminiVisionProvider(VisionProvider):
    def __init__(self, api_key: str | tuple[str, ...] | list[str], model: str = "gemini-3.8-flash") -> None:
        keys = [api_key] if isinstance(api_key, str) else list(api_key)
        self.api_keys = tuple(dict.fromkeys(key.strip() for key in keys if key and key.strip()))
        if not self.api_keys:
            raise ValueError("At least one Gemini API key must be configured.")
        self.model = model
        self._active_key_index = 0
        self._key_lock = threading.Lock()
        self.clients = tuple(genai.Client(api_key=key) for key in self.api_keys)

    def update_keys(self, api_keys: tuple[str, ...] | list[str]) -> None:
        keys = tuple(dict.fromkeys(key.strip() for key in api_keys if key and key.strip()))
        if not keys:
            raise ValueError("At least one Gemini API key must remain configured.")
        clients = tuple(genai.Client(api_key=key) for key in keys)
        with self._key_lock:
            self.api_keys = keys
            self.clients = clients
            self._active_key_index = 0

    @staticmethod
    def _is_quota_or_rate_limit_error(error: Exception) -> bool:
        # Rotate only for exhausted quota / rate limits. Invalid keys and other
        # request errors should surface immediately rather than being hidden.
        message = str(error).lower()
        markers = (
            "resource_exhausted", "quota exceeded", "rate limit", "too many requests",
            "429", "requests per minute", "tokens per minute", "daily limit",
        )
        return any(marker in message for marker in markers)

    def _generate_text(self, contents: list, system_instruction: str, max_output_tokens: int = 1400) -> str:
        with self._key_lock:
            start_index = self._active_key_index
        last_quota_error = None
        for offset in range(len(self.clients)):
            index = (start_index + offset) % len(self.clients)
            try:
                response = self.clients[index].models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        max_output_tokens=max_output_tokens,
                        # Lower randomness improves repeatability for factual visual tags.
                        temperature=0.2,
                        top_p=0.85,
                    ),
                )
                result = (response.text or "").strip()
                if not result:
                    raise RuntimeError("The AI provider returned an empty response.")
                with self._key_lock:
                    self._active_key_index = index
                return result
            except Exception as error:
                if not self._is_quota_or_rate_limit_error(error):
                    raise
                last_quota_error = error
                # The next request starts from the next key after a successful fallback.
                with self._key_lock:
                    self._active_key_index = (index + 1) % len(self.clients)
        raise RuntimeError(
            f"All {len(self.clients)} configured Gemini API key(s) are currently rate-limited or out of quota."
        ) from last_quota_error

    def create_prompt(
        self,
        image_bytes: bytes,
        mime_type: str,
        detail_level: str = "standard",
        output_mode: str = "natural",
        language: str = "English",
    ) -> str:
        detail = DETAIL_GUIDANCE.get(detail_level, DETAIL_GUIDANCE["standard"])
        mode = MODE_GUIDANCE.get(output_mode, MODE_GUIDANCE["natural"])
        # Danbooru/NovelAI vocabulary is conventionally English. Keep tags in
        # English even if a user selected Hindi/Hinglish for prose modes.
        output_language = "English (standard anime tagging vocabulary)" if output_mode == "tags" else language
        instruction = (
            f"Detail level: {detail}\nOutput format: {mode}\n"
            f"Write the result in {output_language}. Keep tool-specific syntax out unless visibly appropriate.\n"
            "Return only the requested prompt."
        )
        result = self._generate_text(
            [instruction, types.Part.from_bytes(data=image_bytes, mime_type=mime_type)],
            SYSTEM_INSTRUCTION,
            # Tag output should be compact; a smaller ceiling reduces unnecessary
            # generation while leaving room for detailed anime scenes.
            max_output_tokens=520 if output_mode == "tags" else 1400,
        )
        if output_mode == "tags":
            result = self._normalize_tags(result)
        return result

    @staticmethod
    def _normalize_tags(text: str) -> str:
        """Remove formatting noise and duplicate tags without inventing content."""
        cleaned = text.strip().replace("```text", "").replace("```", "")
        cleaned = re.sub(r"(?im)^\s*(?:prompt|tags?)\s*:\s*", "", cleaned)
        cleaned = re.sub(r"(?m)^\s*(?:[-*•]+|\d+[.)])\s*", "", cleaned)
        cleaned = re.sub(r"\s*[,;]\s*", ", ", cleaned)
        cleaned = re.sub(r"\s*\n\s*", ", ", cleaned)
        cleaned = re.sub(r"(?:,\s*){2,}", ", ", cleaned).strip(" ,")
        unique = []
        seen = set()
        for item in cleaned.split(","):
            tag = item.strip().strip("`*")
            key = tag.casefold()
            if tag and key not in seen:
                seen.add(key)
                unique.append(tag)
        return ", ".join(unique)

    def translate_prompt(self, prompt: str, target_language: str) -> str:
        instruction = (
            f"Translate the following image-generation prompt into {target_language}. "
            "Preserve its meaning, visual details, structure, and prompt usability. "
            "Do not add or remove visual claims. Return only the translated prompt.\n\n"
            f"PROMPT:\n{prompt}"
        )
        return self._generate_text(
            [instruction],
            "You are a careful translator of image-generation prompts. Translate faithfully; do not embellish.",
            max_output_tokens=1400,
        )
