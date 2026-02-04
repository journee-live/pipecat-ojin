"""Hume EVI Bot with TKinter UI.

A simple speech-to-speech bot using Hume's Empathic Voice Interface (EVI)
with local audio input/output and a TKinter-based UI for displaying
transcripts and status.

Requirements:
    pip install pipecat-ai[hume-evi,local]

Environment variables:
    HUME_API_KEY: Your Hume API key
    HUME_CONFIG_ID: Your Hume EVI configuration ID
"""

import asyncio
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, ttk
from typing import Optional

import numpy as np
from dotenv import load_dotenv
from loguru import logger

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InputAudioRawFrame,
    LLMTextFrame,
    StartFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.hume.hume import HumeStartFrame, HumeSTSService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


class LatencyMeasurementProcessor(FrameProcessor):
    """Processor that measures latency and collects responses."""

    def __init__(self):
        super().__init__()
        self.last_silent_chunk_time = None
        self.first_audio_received_time = None
        self.first_transcript_received_time = None
        self.last_volume = 0
        self.user_transcript = None
        self.assistant_transcript = None
        self.audio_chunks_received = 0
        self.total_audio_duration = 0.0

    def print_summary(self):
        """Print latency summary."""
        logger.info("\n" + "=" * 60)
        logger.info("LATENCY TEST SUMMARY (STANDALONE - hume 0.12.1)")
        logger.info("=" * 60)

        if self.last_silent_chunk_time and self.first_audio_received_time:
            latency = (self.first_audio_received_time - self.last_silent_chunk_time) * 1000
            logger.success(f"⏱️  Time to first audio: {latency:.0f}ms")

        if self.last_silent_chunk_time and self.first_transcript_received_time:
            latency = (self.first_transcript_received_time - self.last_silent_chunk_time) * 1000
            logger.info(f"⏱️  Time to first transcript: {latency:.0f}ms")

        logger.info(f"📊 Audio chunks received: {self.audio_chunks_received}")
        logger.info(f"🎵 Total audio duration: {self.total_audio_duration:.2f}s")

        if self.user_transcript:
            logger.info(f"👤 User said: '{self.user_transcript}'")
        if self.assistant_transcript:
            logger.info(f"🤖 Assistant said: '{self.assistant_transcript}'")

        logger.info("=" * 60)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            if not self.first_transcript_received_time and self.last_silent_chunk_time:
                self.first_transcript_received_time = time.time()
                latency = (self.first_transcript_received_time - self.last_silent_chunk_time) * 1000
                logger.info(f"⏱️  First transcript latency: {latency:.0f}ms")
            self.user_transcript = frame.text
            logger.info(f"👤 User: {frame.text}")

        elif isinstance(frame, InputAudioRawFrame):
            import struct

            samples = struct.unpack(f"{len(frame.audio) // 2}h", frame.audio)
            avg_volume = sum(abs(s) for s in samples) / len(samples) if samples else 0
            if avg_volume > self.last_volume:
                self.last_volume = avg_volume
                self.first_audio_received_time = None
                if not self.last_silent_chunk_time:
                    self.last_silent_chunk_time = time.time()
                    logger.info(
                        f"📍 End of speech detected (transition to silence) at {self.last_silent_chunk_time}"
                    )

        elif isinstance(frame, LLMTextFrame):
            self.assistant_transcript = frame.text
            logger.info(f"🤖 Assistant: {frame.text}")

        elif isinstance(frame, TTSAudioRawFrame):
            self.audio_chunks_received += 1
            if not self.first_audio_received_time and self.last_silent_chunk_time:
                self.first_audio_received_time = time.time()
                latency = (self.first_audio_received_time - self.last_silent_chunk_time) * 1000
                logger.success(f"🎵 First audio latency: {latency:.0f}ms")
                await self.push_frame(EndFrame())
                self.print_summary()

            # Calculate audio duration
            samples = len(frame.audio) / 2  # 16-bit audio
            duration = samples / frame.sample_rate
            self.total_audio_duration += duration

        await self.push_frame(frame, direction)


class TKinterUIProcessor(FrameProcessor):
    """Frame processor that updates TKinter UI with transcripts and status."""

    def __init__(self, app: "HumeBotApp"):
        super().__init__()
        self._app = app

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            self._app.add_transcript("User", frame.text)

        elif isinstance(frame, LLMTextFrame):
            self._app.add_transcript("Assistant", frame.text)

        elif isinstance(frame, TTSStartedFrame):
            self._app.set_status("Speaking...")

        elif isinstance(frame, TTSStoppedFrame):
            self._app.set_status("Listening...")

        await self.push_frame(frame, direction)


