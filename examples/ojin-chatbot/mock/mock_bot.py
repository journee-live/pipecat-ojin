#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import io
import os
import sys
import tkinter as tk
from typing import Awaitable

import cv2
import numpy as np
from dotenv import load_dotenv
from loguru import logger
from PIL import Image

from pipecat.pipeline.pipeline import Pipeline
from pipecat.frames.frames import Frame, ImageRawFrame, OutputImageRawFrame
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.ojin.video import OjinPersonaService, OjinPersonaSettings
from mock_tts import MockTTSProcessor
from pipecat.transports.local.tk import TkLocalTransport, TkTransportParams
# Ensure we can import sibling 'utils' package when running from the 'mock' subdir
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from utils.frame_metrics import FrameMetricsProcessor
from utils.tk_overlay import create_fps_overlay, start_tk_updater_with_fps

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


class ImageFormatConverter(FrameProcessor):
    """Converts image frames from JPG/BGR format to PPM format."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        
        if isinstance(frame, OutputImageRawFrame):
            try:
                # Get the image bytes data
                image_bytes = frame.image
                
                # Check if it's bytes data
                if isinstance(image_bytes, bytes):
                    # Decode the image from bytes (assuming it's JPEG format from Ojin)
                    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
                    
                    # Decode using OpenCV
                    decoded_image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
                    
                    if decoded_image is None:
                        logger.error("Failed to decode image from bytes")
                        await self.push_frame(frame, direction)
                        return
                    
                    # Convert from BGR to RGB (OpenCV loads as BGR by default)
                    rgb_image = cv2.cvtColor(decoded_image, cv2.COLOR_BGR2RGB)
                    
                    # Convert to raw RGB bytes (what Tkinter expects for PPM)
                    # The Tkinter transport will add the PPM header itself
                    rgb_bytes = rgb_image.tobytes()
                    
                    # Create new frame with raw RGB data
                    converted_frame = OutputImageRawFrame(
                        image=rgb_bytes,  # Use raw RGB bytes
                        size=(rgb_image.shape[1], rgb_image.shape[0]),  # (width, height)
                        format="RGB"
                    )
                    
                    await self.push_frame(converted_frame, direction)
                else:
                    await self.push_frame(frame, direction)
                
            except Exception as e:
                logger.error(f"Error converting image format: {e}")
                await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)


async def main():    

    input = MockTTSProcessor(
        {
            "audio_sequence": [                
                ("./mock/assets/long_audio_16k.wav", 20),
                ("./mock/assets/long_audio_16k.wav", 23),
            ],
            "event_sequence": [                
                ("user_started_speaking", 18),
                ("user_stopped_speaking", 19),
                ("user_started_speaking", 21),
                ("user_stopped_speaking", 22),
            ],
            "chunk_size": 600000,
            "chunk_delay": 0.2,
        },
    )


    tk_root = tk.Tk()
    tk_root.title("Ojin Persona Chatbot")
    
    # Configure window to be visible on Windows
    tk_root.geometry("1280x720")
    tk_root.resizable(True, True)
    tk_root.lift()
    tk_root.attributes('-topmost', True)
    tk_root.after_idle(tk_root.attributes, '-topmost', False)
    tk_root.focus_force()
    
    # Create FPS overlay and start Tk updater
    fps_canvas = create_fps_overlay(tk_root, x=8, y=8, width=320, height=120)
    tk_update_task = start_tk_updater_with_fps(tk_root, fps_canvas, interval_ms=10)

    tk_transport = TkLocalTransport(
        tk_root,
        TkTransportParams(
            audio_in_enabled=False,
            audio_out_enabled=False,
            video_out_enabled=True,
            video_out_is_live=True,
            video_out_width=1280,
            video_out_height=720,
        ),
    )

    
   
    # DITTO_SERVER_URL: str = "wss://eu-central-1.models.ojin.foo/realtime"
    persona = OjinPersonaService(OjinPersonaSettings(
        ws_url=os.getenv("OJIN_PROXY_URL", ""),
        api_key=os.getenv("OJIN_API_KEY", ""),
        persona_config_id=os.getenv("OJIN_PERSONA_ID", ""),        
        image_size=(1280, 720),
        idle_to_speech_seconds=1.5,
        idle_sequence_duration=5,
        tts_audio_passthrough=False,
        push_bot_stopped_speaking_frames=False,
    ))    

    # Frame metrics and image format converter
    frame_metrics = FrameMetricsProcessor()
    image_converter = ImageFormatConverter()
    
    pipeline = Pipeline(
        [
            input,
            persona,
            frame_metrics,
            image_converter,  # Convert image format from BGR to PPM
            tk_transport.output(),  # Transport video output
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            allow_interruptions=True
        ),
    )

    # messages.append({"role": "system", "content": "Please introduce yourself to the user."})
    # await task.queue_frames([context_aggregator.user().get_context_frame()])

    runner = PipelineRunner(handle_sigint=False)

    try:
        await runner.run(task)
    finally:
        # Clean up the Tkinter update task
        if 'tk_update_task' in locals():
            tk_update_task.cancel()
            try:
                await tk_update_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":    
    asyncio.run(main())
