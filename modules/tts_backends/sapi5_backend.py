"""Windows SAPI5 TTS backend — fast, offline, COM-based."""

import logging
import threading
import time

logger = logging.getLogger(__name__)

_SAPI_LOCK = threading.Lock()

from ..tts_registry import TTSBackend, TTSResult, TTSRegistry
import contextlib


@TTSRegistry.register("sapi5")
class SAPI5Backend(TTSBackend):
    """Windows SAPI5 via win32com. Fastest local TTS option on Windows.

    COM apartment management: uses proper CoInitialize/CoUninitialize
    pattern to avoid RPC_E_CHANGED_MODE when called from threads that
    already have COM initialized.
    """

    interrupt_event: threading.Event | None = None

    @property
    def name(self) -> str:
        return "sapi5"

    def health(self) -> bool:
        try:
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401
            return True
        except ImportError:
            return False

    def voices(self) -> list[str]:
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            voices = speaker.GetVoices()
            result = []
            for i in range(voices.Count):
                result.append(voices.Item(i).GetDescription())
            return result
        except Exception:
            return []

    def synthesize(self, text: str, **kwargs) -> TTSResult:
        import pythoncom
        import win32com.client

        # Use external interrupt event if provided
        interrupt = kwargs.get("interrupt_event", self.interrupt_event)
        import config as cfg
        rate = kwargs.get("rate", getattr(cfg, "TTS_SAPI_RATE", 0))
        target_voice = kwargs.get("voice", getattr(cfg, "TTS_SAPI_VOICE", ""))

        with _SAPI_LOCK:
            co_init = pythoncom.CoInitialize()
            needs_cleanup = (co_init == 0)

            try:
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                speaker.Rate = int(rate)

                if target_voice:
                    voices = speaker.GetVoices()
                    for i in range(voices.Count):
                        desc = voices.Item(i).GetDescription()
                        if target_voice.lower() in desc.lower():
                            speaker.Voice = voices.Item(i)
                            break

                # Async speak + poll for interrupt
                speaker.Speak(text, 1)
                while speaker.Status.RunningState == 2:
                    if interrupt is not None and interrupt.is_set():
                        speaker.Speak("", 2)  # Purge
                        break
                    time.sleep(0.05)

                return TTSResult(success=True, backend="sapi5", duration_ms=0)
            except Exception as e:
                logger.error("SAPI5 synthesis failed: %s", e)
                return TTSResult(success=False, backend="sapi5", error=str(e))
            finally:
                if needs_cleanup:
                    with contextlib.suppress(Exception):
                        pythoncom.CoUninitialize()

    def stop(self):
        """Force-stop SAPI5 by acquiring lock and sending purge."""
        # SAPI5 handled via interrupt event polling in the loop above
        pass
