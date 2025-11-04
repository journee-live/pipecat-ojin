#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import os
import struct
import sys
import time
import wave

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer

# Ensure we can import from parent directory
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from pipecat.audio.utils import create_default_resampler
from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InputAudioRawFrame,
    OutputAudioRawFrame,
    StartFrame,
    StartInterruptionFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.hume.hume import HumeStartFrame, HumeSTSService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


class LatencyMeasurementProcessor(FrameProcessor):
    """Measures latency from end of input audio to first output audio."""

    def __init__(self):
        super().__init__()
        self._user_stopped_time = None
        self._first_audio_received = False
        self._input_audio_start_time = 0
        self._stopped_speaking_time = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._stopped_speaking_time = time.perf_counter()
            logger.info("⏱️  User stopped speaking")

        elif isinstance(frame, TTSStartedFrame):
            latency = (time.perf_counter() - self._stopped_speaking_time) * 1000  # Convert to ms
            logger.success(f"")
            logger.success(f"{'=' * 80}")
            logger.success(f"🎯 LATENCY MEASUREMENT: {latency:.0f}ms")
            logger.success(f"{'=' * 80}")
            logger.success(f"")
        elif isinstance(frame, StartInterruptionFrame):
            self._first_audio_received = False
            logger.info("⏱️  StartInterruptionFrame")
        await self.push_frame(frame, direction)


class AudioOutputQueue(FrameProcessor):
    """Queues TTS audio frames and manages playback at any sample rate."""

    def __init__(self):
        """Initialize the audio output queue processor."""
        super().__init__()
        self._audio_queue = asyncio.Queue()
        self._running = False
        self._task = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            await self.start()
        elif isinstance(frame, EndFrame):
            await self.stop()
        elif isinstance(frame, StartInterruptionFrame):
            await self.clear_queue()
            logger.info("🧹 AudioOutputQueue: Cleared queue due to interruption")
        elif isinstance(frame, TTSAudioRawFrame):
            # Queue only TTS audio frames to avoid queueing bypassed input audio
            await self._audio_queue.put(frame)
            logger.debug(
                f"📥 AudioOutputQueue: Queued TTS audio frame ({len(frame.audio)} bytes, {frame.sample_rate} Hz, queue size: {self._audio_queue.qsize()})"
            )
            # Don't push the frame downstream yet - it will be processed by the queue task
            return

        await self.push_frame(frame, direction)

    async def start(self):
        """Start processing the audio queue."""
        self._running = True
        self._task = self.create_task(self._process_queue())
        logger.info(f"▶️  AudioOutputQueue: Started processing")

    async def stop(self):
        """Stop processing the audio queue."""
        logger.info("⏹️  AudioOutputQueue: Stopping queue processor")
        self._running = False
        if self._task:
            await self.cancel_task(self._task)
            self._task = None

    async def clear_queue(self):
        """Clear all pending audio frames from the queue."""
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _process_queue(self):
        """Process audio frames from the queue at the correct rate."""
        try:
            while self._running:
                try:
                    # Get the next audio frame from the queue
                    frame = await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)

                    # Calculate the duration of this audio chunk using the frame's sample rate
                    num_samples = len(frame.audio) // 2  # 16-bit audio = 2 bytes per sample
                    duration = num_samples / frame.sample_rate

                    logger.debug(
                        f"📤 AudioOutputQueue: Processing frame ({len(frame.audio)} bytes, {frame.sample_rate} Hz, {duration * 1000:.1f}ms)"
                    )

                    # Push the frame downstream
                    await self.push_frame(frame, FrameDirection.DOWNSTREAM)

                    # Wait for the duration of the audio to maintain real-time playback
                    await asyncio.sleep(duration)

                except asyncio.TimeoutError:
                    # No audio in queue, continue waiting
                    continue

        except Exception as e:
            logger.error(f"❌ AudioOutputQueue: Error processing queue: {e}")
            raise


