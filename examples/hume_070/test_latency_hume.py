"""Test Hume latency using the old HumeSTSService (hume 0.12.1) with WAV file input.

Measures the time from sending audio to receiving the first audio response.
"""

import asyncio
import os
import sys
import time
import wave

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
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.hume.hume import HumeStartFrame, HumeSTSService

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
        self.user_transcript = None
        self.assistant_transcript = None
        self.audio_chunks_received = 0
        self.total_audio_duration = 0.0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            if not self.first_transcript_received_time and self.last_silent_chunk_time:
                self.first_transcript_received_time = time.time()
                latency = (self.first_transcript_received_time - self.last_silent_chunk_time) * 1000
                logger.info(f"⏱️  First transcript latency: {latency:.0f}ms")
            self.user_transcript = frame.text
            logger.info(f"👤 User: {frame.text}")

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

            # Calculate audio duration
            samples = len(frame.audio) / 2  # 16-bit audio
            duration = samples / frame.sample_rate
            self.total_audio_duration += duration

        await self.push_frame(frame, direction)

    def print_summary(self):
        """Print latency summary."""
        logger.info("\n" + "=" * 60)
        logger.info("LATENCY TEST SUMMARY (OLD HUME SERVICE)")
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


async def send_wav_file(
    task: PipelineTask, wav_path: str, measurement: LatencyMeasurementProcessor
):
    """Read WAV file and send as audio frames."""
    logger.info(f"📂 Reading WAV file: {wav_path}")
    await task.queue_frame(HumeStartFrame())
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

    # Wait for connection
    await asyncio.sleep(6)

    logger.info("🚀 Sending audio to Hume...")

    # Send audio in chunks at real-time pace (20ms chunks every 20ms)
    chunk_size = 640  # 20ms chunks at 16kHz after resampling

    logger.info("🎵 Sending WAV audio...")

    import struct

    prev_volume = None

    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i : i + chunk_size]

        frame = InputAudioRawFrame(audio=chunk, sample_rate=sample_rate, num_channels=num_channels)

        samples = struct.unpack(f"{len(frame.audio) // 2}h", frame.audio)
        avg_volume = sum(abs(s) for s in samples) / len(samples) if samples else 0

        # Track the transition from non-zero to zero volume (end of speech)
        if prev_volume is not None and prev_volume > 0.0 and avg_volume == 0.0:
            measurement.last_silent_chunk_time = time.time()
            logger.debug(
                f"📍 End of speech detected (transition to silence) at {measurement.last_silent_chunk_time}"
            )

        prev_volume = avg_volume

        # logger.info(f"Sending audio input: {len(frame.audio)} bytes, avg_volume: {avg_volume:.1f}")
        await task.queue_frame(frame)
        await asyncio.sleep(0.02)  # Real-time: 20ms delay for 20ms chunks

    await asyncio.sleep(5)
    # Continue sending silence for the remaining test duration
    # Create a silence chunk (all zeros)
    # silence_chunk = b"\x00" * chunk_size

    # # Send silence for 10 seconds (500 chunks of 20ms each)
    # for _ in range(500):
    #     frame = InputAudioRawFrame(
    #         audio=silence_chunk, sample_rate=sample_rate, num_channels=num_channels
    #     )
    #     await task.queue_frame(frame)
    #     await asyncio.sleep(0.02)

    # logger.info("✅ Silence sent, ending test...")

    # End the task
    await task.queue_frame(EndFrame())


async def main():
    # Validate environment
    if not os.getenv("HUME_API_KEY"):
        logger.error("❌ HUME_API_KEY environment variable is not set")
        sys.exit(1)
    if not os.getenv("HUME_CONFIG_ID"):
        logger.error("❌ HUME_CONFIG_ID environment variable is not set")
        sys.exit(1)

    # Check WAV file exists
    wav_path = "short.wav"
    if not os.path.exists(wav_path):
        logger.error(f"❌ WAV file not found: {wav_path}")
        sys.exit(1)

    logger.info("🎯 Starting Hume Latency Test (OLD SERVICE - hume 0.12.1)")
    logger.info("=" * 60)

    # Create old Hume service with debug audio recording
    hume_service = HumeSTSService(
        api_key=os.getenv("HUME_API_KEY"),
        config_id=os.getenv("HUME_CONFIG_ID"),
        debug_audio_file="sent_audio_debug.wav",
    )

    # hume_service = HumeEVIService(
    #     api_key=os.getenv("HUME_API_KEY"),
    #     config_id=os.getenv("HUME_CONFIG_ID"),
    # )

    # Create measurement processor
    measurement = LatencyMeasurementProcessor()

    # Build pipeline
    pipeline = Pipeline([hume_service, measurement])

    task = PipelineTask(pipeline)
    runner = PipelineRunner(handle_sigint=False)

    try:
        await asyncio.gather(
            runner.run(task),
            send_wav_file(task, wav_path, measurement),
        )
    except KeyboardInterrupt:
        logger.info("⚠️  Test interrupted by user")
    finally:
        measurement.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
