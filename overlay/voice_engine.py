"""Voice Engine — TTS wrapper that generates speech and plays it via winsound.

Uses edge-tts (Microsoft Edge TTS) for high-quality voice output.
Caches generated audio to avoid regenerating identical phrases.
Falls back silently to no-op if edge-tts is unavailable.
"""
import os
import time
import hashlib
import threading
from typing import Optional

import paths

# Voice configuration — use the preferred voice
DEFAULT_VOICE = "en-GB-LewisNeural"  # Male British voice
FALLBACK_VOICE = "en-GB-SoniaNeural"

# Cooldown between messages (global)
MIN_INTERVAL_SECONDS = 20


class VoiceEngine:
    """Generates TTS audio from text and plays it through system speakers."""

    def __init__(self, voice: str = DEFAULT_VOICE, volume: float = 1.0):
        self.voice = voice
        self.volume = max(0.0, min(1.0, volume))
        self.enabled = True
        self._cache_dir = paths.data_path("overlay", "tts_cache")
        os.makedirs(self._cache_dir, exist_ok=True)
        self._last_played: float = 0.0
        self._lock = threading.Lock()
        # phrase_hash -> timestamp for dedup (3 min window)
        self._recent_phrases: dict = {}
        self._tts_retry_after: float = 0.0  # timestamp after which TTS can be retried
        self._tts_retry_interval: float = 300.0  # retry after 5 minutes

    def speak(self, text: str) -> bool:
        """Generate TTS and play it. Returns True if played, False if skipped."""
        if not self.enabled or not text:
            return False

        # Cooldown check — never more than one message per 20s
        now = time.time()
        if now - self._last_played < MIN_INTERVAL_SECONDS:
            return False

        # Dedup: don't repeat the same content within 3 minutes
        phrase_hash = hashlib.md5(text.encode()).hexdigest()[:12]
        if phrase_hash in self._recent_phrases:
            if now - self._recent_phrases[phrase_hash] < 180:
                return False

        def _play():
            try:
                wav_path = self._generate_wav(text)
                if wav_path and os.path.exists(wav_path):
                    # winsound is Windows-only — import locally with fallback
                    try:
                        import winsound
                    except ImportError:
                        # On Linux/macOS: skip audio playback gracefully
                        with self._lock:
                            self._last_played = time.time()
                            self._recent_phrases[phrase_hash] = time.time()
                        print("[VoiceEngine] winsound not available — skipping playback (non-Windows OS)")
                        return

                    with self._lock:
                        winsound.PlaySound(
                            wav_path,
                            winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                        )
                        self._last_played = time.time()
                        self._recent_phrases[phrase_hash] = time.time()
                    # Cleanup old cache files (keep last 50)
                    self._cleanup_cache()
            except Exception as e:
                print(f"[VoiceEngine] Playback error: {e}")

        thread = threading.Thread(target=_play, daemon=True)
        thread.start()
        return True

    def _generate_wav(self, text: str) -> Optional[str]:
        """Generate WAV from text using edge-tts. Returns path to WAV file."""
        # Respect retry cooldown after failures
        if time.time() < self._tts_retry_after:
            return None

        cache_name = f"{hashlib.md5(text.encode()).hexdigest()[:16]}.wav"
        cache_path = os.path.join(self._cache_dir, cache_name)

        # Return cached if exists
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1000:
            return cache_path

        try:
            import edge_tts
            import asyncio
            asyncio.run(edge_tts.Communicate(text, self.voice).save(cache_path))
            if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1000:
                return cache_path
        except ImportError:
            print(f"[VoiceEngine] edge-tts not installed — will retry in {self._tts_retry_interval:.0f}s")
            self._tts_retry_after = time.time() + self._tts_retry_interval
        except Exception:
            print(f"[VoiceEngine] TTS generation failed — will retry in {self._tts_retry_interval:.0f}s")
            self._tts_retry_after = time.time() + self._tts_retry_interval

        return None

    def _cleanup_cache(self, max_files: int = 50):
        """Remove oldest cache files beyond max_files."""
        try:
            files = sorted(
                [os.path.join(self._cache_dir, f) for f in os.listdir(self._cache_dir) if f.endswith('.wav')],
                key=os.path.getmtime,
            )
            for f in files[:-max_files]:
                os.remove(f)
        except Exception:
            pass

    def play_test(self) -> bool:
        """Play a test phrase to verify voice engine works."""
        return self.speak("Audio check. This is your race engineer.")

    def set_volume(self, vol: float):
        self.volume = max(0.0, min(1.0, vol))