class WavFileInputProcessor(FrameProcessor):
    """Reads a wav file and sends audio frames to the pipeline."""

    def __init__(
        self,
        wav_file_path: str,
        chunk_size: int = 4800,
        chunk_delay: float = 0.3,
        volume_threshold: float = 350.0,
    ):
        """
        Initialize the wav file input processor.

        Args:
            wav_file_path: Path to the wav file to read
            chunk_size: Number of frames to read per chunk
            chunk_delay: Delay between chunks in seconds
            volume_threshold: RMS volume threshold for speech detection
        """
        super().__init__()
        self.wav_file_path = wav_file_path
        self.chunk_size = chunk_size
        self.chunk_delay = chunk_delay
        self.volume_threshold = volume_threshold
        self._resampler = create_default_resampler()
        self._running = False
        self._task = None
        self._is_speaking = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            await self.start(frame)
        elif isinstance(frame, EndFrame):
            await self.stop(frame)

        await self.push_frame(frame, direction)

    async def start(self, frame: StartFrame):
        """Start reading from the wav file."""
        self._running = True
        self._task = self.create_task(self._read_wav_file())
        logger.info(f"Started reading wav file: {self.wav_file_path}")

    async def stop(self, frame: EndFrame):
        """Stop reading from the wav file."""
        logger.info("Stopping wav file reader")
        self._running = False
        if self._task:
            await self.cancel_task(self._task)
            self._task = None

    def _calculate_rms_volume(self, audio_data: bytes, sample_width: int) -> float:
        """
        Calculate the RMS (Root Mean Square) volume of audio data.

        Args:
            audio_data: Raw audio bytes
            sample_width: Number of bytes per sample (2 for 16-bit audio)

        Returns:
            RMS volume as a float
        """
        if len(audio_data) == 0:
            return 0.0

        # Convert bytes to integers based on sample width
        if sample_width == 2:  # 16-bit audio
            format_char = "h"  # signed short
            max_value = 32768.0
        elif sample_width == 1:  # 8-bit audio
            format_char = "b"  # signed char
            max_value = 128.0
        else:
            return 0.0

        # Unpack audio data into samples
        num_samples = len(audio_data) // sample_width
        samples = struct.unpack(
            f"{num_samples}{format_char}", audio_data[: num_samples * sample_width]
        )

        # Calculate RMS
        sum_squares = sum(sample * sample for sample in samples)
        rms = (sum_squares / num_samples) ** 0.5

        return rms

    async def _read_wav_file(self):
        """Read the wav file and send audio frames in a loop."""
        try:
            with wave.open(self.wav_file_path, "rb") as wav_file:
                # Get wav file properties
                num_channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                sample_rate = wav_file.getframerate()
                num_frames = wav_file.getnframes()

                logger.info(f"Wav file properties:")
                logger.info(f"  Channels: {num_channels}")
                logger.info(f"  Sample width: {sample_width} bytes")
                logger.info(f"  Sample rate: {sample_rate} Hz")
                logger.info(f"  Total frames: {num_frames}")
                logger.info(f"  Duration: {num_frames / sample_rate:.2f} seconds")

                # Validate audio format and prepare for resampling if needed
                # Hume expects: linear16 (16-bit PCM), 16000 Hz, mono (1 channel)
                if sample_width != 2:
                    raise ValueError(
                        f"Invalid sample width. Hume expects 16-bit PCM (2 bytes), got {sample_width * 8}-bit"
                    )
                if num_channels != 1:
                    raise ValueError(
                        f"Invalid channel count. Hume expects mono (1 channel), got {num_channels} channels"
                    )

                # Check if resampling is needed
                target_sample_rate = 24000
                needs_resampling = sample_rate != target_sample_rate

                if needs_resampling:
                    logger.warning(
                        f"⚠️  Sample rate mismatch: {sample_rate} Hz → resampling to {target_sample_rate} Hz"
                    )
                else:
                    logger.info(
                        f"✓ Audio format validated: 16-bit PCM, {sample_rate} Hz, mono - matches Hume requirements"
                    )

                # Wait a bit before starting to send audio
                await asyncio.sleep(1.0)

                # Loop playback
                loop_count = 0
                while self._running:
                    loop_count += 1
                    logger.info(f"🔁 Starting playback iteration #{loop_count}")
                    await self.push_frame(StartInterruptionFrame(), FrameDirection.DOWNSTREAM)
                    # Reset speaking state for each iteration
                    self._is_speaking = False
                    # Rewind to beginning for subsequent iterations
                    wav_file.rewind()

                    # Read and send audio in chunks at real-time rate
                    total_sent = 0
                    start_time = time.perf_counter()
                    while self._running:
                        audio_data = wav_file.readframes(self.chunk_size)
                        if len(audio_data) == 0:
                            logger.info(f"Reached end of wav file (iteration #{loop_count})")
                            break

                        # Resample if needed
                        if needs_resampling:
                            audio_data = await self._resampler.resample(
                                audio_data, sample_rate, target_sample_rate
                            )
                            # Update chunk size after resampling
                            effective_sample_rate = target_sample_rate
                        else:
                            effective_sample_rate = sample_rate

                        # Calculate when this chunk should be sent based on real-time playback
                        # Use target sample rate for timing to match real-time at output rate
                        chunk_samples = len(audio_data) // (sample_width * num_channels)
                        expected_time = start_time + (
                            total_sent / (sample_width * num_channels) / target_sample_rate
                        )
                        current_time = time.perf_counter()

                        # Wait until it's time to send this chunk
                        if current_time < expected_time:
                            await asyncio.sleep(expected_time - current_time)

                        # Send audio frame with target sample rate
                        frame = InputAudioRawFrame(
                            audio=audio_data,
                            sample_rate=target_sample_rate,
                            num_channels=num_channels,
                        )
                        await self.push_frame(frame, FrameDirection.DOWNSTREAM)

                        frame = OutputAudioRawFrame(
                            audio=audio_data,
                            sample_rate=target_sample_rate,
                            num_channels=num_channels,
                        )
                        await self.push_frame(frame, FrameDirection.DOWNSTREAM)

                        # Calculate volume for speech detection
                        volume = self._calculate_rms_volume(audio_data, sample_width)

                        # Detect speech start/stop based on volume threshold
                        if volume > self.volume_threshold and not self._is_speaking:
                            logger.warning(f"🎤 User started speaking (volume: {volume:.1f})")
                            self._is_speaking = True
                        elif volume <= self.volume_threshold and self._is_speaking:
                            logger.warning(f"🔇 User stopped speaking (volume: {volume:.1f})")
                            self._is_speaking = False
                            await self.push_frame(
                                UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM
                            )

                        total_sent += len(audio_data)
                        samples_sent = total_sent / sample_width
                        duration_sent = samples_sent / num_channels / target_sample_rate

                        logger.debug(
                            f"Sent {len(audio_data)} bytes ({duration_sent:.2f}s of audio, volume: {volume:.1f})"
                        )

                    # Signal end of user speech
                    logger.info(f"Finished wav playback iteration #{loop_count}")

                    # Wait 2 seconds before next iteration
                    if self._running:
                        logger.info("⏸️  Waiting 4 seconds before next playback...")
                        await asyncio.sleep(3.0)

        except Exception as e:
            logger.error(f"Error reading wav file: {e}")
            raise


