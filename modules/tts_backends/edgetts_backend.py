"""EdgeTTS TTS backend — cloud-based, high quality, free."""

import asyncio
import concurrent.futures
import logging
import os
import tempfile
import threading
import time

logger = logging.getLogger(__name__)

from ..tts_registry import TTSBackend, TTSResult, TTSRegistry
import contextlib

# Shared lock for MCI playback (Windows only)
_MCI_LOCK = threading.Lock()


@TTSRegistry.register("edgetts")
class EdgeTTSBackend(TTSBackend):
    """Microsoft Edge TTS via edge-tts library. Free, natural-sounding voices.
    Downloads audio as MP3, plays via MCI (Windows) or sounddevice.
    """

    interrupt_event: threading.Event | None = None

    @property
    def name(self) -> str:
        return "edgetts"

    def health(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            return False

    def voices(self) -> list[str]:
        """Return list of available EdgeTTS voices."""
        try:
            async def _list_voices():
                import edge_tts
                voices = await edge_tts.list_voices()
                return sorted(set(v["ShortName"] for v in voices))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_list_voices())
        except Exception:
            return []

    def synthesize(self, text: str, **kwargs) -> TTSResult:
        import config
        voice = kwargs.get("voice", getattr(config, "EDGETTS_VOICE", "en-US-JennyNeural"))
        rate = kwargs.get("rate", getattr(config, "TTS_RATE", "+0%"))
        pitch = kwargs.get("pitch", getattr(config, "TTS_PITCH", "+0Hz"))
        volume = kwargs.get("volume", getattr(config, "TTS_VOLUME", "+0%"))
        interrupt = kwargs.get("interrupt_event", self.interrupt_event)

        try:
            # Generate MP3 to temp file
            async def _generate():
                import edge_tts
                communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp_path = tmp.name
                await communicate.save(tmp_path)
                return tmp_path

            # edge-tts requires asyncio — handle event loop
            try:
                loop = asyncio.get_running_loop()
                # Already running — use thread pool fallback
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(self._run_async_safe, _generate)
                    tmp_path = future.result()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                tmp_path = loop.run_until_complete(_generate())

            # Play via MCI
            self._play_mci(tmp_path, interrupt)

            if interrupt is None or not interrupt.is_set():
                return TTSResult(
                    success=True, backend="edgetts", audio_path=tmp_path
                )
            else:
                return TTSResult(
                    success=False, backend="edgetts", error="interrupted"
                )
        except Exception as e:
            logger.error("EdgeTTS failed: %s", e)
            return TTSResult(success=False, backend="edgetts", error=str(e))

    def _run_async_safe(self, coro_factory):
        """Run async generator in a new event loop on this thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro_factory())
        finally:
            loop.close()

    def _play_mci(self, file_path: str, interrupt: threading.Event | None):
        """Play audio via Windows MCI with silence compression (MP3 → WAV conversion)."""
        # EdgeTTS outputs MP3 but silence compression needs WAV PCM16.
        # Convert MP3 → WAV via miniaudio, then compress, then play compressed WAV.
        wav_path = None
        cleanup_paths = [file_path]
        try:
            import miniaudio
            mp3_audio = miniaudio.read_file(file_path)
            base = os.path.splitext(file_path)[0]
            wav_path = base + "_tmp.wav"
            miniaudio.wav_write_s16(wav_path, mp3_audio.samples,
                                     mp3_audio.nchannels, mp3_audio.sample_rate)
            cleanup_paths.append(wav_path)

            # Silence compression — now works since it's WAV PCM16
            try:
                from modules.tts import _compress_audio_file
                _compress_audio_file(wav_path)
            except Exception:
                pass  # Play uncompressed WAV if compression fails
        except Exception:
            # miniaudio failed — fall back to original MP3
            wav_path = file_path

        import ctypes
        from ctypes import wintypes

        with _MCI_LOCK:
            try:
                mci_send = ctypes.windll.winmm.mciSendStringW
                mci_send.restype = wintypes.UINT

                alias = "edge_tts"

                # Determine MCI device type from file extension
                is_mp3 = str(wav_path).lower().endswith(".mp3") if wav_path else False
                device_type = "mpegvideo" if is_mp3 else "waveaudio"

                # Open
                cmd_open = f'open "{wav_path}" type {device_type} alias {alias}'
                if mci_send(cmd_open, None, 0, None) != 0:
                    logger.error("MCI open failed for %s", wav_path)
                    return

                # Play
                cmd_play = f"play {alias}"
                mci_send(cmd_play, None, 0, None)

                # Poll for completion / interrupt
                buf = ctypes.create_unicode_buffer(128)
                while True:
                    if interrupt is not None and interrupt.is_set():
                        mci_send(f"close {alias}", None, 0, None)
                        return
                    mci_send(f"status {alias} mode", buf, 128, None)
                    if buf.value != "playing":
                        break
                    time.sleep(0.05)

                # Close
                mci_send(f"close {alias}", None, 0, None)
            except Exception as e:
                logger.error("MCI playback error: %s", e)
            finally:
                # Clean up temp files
                for p in cleanup_paths:
                    with contextlib.suppress(Exception):
                        os.unlink(p)
