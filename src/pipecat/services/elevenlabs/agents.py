"""ElevenLabs Conversational AI (Agents) Speech-to-Speech service.

This service connects to ElevenLabs' Conversational AI WebSocket API,
sending user audio and receiving agent audio, transcriptions, and
agent responses. It follows the same STS pattern as HumeSTSService.

Protocol reference (from elevenlabs-python SDK):
  - WebSocket URL: wss://api.elevenlabs.io/v1/convai/conversation?agent_id={agent_id}
  - Audio format: 16-bit PCM mono 16 kHz
  - Client sends: {"user_audio_chunk": "<base64>"}
  - Server sends: audio, agent_response, user_transcript, interruption, ping
"""

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Optional

import aiohttp
from loguru import logger

from pipecat.audio.utils import create_stream_resampler
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
from pipecat.processors.aggregators.llm_response import (
    LLMAssistantAggregatorParams,
    LLMUserAggregatorParams,
)
from pipecat.processors.aggregators.openai_llm_context import (
    OpenAILLMContext,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService
from pipecat.services.openai.llm import OpenAIContextAggregatorPair
from pipecat.services.openai_realtime_beta.context import (
    OpenAIRealtimeAssistantContextAggregator,
    OpenAIRealtimeLLMContext,
    OpenAIRealtimeUserContextAggregator,
)
from pipecat.utils.time import time_now_iso8601

try:
    from websockets.asyncio.client import connect as websocket_connect
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error("In order to use ElevenLabs Agents, you need to `pip install websockets`.")
    raise Exception(f"Missing module: {e}")

_BASE_URL = "https://api.elevenlabs.io"
_BASE_WS_URL = "wss://api.elevenlabs.io"
_AGENT_SAMPLE_RATE = 16000
_AGENT_CHANNELS = 1


@dataclass
class ElevenLabsAgentStartFrame(SystemFrame):
    """Frame that triggers ElevenLabs Agent WebSocket connection."""

    pass


class ElevenLabsAgentService(LLMService):
    """ElevenLabs Conversational AI (Agents) Speech-to-Speech service.

    Connects to an ElevenLabs Agent via WebSocket. Sends user audio
    and receives TTS audio frames, user transcription frames, and
    assistant text frames.
    """

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        model: str = "elevenlabs-agent",
        start_frame_cls: type[Frame] | None = None,
        audio_passthrough: bool = False,
        **kwargs,
    ):
        """Initialize the ElevenLabs Agent service.

        Args:
            api_key: ElevenLabs API key for authentication.
            agent_id: The ID of the ElevenLabs agent to converse with.
            model: Model name for metrics tracking.
            start_frame_cls: Frame class that triggers connection.
            audio_passthrough: Whether to pass input audio downstream.
            **kwargs: Additional arguments passed to LLMService.
        """
        super().__init__(**kwargs)
        logger.debug("Initializing ElevenLabsAgentService")
        self._api_key = api_key
        self._agent_id = agent_id
        self._audio_passthrough = audio_passthrough
        self._start_frame_cls = start_frame_cls or ElevenLabsAgentStartFrame

        self._websocket = None
        self._receive_task: asyncio.Task | None = None
        self._active_conversation: bool = False
        self._conversation_id: str | None = None
        self._last_interrupt_id: int = 0
        self._resampler = create_stream_resampler()

        self.set_model_name(model)

    async def start(self, frame: StartFrame) -> None:
        """Start the service."""
        await super().start(frame)

    async def stop(self, frame: EndFrame) -> None:
        """Stop the service and disconnect."""
        await super().stop(frame)
        await self._disconnect()

    async def cancel(self, frame: CancelFrame) -> None:
        """Cancel the service and disconnect."""
        await super().cancel(frame)
        await self._disconnect()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process incoming frames."""
        await super().process_frame(frame, direction)

        if isinstance(frame, self._start_frame_cls):
            logger.info("ElevenLabs Agent: start frame received, connecting")
            await self._connect()
            await self.push_frame(frame, direction)

        elif isinstance(frame, StartInterruptionFrame):
            self._active_conversation = False
            await self.push_frame(frame)

        elif isinstance(frame, InputAudioRawFrame):
            if self._websocket:
                audio = await self._resampler.resample(
                    frame.audio, frame.sample_rate, _AGENT_SAMPLE_RATE
                )
                await self._send_audio(audio)
            if self._audio_passthrough:
                await self.push_frame(frame, direction)

        else:
            await self.push_frame(frame, direction)

    # ------------------------------------------------------------------
    # WebSocket connection
    # ------------------------------------------------------------------

    async def _get_signed_url(self) -> str:
        """Obtain a signed WebSocket URL from the ElevenLabs API."""
        url = f"{_BASE_URL}/v1/convai/conversation/get_signed_url?agent_id={self._agent_id}"
        headers = {"xi-api-key": self._api_key}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Failed to get signed URL (HTTP {resp.status}): {text}")
                data = await resp.json()
                return data["signed_url"]

    async def _connect(self) -> None:
        try:
            signed_url = await self._get_signed_url()
            logger.debug(f"ElevenLabs Agent: connecting to signed URL")

            self._websocket = await websocket_connect(signed_url, max_size=16 * 1024 * 1024)

            # Send conversation initiation message
            initiation = json.dumps(
                {
                    "type": "conversation_initiation_client_data",
                    "conversation_config_override": {},
                    "dynamic_variables": {},
                }
            )
            await self._websocket.send(initiation)

            if not self._receive_task:
                self._receive_task = self.create_task(self._receive_loop())

            logger.info("ElevenLabs Agent: connected")
        except Exception as e:
            logger.error(f"ElevenLabs Agent: connection failed: {e}")
            self._websocket = None
            await self.push_error(
                error_msg=f"ElevenLabs Agent connection failed: {e}",
                exception=e,
            )

    async def _disconnect(self) -> None:
        if self._receive_task:
            await self.cancel_task(self._receive_task)
            self._receive_task = None

        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as e:
                logger.warning(f"ElevenLabs Agent: error closing websocket: {e}")
            finally:
                self._websocket = None

        self._active_conversation = False
        self._conversation_id = None
        self._last_interrupt_id = 0

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    async def _send_audio(self, audio: bytes) -> None:
        """Send a chunk of PCM audio to the agent."""
        if not self._websocket:
            return
        try:
            msg = json.dumps({"user_audio_chunk": base64.b64encode(audio).decode("utf-8")})
            await self._websocket.send(msg)
        except Exception as e:
            logger.error(f"ElevenLabs Agent: error sending audio: {e}")

    async def _send_pong(self, event_id: int) -> None:
        if not self._websocket:
            return
        try:
            await self._websocket.send(json.dumps({"type": "pong", "event_id": event_id}))
        except Exception as e:
            logger.warning(f"ElevenLabs Agent: error sending pong: {e}")

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        """Background task that reads WebSocket messages."""
        try:
            async for raw_msg in self._websocket:
                try:
                    message = json.loads(raw_msg)
                    await self._handle_message(message)
                except json.JSONDecodeError:
                    logger.warning("ElevenLabs Agent: non-JSON message received")
                except Exception as e:
                    logger.error(f"ElevenLabs Agent: error handling message: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"ElevenLabs Agent: receive loop error: {e}")

    async def _handle_message(self, message: dict) -> None:
        msg_type = message.get("type")

        if msg_type == "conversation_initiation_metadata":
            event = message.get("conversation_initiation_metadata_event", {})
            self._conversation_id = event.get("conversation_id")
            logger.info(f"ElevenLabs Agent: conversation started, id={self._conversation_id}")

        elif msg_type == "audio":
            event = message.get("audio_event", {})
            event_id = int(event.get("event_id", 0))
            if event_id <= self._last_interrupt_id:
                return

            if not self._active_conversation:
                self._active_conversation = True
                await self.push_frame(TTSStartedFrame())
                await self.push_frame(LLMFullResponseStartFrame())

            audio_b64 = event.get("audio_base_64", "")
            if audio_b64:
                audio = base64.b64decode(audio_b64)
                frame = TTSAudioRawFrame(
                    audio=audio,
                    sample_rate=_AGENT_SAMPLE_RATE,
                    num_channels=_AGENT_CHANNELS,
                )
                await self.push_frame(frame)

        elif msg_type == "agent_response":
            event = message.get("agent_response_event", {})
            content = event.get("agent_response", "").strip()
            if content:
                logger.info(f"ElevenLabs Agent response: {content}")
                await self.push_frame(LLMTextFrame(text=content))
                await self.push_frame(
                    TTSTextFrame(text=content, aggregated_by=AggregationType.SENTENCE)
                )

        elif msg_type == "user_transcript":
            event = message.get("user_transcription_event", {})
            transcript = event.get("user_transcript", "").strip()
            if transcript:
                logger.info(f"ElevenLabs Agent user transcript: {transcript}")
                # End previous agent turn if still active
                if self._active_conversation:
                    self._active_conversation = False
                    await self.push_frame(LLMFullResponseEndFrame())
                    await self.push_frame(TTSStoppedFrame())

                await self.push_frame(
                    TranscriptionFrame(
                        text=transcript,
                        user_id="",
                        timestamp=time_now_iso8601(),
                        result=event,
                    )
                )

        elif msg_type == "interruption":
            event = message.get("interruption_event", {})
            self._last_interrupt_id = int(event.get("event_id", 0))
            if self._active_conversation:
                self._active_conversation = False
                await self.push_frame(LLMFullResponseEndFrame())
                await self.push_frame(TTSStoppedFrame())
            await self.push_frame(StartInterruptionFrame())

        elif msg_type == "ping":
            event = message.get("ping_event", {})
            event_id = event.get("event_id", 0)
            await self._send_pong(event_id)

        elif msg_type == "agent_response_correction":
            event = message.get("agent_response_correction_event", {})
            corrected = event.get("corrected_agent_response", "").strip()
            if corrected:
                logger.debug(f"ElevenLabs Agent response correction: {corrected}")

        else:
            logger.trace(f"ElevenLabs Agent: unhandled message type: {msg_type}")

    # ------------------------------------------------------------------
    # Context aggregator (same pattern as HumeSTSService)
    # ------------------------------------------------------------------

    def create_context_aggregator(
        self,
        context: OpenAILLMContext,
        *,
        user_params: LLMUserAggregatorParams = LLMUserAggregatorParams(),
        assistant_params: LLMAssistantAggregatorParams = LLMAssistantAggregatorParams(),
    ) -> OpenAIContextAggregatorPair:
        """Create context aggregator pair (same pattern as HumeSTSService)."""
        context.set_llm_adapter(self.get_llm_adapter())
        OpenAIRealtimeLLMContext.upgrade_to_realtime(context)
        user = OpenAIRealtimeUserContextAggregator(context, params=user_params)
        assistant_params.expect_stripped_words = False
        assistant = OpenAIRealtimeAssistantContextAggregator(context, params=assistant_params)
        return OpenAIContextAggregatorPair(_user=user, _assistant=assistant)
