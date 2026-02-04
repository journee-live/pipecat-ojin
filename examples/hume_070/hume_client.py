"""
Hume.ai EVI (Empathic Voice Interface) WebSocket client.
Handles speech-to-speech conversation with Hume's API.
"""

import asyncio
import base64
import json
import logging
import os
from types import SimpleNamespace
from typing import Any, Callable, Optional

import websockets
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)


class SimpleHumeClient:
    """
    Simplified Hume client using direct WebSocket connection.
    More control over the connection for our POC.
    """

    def __init__(
        self,
        on_message: Callable[[Any], None],
    ):
        self.on_message = on_message

        self.ws = None
        self.is_connected = False
        self._receive_task = None

    async def connect(self):
        """Connect to Hume EVI via WebSocket."""
        try:
            # Hume EVI WebSocket URL
            url = "wss://api.hume.ai/v0/evi/chat"

            # Headers for authentication
            headers = {
                "X-Hume-Api-Key": os.getenv("HUME_API_KEY"),
            }

            self.ws = await websockets.connect(url, extra_headers=headers)
            self.is_connected = True
            logger.info("Connected to Hume EVI WebSocket")

            # Send session settings
            await self._send_session_settings()

            # Start receiving messages
            self._receive_task = asyncio.create_task(self._receive_loop())

        except Exception as e:
            logger.error(f"Hume connection error: {e}")
            raise

    async def _send_session_settings(self):
        """Send initial session configuration."""
        settings = {
            "type": "session_settings",
            "audio": {
                "encoding": "linear16",
                "sample_rate": 16000,
                "channels": 1,
            },
        }

        if os.getenv("HUME_CONFIG_ID"):
            settings["config_id"] = os.getenv("HUME_CONFIG_ID")

        await self.ws.send(json.dumps(settings))

    async def _receive_loop(self):
        """Receive and process messages from Hume."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                # Convert dict to object with attribute access
                msg_obj = json.loads(message, object_hook=lambda d: SimpleNamespace(**d))
                self.on_message(msg_obj)
        except Exception as e:
            if self.is_connected:
                logger.error(f"Receive loop error: {e}")
        finally:
            self.is_connected = False

    async def send_audio(self, audio_data: bytes):
        """Send audio to Hume."""
        if not self.is_connected or not self.ws:
            return

        try:
            message = {
                "type": "audio_input",
                "data": base64.b64encode(audio_data).decode("utf-8"),
            }
            await self.ws.send(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending audio: {e}")

    async def disconnect(self):
        """Disconnect from Hume."""
        self.is_connected = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            await self.ws.close()
            self.ws = None

        logger.info("Disconnected from Hume")
