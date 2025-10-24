#!/usr/bin/env python3
#
# Electron-compatible bot adapter for Ojin Agents Desktop
# Based on ojin-chatbot/bot.py but adapted for IPC communication
#

import asyncio
import base64
import json
import os
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import Frame, OutputAudioRawFrame, OutputImageRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.hume.hume import HumeSTSService
from pipecat.services.ojin.video import (
    OjinPersonaInitializedFrame,
    OjinPersonaService,
    OjinPersonaSettings,
)
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="INFO")


class ElectronIPCOutput(FrameProcessor):
    """Sends video frames and transcript updates to Electron via stdout as JSON."""

    def __init__(self, suppress_video_logging=False, **kwargs):
        super().__init__(**kwargs)
        self._suppress_video_logging = suppress_video_logging

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        try:
            if isinstance(frame, OutputImageRawFrame):
                # Encode image as base64 JPEG
                image_bytes = frame.image
                if isinstance(image_bytes, bytes):
                    b64_image = base64.b64encode(image_bytes).decode("utf-8")

                    message = {
                        "type": "video_frame",
                        "data": b64_image,
                        "width": frame.size[0] if frame.size else 1280,
                        "height": frame.size[1] if frame.size else 720,
                        "format": getattr(frame, "format", "JPEG"),
                    }

                    # Send to Electron via stdout (suppress if in debug mode)
                    if not self._suppress_video_logging:
                        print(json.dumps(message), flush=True)

        except Exception as e:
            logger.error(f"Error sending frame to Electron: {e}")

        await self.push_frame(frame, direction)


class TranscriptCapture(FrameProcessor):
    """Captures conversation transcript and sends to Electron."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # TODO: Capture text frames and send as transcript updates
        # This will depend on how Hume/LLM outputs text

        await self.push_frame(frame, direction)


async def main():
    if len(sys.argv) < 3:
        logger.error("Usage: python bot.py <persona_id> <hume_config_id>")
        sys.exit(1)

    persona_id = sys.argv[1]
    hume_config_id = sys.argv[2]

    logger.info(
        f"Starting bot session with persona_id={persona_id}, hume_config_id={hume_config_id}"
    )

    # Send ready signal to Electron
    print(
        json.dumps({"type": "ready", "persona_id": persona_id, "hume_config_id": hume_config_id}),
        flush=True,
    )

    # Initialize audio transport
    audio_transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_out_enabled=True,
            audio_in_enabled=True,
            vad_enabled=True,
            vad_audio_passthrough=True,
            vad_analyzer=SileroVADAnalyzer(),
        )
    )

    # Initialize LLM service with Hume
    llm = HumeSTSService(
        api_key=os.getenv("HUME_API_KEY", ""),
        config_id=hume_config_id,
        model=os.getenv("HUME_MODEL", "evi"),
        start_frame_cls=OjinPersonaInitializedFrame,
    )

    messages = [
        {
            "role": "system",
            "content": "Always answer the last question from the context no matter who was the role of the last question",
        },
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    # Initialize Ojin Persona service
    ojin_ws_url = os.getenv("OJIN_PROXY_URL", "wss://models.ojin.ai/realtime")

    # Add mode as query parameter if specified
    persona = OjinPersonaService(
        OjinPersonaSettings(
            ws_url=ojin_ws_url,
            api_key=os.getenv("OJIN_API_KEY", ""),
            persona_config_id=persona_id,
            image_size=(1280, 720),
            tts_audio_passthrough=False,
            push_bot_stopped_speaking_frames=False,
        )
    )

    # Create IPC output handler
    # Suppress video logging when debugging to avoid console spam
    suppress_video = os.getenv("SUPPRESS_VIDEO_LOGS", "false").lower() == "true"
    electron_output = ElectronIPCOutput(suppress_video_logging=suppress_video)
    transcript_capture = TranscriptCapture()

    # Build pipeline
    pipeline = Pipeline(
        [
            audio_transport.input(),
            context_aggregator.user(),
            llm,
            persona,
            electron_output,  # Send frames to Electron
            transcript_capture,  # Capture transcript
            audio_transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True, enable_usage_metrics=True, allow_interruptions=True
        ),
    )

    runner = PipelineRunner(handle_sigint=False)
    
    # Setup signal handler for graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        shutdown_event.set()
    
    # Register signal handlers (Windows doesn't support all signals)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("Bot pipeline started")
    print(json.dumps({"type": "started"}), flush=True)

    try:
        # Run with cancellation support
        run_task = asyncio.create_task(runner.run(task))
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        
        done, pending = await asyncio.wait(
            [run_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel remaining tasks
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
                
    except KeyboardInterrupt:
        logger.info("Bot session interrupted")
    except Exception as e:
        logger.error(f"Bot session error: {e}")
        print(json.dumps({"type": "error", "message": str(e)}), flush=True)
    finally:
        logger.info("Bot session ended")
        print(json.dumps({"type": "ended"}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
