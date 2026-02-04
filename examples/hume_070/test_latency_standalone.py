"""Standalone Hume latency test without Pipecat framework.

Uses only the Hume SDK to measure latency from end of speech to first audio response.
"""

import asyncio
import base64
import os
import struct
import sys
import time
import wave

import numpy as np
from dotenv import load_dotenv
from hume_client import SimpleHumeClient
from loguru import logger

from pipecat.audio.utils import create_default_resampler

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


async def send_audio(client: SimpleHumeClient, wav_path: str, measurement: LatencyMeasurement):
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
    await asyncio.sleep(5)

    logger.info("🚀 Sending audio to Hume...")

    # At 16kHz, 20ms = 320 samples = 640 bytes (16-bit PCM)
    chunk_size = 640  # 20ms at 16kHz

    logger.info("🎵 Sending WAV audio...")

    prev_volume = None

    resampler = create_default_resampler()
    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i : i + chunk_size]

        # Calculate volume
        samples = struct.unpack(f"{len(chunk) // 2}h", chunk)
        avg_volume = sum(abs(s) for s in samples) / len(samples) if samples else 0

        # Track the transition from non-zero to zero volume (end of speech)
        if prev_volume is not None and prev_volume > 0.0 and avg_volume == 0.0:
            measurement.last_silent_chunk_time = time.time()
            logger.success(
                f"📍 End of speech detected (transition to silence) at {measurement.last_silent_chunk_time}"
            )

        prev_volume = avg_volume

        chunk = await resampler.resample(chunk, 48000, 16000)

        await client.send_audio(chunk)
        await asyncio.sleep(0.02)  # Real-time: 20ms delay for 20ms chunks

    logger.info("✅ Audio sent, waiting for response...")


def create_message_handler(measurement: LatencyMeasurement, stop_event: asyncio.Event):
    """Create message handler callbacks."""

    def on_message(message):
        """Handle incoming messages from Hume."""
        msg_type = message.type

        if msg_type == "user_message":
            if (
                not measurement.first_transcript_received_time
                and measurement.last_silent_chunk_time
            ):
                measurement.first_transcript_received_time = time.time()
                latency = (
                    measurement.first_transcript_received_time - measurement.last_silent_chunk_time
                ) * 1000
                logger.info(f"⏱️  First transcript latency: {latency:.0f}ms")

            measurement.user_transcript = message.message.content
            logger.info(f"👤 User: {message.message.content}")

        elif msg_type == "assistant_message":
            measurement.assistant_transcript = message.message.content
            logger.info(f"🤖 Assistant: {message.message.content}")

        elif msg_type == "audio_output":
            measurement.audio_chunks_received += 1

            if not measurement.first_audio_received_time and measurement.last_silent_chunk_time:
                measurement.first_audio_received_time = time.time()
                latency = (
                    measurement.first_audio_received_time - measurement.last_silent_chunk_time
                ) * 1000
                logger.success(f"🎵 First audio latency: {latency:.0f}ms")
                # Signal to stop after receiving first audio
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

    return on_message


async def main():
    """Main test function."""
    # Check WAV file exists
    wav_path = "short.wav"
    if not os.path.exists(wav_path):
        logger.error(f"❌ WAV file not found: {wav_path}")
        sys.exit(1)

    logger.info("🎯 Starting Standalone Hume Latency Test (hume 0.7.0)")
    logger.info("=" * 60)

    # Create measurement tracker
    measurement = LatencyMeasurement()

    # Create stop event to signal when to end the test
    stop_event = asyncio.Event()
    on_message = create_message_handler(measurement, stop_event)
    # Create Hume client
    hume_client = SimpleHumeClient(
        on_message=on_message,
    )

    try:
        # Connect to Hume with callbacks
        await hume_client.connect()
        # Send audio and wait for stop signal
        await send_audio(hume_client, wav_path, measurement)

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


if __name__ == "__main__":
    asyncio.run(main())
