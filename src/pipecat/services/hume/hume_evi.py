"""Hume EVI (Empathic Voice Interface) service using hume 0.7.0 HumeVoiceClient."""

import asyncio
import base64
import io
import json
import wave
from dataclasses import dataclass
from typing import Optional

from hume import HumeVoiceClient
from loguru import logger

from pipecat.frames.frames import (
    AggregationType,
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    InputAudioRawFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    StartFrame,
    StartInterruptionFrame,
    SystemFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TTSTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.utils.time import time_now_iso8601


@dataclass
class HumeEVIStartFrame(SystemFrame):
    """Frame to trigger Hume EVI connection."""

    pass


class HumeEVIService(FrameProcessor):
    """Hume EVI (Empathic Voice Interface) service using HumeVoiceClient.

    This service uses Hume's Empathic Voice Interface via the hume 0.7.0 SDK
    to provide speech-to-speech functionality with emotion detection.
    """

    def __init__(
        self,
        *,
        api_key: str,
        config_id: str,
        start_frame_cls: type[Frame] | None = None,
        audio_passthrough: bool = False,
        **kwargs,
    ):
        """Initialize HumeEVIService.

        Args:
            api_key: Hume API key.
            config_id: Hume EVI configuration ID.
            start_frame_cls: Frame class that triggers connection.
            audio_passthrough: Whether to pass audio frames downstream.
            **kwargs: Additional arguments for FrameProcessor.
        """
        super().__init__(**kwargs)
        logger.debug("Initializing HumeEVIService")
        self._audio_passthrough = audio_passthrough
        self.api_key = api_key
        self.config_id = config_id
        self._client: Optional[HumeVoiceClient] = None
        self._socket = None
        self._socket_context = None
        self._receive_task: Optional[asyncio.Task] = None
        self._is_connected = False
        self.active_conversation: bool = False
        self.active_conversation_id: Optional[str] = None
        self.cancelled_conversation_ids: list[str] = []
        self._start_frame_cls = start_frame_cls or HumeEVIStartFrame

    async def start(self, frame: StartFrame):
        """Handle start frame."""
        await super().start(frame)

    async def stop(self, frame: EndFrame):
        """Handle end frame."""
        await super().stop(frame)
        await self._disconnect()

    async def cancel(self, frame: CancelFrame):
        """Handle cancel frame."""
        await super().cancel(frame)
        await self._disconnect()

    async def reset_conversation(self):
        """Reset the conversation by reconnecting."""
        await self._disconnect()
        await self._connect()
        self.active_conversation = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames."""
        await super().process_frame(frame, direction)

        if isinstance(frame, self._start_frame_cls):
            await self._connect()

        elif isinstance(frame, StartInterruptionFrame):
            if self.active_conversation_id is not None:
                self.cancelled_conversation_ids.append(self.active_conversation_id)
            self.active_conversation_id = None
            self.active_conversation = False
            await self.push_frame(frame)

        elif isinstance(frame, InputAudioRawFrame):
            await self._send_audio(frame.audio)
            if self._audio_passthrough:
                await self.push_frame(frame, direction)

        else:
            await self.push_frame(frame, direction)

    async def _connect(self):
        """Connect to Hume EVI WebSocket."""
        try:
            logger.info("Connecting to Hume EVI...")
            self._client = HumeVoiceClient(api_key=self.api_key)

            # Properly use async context manager
            self._socket_context = self._client.connect(config_id=self.config_id)
            self._socket = await self._socket_context.__aenter__()

            # Wait a moment for connection to stabilize
            await asyncio.sleep(0.1)

            self._is_connected = True
            logger.info("Connected to Hume EVI")

            # Start receiving messages in background
            self._receive_task = asyncio.create_task(self._receive_loop())

        except Exception as e:
            logger.error(f"Failed to connect to Hume EVI: {e}")
            await self.push_error(ErrorFrame(error=str(e), fatal=True))

    async def _disconnect(self):
        """Disconnect from Hume EVI."""
        self._is_connected = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._socket_context:
            try:
                await self._socket_context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing Hume context: {e}")
            self._socket_context = None
            self._socket = None

        self._client = None
        logger.info("Disconnected from Hume EVI")

    async def _receive_loop(self):
        """Receive and process messages from Hume."""
        try:
            message_count = 0
            async for message in self._socket:
                message_count += 1
                logger.debug(f"Received message #{message_count} from Hume")
                await self._handle_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if self._is_connected:
                logger.error(f"Hume receive loop error: {e}")
                await self.push_error(ErrorFrame(error=str(e), fatal=True))
        finally:
            self._is_connected = False

    async def _handle_message(self, message):
        """Handle incoming message from Hume."""
        try:
            # Parse message if it's a string (JSON)
            if isinstance(message, str):
                message_data = json.loads(message)
            elif isinstance(message, bytes):
                message_data = json.loads(message.decode("utf-8"))
            else:
                message_data = message

            msg_type = message_data.get("type")
            logger.info(f" Hume message type: {msg_type}")

            # Check if this message is from a cancelled conversation
            msg_id = message_data.get("id")
            if msg_id and msg_id in self.cancelled_conversation_ids:
                return

            if msg_type == "audio_output":
                await self._handle_audio_output(message_data)

            elif msg_type == "assistant_message":
                await self._handle_assistant_message(message_data)

            elif msg_type == "user_message":
                await self._handle_user_message(message_data)

            elif msg_type == "assistant_end":
                await self._handle_assistant_end(message_data)

            elif msg_type == "user_interruption":
                await self.push_frame(StartInterruptionFrame())

            elif msg_type == "chat_metadata":
                logger.info(f"Hume chat metadata: {message_data}")

            elif msg_type == "error":
                error_msg = message_data.get("message", str(message_data))
                logger.error(f"❌ Hume error: {message_data}")
                await self.push_error(ErrorFrame(error=error_msg, fatal=False))

        except Exception as e:
            logger.error(f"Error handling Hume message: {e}")

    async def _handle_audio_output(self, message_data: dict):
        """Handle audio output from Hume."""
        self.active_conversation_id = message_data.get("id")

        if not self.active_conversation:
            self.active_conversation = True
            await self.push_frame(TTSStartedFrame())
            await self.push_frame(LLMFullResponseStartFrame())

        # Decode audio data
        audio_b64 = message_data.get("data", "")
        wav_data = base64.b64decode(audio_b64)

        # Parse WAV to get raw PCM
        with io.BytesIO(wav_data) as wav_file:
            with wave.open(wav_file, "rb") as wav_reader:
                sample_rate = wav_reader.getframerate()
                num_channels = wav_reader.getnchannels()
                audio_frames = wav_reader.readframes(wav_reader.getnframes())

        frame = TTSAudioRawFrame(
            audio=audio_frames, sample_rate=sample_rate, num_channels=num_channels
        )
        await self.push_frame(frame)

        samples_count = len(audio_frames) / 2
        logger.debug(
            f"Received audio from Hume: {samples_count} samples, "
            f"channels: {num_channels}, duration: {samples_count / num_channels / sample_rate:.2f}s"
        )

    async def _handle_assistant_message(self, message_data: dict):
        """Handle assistant message (transcript) from Hume."""
        logger.info(f"Assistant message: {message_data}")
        message_obj = message_data.get("message", {})
        if message_obj:
            content = message_obj.get("content", "")
            if content:
                await self.push_frame(LLMTextFrame(text=content))
                await self.push_frame(
                    TTSTextFrame(text=content, aggregated_by=AggregationType.SENTENCE)
                )

    async def _handle_user_message(self, message_data: dict):
        """Handle user message (transcription) from Hume."""
        logger.info(f"User message: {message_data}")
        message_obj = message_data.get("message", {})
        if message_obj:
            content = message_obj.get("content", "")
            if content:
                await self.push_frame(
                    TranscriptionFrame(
                        text=content, user_id="", timestamp=time_now_iso8601(), result=message_data
                    )
                )

    async def _handle_assistant_end(self, message_data: dict):
        """Handle end of assistant response."""
        logger.info(f"Assistant end for conversation id: {self.active_conversation_id}")
        self.active_conversation = False
        await self.push_frame(LLMFullResponseEndFrame())
        await self.push_frame(TTSStoppedFrame())

    async def _send_audio(self, audio_data: bytes):
        """Send audio data to Hume."""
        if not self._is_connected or not self._socket:
            return

        try:
            # VoiceSocket.send() expects raw PCM bytes
            logger.debug(f"Sending {len(audio_data)} bytes of audio to Hume")
            await self._socket.send(audio_data)
        except Exception as e:
            logger.error(f"Error sending audio to Hume: {e}")
            await self.reset_conversation()

    async def push_error(self, frame: ErrorFrame):
        """Push an error frame downstream."""
        await self.push_frame(frame)
