from abc import ABC, abstractmethod


class VisionProvider(ABC):
    @abstractmethod
    def create_prompt(self, image_bytes: bytes, mime_type: str, detail_level: str = "standard") -> str:
        """Return a usable image-generation prompt from image bytes."""
