"""Transcription service using OpenAI Whisper API"""
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from loguru import logger
from openai import OpenAI
from core.config import settings


class WhisperTranscriber:
    """
    Transcribes audio/video files using OpenAI Whisper API.

    Flow:
    1. Extract audio from video (mp4 → mp3) using ffmpeg
    2. If file > 24MB, split into chunks using ffmpeg
    3. Send each chunk to OpenAI Whisper API
    4. Merge results with corrected timestamps
    """

    # Whisper API max file size is 25MB, use 24MB as safe limit
    MAX_FILE_SIZE_MB = 24
    # Chunk duration in seconds (20 min chunks at 64kbps mono 16kHz ≈ 10MB)
    CHUNK_DURATION_SEC = 1200

    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        logger.info("WhisperTranscriber initialized")

    def _ffmpeg_available(self) -> bool:
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

    def extract_audio(self, video_path: str) -> str:
        """Extract audio from video file using ffmpeg."""
        audio_path = video_path.replace(".mp4", ".mp3")

        if not self._ffmpeg_available():
            logger.warning("ffmpeg not found, trying to send mp4 directly to Whisper")
            return video_path

        cmd = [
            "ffmpeg", "-i", video_path,
            "-vn",
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-acodec", "libmp3lame",
            "-ab", "64k",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            audio_path,
        ]

        logger.info(f"Extracting audio: {video_path} → {audio_path}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"ffmpeg error: {result.stderr}")
            return video_path

        file_size = Path(audio_path).stat().st_size / (1024 * 1024)
        logger.info(f"Audio extracted: {audio_path} ({file_size:.1f} MB)")
        return audio_path

    def _get_audio_duration_seconds(self, audio_path: str) -> Optional[float]:
        """Probe audio duration via ffprobe. Returns None if ffprobe is unavailable or fails."""
        if not self._ffmpeg_available():
            return None
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"ffprobe error: {result.stderr}")
            return None
        try:
            return float(result.stdout.strip())
        except (ValueError, AttributeError):
            return None

    def _split_audio(self, audio_path: str) -> list[str]:
        """Split audio file into chunks using ffmpeg."""
        if not self._ffmpeg_available():
            logger.warning("ffmpeg not found, cannot split audio")
            return [audio_path]

        total_duration = self._get_audio_duration_seconds(audio_path)
        if total_duration is None:
            return [audio_path]
        logger.info(f"Audio duration: {total_duration:.0f}s ({total_duration/60:.1f} min)")

        if total_duration <= self.CHUNK_DURATION_SEC:
            return [audio_path]

        # Split into chunks
        chunks = []
        chunk_dir = Path(audio_path).parent
        base_name = Path(audio_path).stem
        chunk_idx = 0
        offset = 0.0

        while offset < total_duration:
            chunk_path = str(chunk_dir / f"{base_name}_chunk{chunk_idx:03d}.mp3")
            cmd = [
                "ffmpeg", "-i", audio_path,
                "-ss", str(offset),
                "-t", str(self.CHUNK_DURATION_SEC),
                "-acodec", "libmp3lame",
                "-ab", "64k",
                "-ar", "16000",
                "-ac", "1",
                "-y",
                chunk_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"ffmpeg split error at chunk {chunk_idx}: {result.stderr}")
                break

            chunk_size = Path(chunk_path).stat().st_size / (1024 * 1024)
            logger.info(f"Chunk {chunk_idx}: offset={offset:.0f}s, size={chunk_size:.1f} MB")
            chunks.append(chunk_path)
            offset += self.CHUNK_DURATION_SEC
            chunk_idx += 1

        logger.info(f"Split into {len(chunks)} chunks")
        return chunks if chunks else [audio_path]

    def _transcribe_single(self, file_path: str, language: str, time_offset: float = 0) -> list[dict]:
        """Transcribe a single audio file, adjusting timestamps by time_offset."""
        with open(file_path, "rb") as f:
            response = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language=language,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        segments = []
        for seg in response.segments or []:
            start = getattr(seg, "start", 0) + time_offset
            end = getattr(seg, "end", start) + time_offset
            minutes = int(start // 60)
            seconds = int(start % 60)
            timestamp = f"{minutes:02d}:{seconds:02d}"
            text = getattr(seg, "text", "").strip()

            if text:
                segments.append({
                    "speaker": "Speaker",
                    "timestamp": timestamp,
                    "start_sec": start,
                    "end_sec": end,
                    "text": text,
                })

        return segments, response.text

    def transcribe(self, file_path: str, language: str = "ru") -> dict:
        """
        Transcribe audio/video file using OpenAI Whisper API.
        Automatically splits large files into chunks.

        Args:
            file_path: Path to audio or video file
            language: Language code (default: "ru" for Russian)

        Returns:
            Dict with `segments`, `full_text` and `audio_seconds`
            (audio_seconds may be None if ffprobe is unavailable; in that
             case callers should fall back to the last segment's end time).
        """
        # Extract audio if it's a video file
        if file_path.endswith(".mp4"):
            file_path = self.extract_audio(file_path)

        # Probe duration BEFORE transcription/cleanup. Used for billing.
        audio_seconds = self._get_audio_duration_seconds(file_path)

        file_size = Path(file_path).stat().st_size / (1024 * 1024)
        logger.info(
            f"Transcribing {file_path} ({file_size:.1f} MB, "
            f"~{audio_seconds:.0f}s)" if audio_seconds is not None
            else f"Transcribing {file_path} ({file_size:.1f} MB)"
        )

        # If file is small enough, transcribe directly
        if file_size <= self.MAX_FILE_SIZE_MB:
            segments, full_text = self._transcribe_single(file_path, language)
            logger.info(f"Whisper transcription complete: {len(segments)} segments, "
                        f"full text length: {len(full_text)}")
            self._cleanup(file_path)
            if audio_seconds is None and segments:
                audio_seconds = segments[-1].get("end_sec")
            return {
                "segments": segments,
                "full_text": full_text,
                "audio_seconds": audio_seconds,
            }

        # Large file — split into chunks
        logger.info(f"File too large ({file_size:.1f} MB > {self.MAX_FILE_SIZE_MB} MB), splitting into chunks")
        chunks = self._split_audio(file_path)

        all_segments = []
        all_text_parts = []

        for i, chunk_path in enumerate(chunks):
            time_offset = i * self.CHUNK_DURATION_SEC
            chunk_size = Path(chunk_path).stat().st_size / (1024 * 1024)
            logger.info(f"Transcribing chunk {i+1}/{len(chunks)} ({chunk_size:.1f} MB), "
                        f"time_offset={time_offset}s")

            segments, text = self._transcribe_single(chunk_path, language, time_offset)
            all_segments.extend(segments)
            all_text_parts.append(text)

            # Clean up chunk file
            if chunk_path != file_path:
                self._cleanup(chunk_path)

        full_text = " ".join(all_text_parts)
        logger.info(f"Whisper transcription complete: {len(all_segments)} segments from "
                    f"{len(chunks)} chunks, full text length: {len(full_text)}")

        # Clean up original audio file
        self._cleanup(file_path)

        if audio_seconds is None and all_segments:
            audio_seconds = all_segments[-1].get("end_sec")

        return {
            "segments": all_segments,
            "full_text": full_text,
            "audio_seconds": audio_seconds,
        }

    def _cleanup(self, file_path: str):
        """Remove temp file if it's an mp3."""
        if file_path.endswith(".mp3"):
            try:
                os.remove(file_path)
            except Exception:
                pass


# Singleton instance
whisper_transcriber = WhisperTranscriber()
