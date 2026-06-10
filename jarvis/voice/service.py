from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


InputMode = Literal["text", "voice"]


@dataclass(frozen=True)
class VoiceTranscript:
    text: str
    confidence: float | None = None
    provider: str | None = None


class SpeechToTextProvider(ABC):
    @abstractmethod
    def transcribe(self, audio: bytes) -> VoiceTranscript:
        """Convert speech audio into text."""


class TextToSpeechProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Convert text into speech audio."""


class VoiceService:
    def __init__(self, stt: SpeechToTextProvider | None = None, tts: TextToSpeechProvider | None = None) -> None:
        self.stt = stt
        self.tts = tts

    @property
    def speech_to_text_enabled(self) -> bool:
        return self.stt is not None

    @property
    def text_to_speech_enabled(self) -> bool:
        return self.tts is not None