class HumeBotApp:
    """TKinter application for Hume EVI bot."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Hume EVI Bot")
        self.root.geometry("600x500")
        self.root.configure(bg="#1e1e1e")

        self._task: Optional[PipelineTask] = None
        self._runner: Optional[PipelineRunner] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False

        self._setup_ui()

    def _setup_ui(self):
        """Setup the TKinter UI components."""
        style = ttk.Style()
        style.theme_use("clam")

        # Status frame
        status_frame = tk.Frame(self.root, bg="#1e1e1e")
        status_frame.pack(fill=tk.X, padx=10, pady=10)

        self.status_label = tk.Label(
            status_frame,
            text="Status: Not connected",
            font=("Helvetica", 12),
            fg="#00ff00",
            bg="#1e1e1e",
        )
        self.status_label.pack(side=tk.LEFT)

        # Transcript area
        transcript_frame = tk.Frame(self.root, bg="#1e1e1e")
        transcript_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Label(
            transcript_frame,
            text="Conversation:",
            font=("Helvetica", 11, "bold"),
            fg="#ffffff",
            bg="#1e1e1e",
        ).pack(anchor=tk.W)

        self.transcript_text = scrolledtext.ScrolledText(
            transcript_frame,
            wrap=tk.WORD,
            font=("Helvetica", 10),
            bg="#2d2d2d",
            fg="#ffffff",
            insertbackground="#ffffff",
            height=20,
        )
        self.transcript_text.pack(fill=tk.BOTH, expand=True, pady=5)
        self.transcript_text.config(state=tk.DISABLED)

        # Configure tags for different speakers
        self.transcript_text.tag_config("user", foreground="#4fc3f7")
        self.transcript_text.tag_config("assistant", foreground="#81c784")
        self.transcript_text.tag_config("system", foreground="#ffb74d")

        # Control buttons
        button_frame = tk.Frame(self.root, bg="#1e1e1e")
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        self.start_button = tk.Button(
            button_frame,
            text="Start",
            command=self._on_start,
            font=("Helvetica", 11),
            bg="#4caf50",
            fg="white",
            width=10,
        )
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = tk.Button(
            button_frame,
            text="Stop",
            command=self._on_stop,
            font=("Helvetica", 11),
            bg="#f44336",
            fg="white",
            width=10,
            state=tk.DISABLED,
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)

        self.clear_button = tk.Button(
            button_frame,
            text="Clear",
            command=self._on_clear,
            font=("Helvetica", 11),
            bg="#2196f3",
            fg="white",
            width=10,
        )
        self.clear_button.pack(side=tk.LEFT, padx=5)

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def set_status(self, status: str):
        """Update status label (thread-safe)."""
        self.root.after(0, lambda: self.status_label.config(text=f"Status: {status}"))

    def add_transcript(self, role: str, text: str):
        """Add transcript to the text area (thread-safe)."""

        def _add():
            self.transcript_text.config(state=tk.NORMAL)
            tag = "user" if role == "User" else "assistant"
            self.transcript_text.insert(tk.END, f"{role}: ", tag)
            self.transcript_text.insert(tk.END, f"{text}\n\n")
            self.transcript_text.see(tk.END)
            self.transcript_text.config(state=tk.DISABLED)

        self.root.after(0, _add)

    def add_system_message(self, text: str):
        """Add system message to the text area (thread-safe)."""

        def _add():
            self.transcript_text.config(state=tk.NORMAL)
            self.transcript_text.insert(tk.END, f"[System] {text}\n", "system")
            self.transcript_text.see(tk.END)
            self.transcript_text.config(state=tk.DISABLED)

        self.root.after(0, _add)

    def _on_start(self):
        """Handle start button click."""
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self._running = True

        # Start pipeline in a separate thread
        thread = threading.Thread(target=self._run_pipeline, daemon=True)
        thread.start()

    def _on_stop(self):
        """Handle stop button click."""
        self._running = False
        if self._task and self._loop:
            asyncio.run_coroutine_threadsafe(self._task.queue_frame(EndFrame()), self._loop)

        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.set_status("Stopped")

    def _on_clear(self):
        """Handle clear button click."""
        self.transcript_text.config(state=tk.NORMAL)
        self.transcript_text.delete(1.0, tk.END)
        self.transcript_text.config(state=tk.DISABLED)

    def _on_close(self):
        """Handle window close."""
        self._on_stop()
        self.root.quit()
        self.root.destroy()

    def _run_pipeline(self):
        """Run the pipecat pipeline in a separate thread."""
        asyncio.run(self._async_run_pipeline())

    async def _async_run_pipeline(self):
        """Async pipeline runner."""
        self._loop = asyncio.get_event_loop()

        try:
            self.set_status("Connecting...")
            self.add_system_message("Connecting to Hume EVI...")

            # Setup transport
            transport = LocalAudioTransport(
                LocalAudioTransportParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                    audio_in_sample_rate=16000,
                    audio_out_sample_rate=24000,
                )
            )

            # Setup Hume EVI service
            hume_service = HumeSTSService(
                api_key=os.getenv("HUME_API_KEY"),
                config_id=os.getenv("HUME_CONFIG_ID"),
                start_frame_cls=HumeStartFrame,
                audio_passthrough=True,
            )

            # UI processor
            ui_processor = TKinterUIProcessor(self)
            latency_processor = LatencyMeasurementProcessor()
            # Build pipeline: input -> hume -> ui -> output
            pipeline = Pipeline(
                [
                    transport.input(),
                    hume_service,
                    latency_processor,
                    ui_processor,
                    transport.output(),
                ]
            )

            self._task = PipelineTask(pipeline)
            self._runner = PipelineRunner(handle_sigint=False)

            # Queue start frames
            async def start_conversation():
                await asyncio.sleep(0.5)
                await self._task.queue_frame(HumeStartFrame())
                self.set_status("Listening...")
                self.add_system_message("Connected! Start speaking...")

            await asyncio.gather(
                self._runner.run(self._task),
                start_conversation(),
            )

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            self.set_status(f"Error: {e}")
            self.add_system_message(f"Error: {e}")

        finally:
            self.root.after(
                0,
                lambda: (
                    self.start_button.config(state=tk.NORMAL),
                    self.stop_button.config(state=tk.DISABLED),
                ),
            )

    def run(self):
        """Run the TKinter application."""
        self.root.mainloop()


def main():
    # Validate environment
    if not os.getenv("HUME_API_KEY"):
        logger.error("HUME_API_KEY environment variable is not set")
        sys.exit(1)
    if not os.getenv("HUME_CONFIG_ID"):
        logger.error("HUME_CONFIG_ID environment variable is not set")
        sys.exit(1)

    app = HumeBotApp()
    app.run()


if __name__ == "__main__":
    main()