async def main():
    """Main test function for HumeSTSService."""

    # Configuration
    wav_file_path = os.path.join(os.path.dirname(__file__), "assets", "short.wav")

    # Check if API keys are set
    api_key = os.getenv("HUME_API_KEY", "")
    config_id = os.getenv("HUME_CONFIG_ID", "")

    if not api_key or not config_id:
        logger.error("HUME_API_KEY and HUME_CONFIG_ID must be set in environment variables")
        return

    # Create audio transport for output only
    audio_transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_out_enabled=True,
            audio_in_enabled=False,
            vad_enabled=True,
            vad_audio_passthrough=True,
            vad_analyzer=SileroVADAnalyzer(),
        )
    )

    # Create Hume STS service
    llm = HumeSTSService(
        api_key=api_key,
        config_id=config_id,
        model=os.getenv("HUME_MODEL", "evi"),
        start_frame_cls=HumeStartFrame,
        audio_passthrough=True,
    )

    # Create context (required for Hume service)
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant.",
        },
    ]
    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    # Create wav file input processor
    wav_input = WavFileInputProcessor(
        wav_file_path=wav_file_path,
        chunk_size=4800,  # ~0.3 seconds of audio at 16kHz
        chunk_delay=0.3,
        volume_threshold=500.0,  # RMS volume threshold for speech detection
    )

    latency_meter = LatencyMeasurementProcessor()  # Measure latency
    audio_queue = AudioOutputQueue()  # Queue and manage audio output

    # Build pipeline
    pipeline = Pipeline(
        [
            wav_input,  # Read from wav file
            context_aggregator.user(),  # User context
            llm,  # Hume STS service
            latency_meter,  # Measure latency
            audio_queue,  # Queue and manage audio output at any sample rate
            audio_transport.output(),  # Audio output to local device
            context_aggregator.assistant(),  # Assistant context
        ]
    )

    # Create task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            allow_interruptions=False,
        ),
    )

    # Queue the HumeStartFrame to initiate connection
    await task.queue_frames([HumeStartFrame()])

    # Run the pipeline
    runner = PipelineRunner(handle_sigint=False)

    logger.info("Starting Hume test...")
    logger.info(f"Reading audio from: {wav_file_path}")
    logger.info("Audio output will be sent to local audio device")
    logger.info("Press Ctrl+C to stop")

    try:
        await runner.run(task)
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        raise
    finally:
        logger.info("Test completed")


if __name__ == "__main__":
    asyncio.run(main())
