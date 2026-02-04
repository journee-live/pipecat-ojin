"""Standalone Hume latency test without Pipecat framework.

Uses only the Hume SDK to measure latency from end of speech to first audio response.
"""

import asyncio
import csv
import os
import struct
import sys
import time
import wave
from datetime import datetime

from dotenv import load_dotenv
from hume import AsyncHumeClient
from hume.empathic_voice import AudioConfiguration, SessionSettings
from hume.empathic_voice.chat.socket_client import ChatConnectOptions, ChatWebsocketConnection
from loguru import logger

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="INFO")


class LatencyMeasurement:
    """Track latency measurements."""

    def __init__(self):
        self.last_silent_chunk_time = None
        self.first_audio_received_time = None
        self.first_transcript_received_time = None
        self.user_transcript = None
        self.assistant_transcript = None
        self.audio_chunks_received = 0
        self.total_audio_duration = 0.0
        self.chat_metadata = None
        self.first_audio_message_id = None

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

        if self.chat_metadata:
            logger.info(f"📋 Chat metadata: {self.chat_metadata}")
        if self.first_audio_message_id:
            logger.info(f"🆔 First audio message ID: {self.first_audio_message_id}")

        logger.info("=" * 60)

    def save_to_csv(self, csv_path: str):
        """Save latency results to CSV file."""
        timestamp = datetime.now().isoformat()

        time_to_first_audio = None
        time_to_first_transcript = None

        if self.last_silent_chunk_time and self.first_audio_received_time:
            time_to_first_audio = (
                self.first_audio_received_time - self.last_silent_chunk_time
            ) * 1000

        if self.last_silent_chunk_time and self.first_transcript_received_time:
            time_to_first_transcript = (
                self.first_transcript_received_time - self.last_silent_chunk_time
            ) * 1000

        # Check if file exists and is empty to write header
        file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0

        with open(csv_path, "a", newline="") as csvfile:
            fieldnames = [
                "timestamp",
                "time_to_first_audio_ms",
                "time_to_first_transcript_ms",
                "audio_chunks_received",
                "total_audio_duration_s",
                "user_transcript",
                "assistant_transcript",
                "chat_metadata",
                "first_audio_message_id",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()

            writer.writerow(
                {
                    "timestamp": timestamp,
                    "time_to_first_audio_ms": f"{time_to_first_audio:.0f}"
                    if time_to_first_audio
                    else "",
                    "time_to_first_transcript_ms": f"{time_to_first_transcript:.0f}"
                    if time_to_first_transcript
                    else "",
                    "audio_chunks_received": self.audio_chunks_received,
                    "total_audio_duration_s": f"{self.total_audio_duration:.2f}",
                    "user_transcript": self.user_transcript or "",
                    "assistant_transcript": self.assistant_transcript or "",
                    "chat_metadata": self.chat_metadata or "",
                    "first_audio_message_id": self.first_audio_message_id or "",
                }
            )

        logger.info(f"💾 Results saved to {csv_path}")


async def send_audio(
    socket: ChatWebsocketConnection,
    wav_path: str,
    measurement: LatencyMeasurement,
    initialized_event: asyncio.Event,
):
    """Send audio from WAV file to Hume."""
    logger.info(f"📂 Reading WAV file: {wav_path}")

    with wave.open(wav_path, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        num_channels = wav_file.getnchannels()
        num_frames = wav_file.getnframes()

        logger.info(f"🎵 WAV info: {sample_rate}Hz, {num_channels} channel(s), {num_frames} frames")

        # Read all audio data
        audio_data = wav_file.readframes(num_frames)

    # Calculate duration
    duration = num_frames / sample_rate
    logger.info(f"⏱️  Audio duration: {duration:.2f}s")

    # Wait for connection to be ready
    await initialized_event.wait()

    logger.info("🚀 Sending audio to Hume...")

    # At 16kHz, 20ms = 320 samples = 640 bytes (16-bit PCM)
    chunk_size = 640  # 20ms at 16kHz

    logger.info("🎵 Sending WAV audio...")

    prev_volume = None

    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i : i + chunk_size]

        # Calculate volume
        samples = struct.unpack(f"{len(chunk) // 2}h", chunk)
        avg_volume = sum(abs(s) for s in samples) / len(samples) if samples else 0

        # Track the transition from non-zero to zero volume (end of speech)
        if prev_volume is not None and prev_volume > 0.0 and avg_volume == 0.0:
            measurement.last_silent_chunk_time = time.perf_counter()
            logger.success(
                f"📍 End of speech detected (transition to silence) at {measurement.last_silent_chunk_time}"
            )

        prev_volume = avg_volume

        # logger.info(f"Sending audio to hume: {len(chunk)} bytes")
        await socket._send(chunk)
        await asyncio.sleep(0.02)  # Real-time: 20ms delay for 20ms chunks


def create_message_handler(
    measurement: LatencyMeasurement, stop_event: asyncio.Event, initialized_event: asyncio.Event
):
    """Create message handler callbacks."""

    def on_message(message):
        """Handle incoming messages from Hume."""
        msg_type = message.type

        if msg_type == "user_message":
            if (
                not measurement.first_transcript_received_time
                and measurement.last_silent_chunk_time
            ):
                measurement.first_transcript_received_time = time.perf_counter()

            measurement.user_transcript = message.message.content

        elif msg_type == "assistant_message":
            measurement.assistant_transcript = message.message.content

        elif msg_type == "audio_output":
            measurement.audio_chunks_received += 1

            if not measurement.first_audio_received_time and measurement.last_silent_chunk_time:
                measurement.first_audio_received_time = time.perf_counter()
                # Capture the message ID of the first audio
                if hasattr(message, "id"):
                    measurement.first_audio_message_id = message.id
                # Signal to stop after receiving first audio
                logger.success(f"First audio received at {measurement.first_audio_received_time}")
                stop_event.set()

            # Calculate audio duration
            if hasattr(message, "data") and message.data:
                duration = len(message.data) / 48000.0  # Assuming 48kHz output
                measurement.total_audio_duration += duration

        elif msg_type == "assistant_end":
            logger.info(f"✅ Assistant end")
            stop_event.set()

        elif msg_type == "error":
            logger.error(f"❌ Error from Hume: {message}")

        elif msg_type == "chat_metadata":
            logger.info(f"📋 Chat metadata: {message}")
            # Store the full chat metadata as JSON string
            import json

            measurement.chat_metadata = json.dumps(
                message.dict() if hasattr(message, "dict") else str(message)
            )
            initialized_event.set()

    return on_message


async def main():
    """Main test function."""
    # Check WAV file exists
    wav_path = "short_16k.wav"
    if not os.path.exists(wav_path):
        logger.error(f"❌ WAV file not found: {wav_path}")
        sys.exit(1)

    logger.info("🎯 Starting Standalone Hume Latency Test (hume 0.12.1)")
    logger.info("=" * 60)

    # Create measurement tracker
    measurement = LatencyMeasurement()

    # Create Hume client
    client = AsyncHumeClient(api_key=os.getenv("HUME_API_KEY"))

    # Create stop event to signal when to end the test
    stop_event = asyncio.Event()

    initialized_event = asyncio.Event()

    # Create message handler
    on_message = create_message_handler(measurement, stop_event, initialized_event)

    try:
        # Connect to Hume with callbacks
        async with client.empathic_voice.chat.connect_with_callbacks(
            options=ChatConnectOptions(config_id=os.getenv("HUME_CONFIG_ID")),
            on_open=lambda: logger.info("🔌 Connected to Hume"),
            on_close=lambda: logger.info("🔌 Disconnected from Hume"),
            on_error=lambda error: logger.error(f"❌ Connection error: {error}"),
            on_message=on_message,
        ) as socket:
            await socket.send_session_settings(
                SessionSettings(
                    type="session_settings",
                    system_prompt=None,
                    audio=AudioConfiguration(
                        encoding="linear16",
                        sample_rate=16000,
                        channels=1,
                    ),
                )
            )
            # Send audio and wait for stop signal
            await send_audio(socket, wav_path, measurement, initialized_event)

            # Wait for first audio response or timeout
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("⏱️  Timeout waiting for response")

    except KeyboardInterrupt:
        logger.info("⚠️  Test interrupted by user")
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
    finally:
        measurement.print_summary()
        await asyncio.sleep(1.0)
        measurement.save_to_csv("latency_history.csv")


if __name__ == "__main__":
    asyncio.run(main())
