"""
Hume.ai EVI (Empathic Voice Interface) WebSocket client.
Handles speech-to-speech conversation with Hume's API.
"""

import asyncio
import base64
import json
import logging
from typing import Callable, Optional

import config

logger = logging.getLogger(__name__)


class HumeEVIClient:
    """
    Client for Hume.ai's Empathic Voice Interface.
    Manages real-time speech-to-speech conversation.
    """
    
    def __init__(
        self,
        on_audio_received: Callable[[bytes], None],
        on_transcript: Callable[[str, str], None],  # (role, text)
        on_status_change: Callable[[str], None],
    ):
        self.on_audio_received = on_audio_received
        self.on_transcript = on_transcript
        self.on_status_change = on_status_change
        
        self.client: Optional[HumeVoiceClient] = None
        self.socket = None
        self.is_connected = False
        self._audio_buffer = bytearray()
        
    async def connect(self):
        """Connect to Hume EVI WebSocket."""
        try:
            self.on_status_change("connecting")
            
            # Initialize Hume client
            self.client = HumeVoiceClient(
                api_key=config.HUME_API_KEY,
            )
            
            # Connect to EVI
            async with self.client.connect(
                config_id=config.HUME_CONFIG_ID
            ) as socket:
                self.socket = socket
                self.is_connected = True
                self.on_status_change("connected")
                logger.info("Connected to Hume EVI")
                
                # Listen for messages
                async for message in socket:
                    await self._handle_message(message)
                    
        except Exception as e:
            logger.error(f"Hume connection error: {e}")
            self.on_status_change("error")
            raise
        finally:
            self.is_connected = False
            self.socket = None
            
    async def _handle_message(self, message):
        """Handle incoming message from Hume."""
        try:
            msg_type = message.type
            
            if msg_type == "audio_output":
                # Received audio response from AI
                audio_data = base64.b64decode(message.data)
                self.on_audio_received(audio_data)
                self.on_status_change("speaking")
                
            elif msg_type == "assistant_message":
                # AI transcript
                if hasattr(message, 'message') and message.message:
                    text = message.message.content
                    self.on_transcript("ai", text)
                    
            elif msg_type == "user_message":
                # User transcript (what Hume heard)
                if hasattr(message, 'message') and message.message:
                    text = message.message.content
                    self.on_transcript("user", text)
                    self.on_status_change("listening")
                    
            elif msg_type == "assistant_end":
                # AI finished speaking
                self.on_status_change("listening")
                
            elif msg_type == "error":
                logger.error(f"Hume error: {message}")
                self.on_status_change("error")
                
        except Exception as e:
            logger.error(f"Error handling Hume message: {e}")
            
    async def send_audio(self, audio_data: bytes):
        """Send audio data to Hume for processing."""
        if not self.is_connected or not self.socket:
            logger.warning("Cannot send audio: not connected")
            return
            
        try:
            # Hume expects base64-encoded audio
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')
            await self.socket.send_audio(audio_b64)
        except Exception as e:
            logger.error(f"Error sending audio to Hume: {e}")
            
    async def disconnect(self):
        """Disconnect from Hume."""
        self.is_connected = False
        if self.socket:
            try:
                await self.socket.close()
            except:
                pass
        self.socket = None
        logger.info("Disconnected from Hume EVI")


class SimpleHumeClient:
    """
    Simplified Hume client using direct WebSocket connection.
    More control over the connection for our POC.
    """
    
    def __init__(
        self,
        on_audio_received: Callable[[bytes], None],
        on_transcript: Callable[[str, str], None],
        on_status_change: Callable[[str], None],
        on_emotions: Callable[[str, list], None] = None,  # (role, emotions)
        on_assistant_end: Callable[[], None] = None,
    ):
        self.on_audio_received = on_audio_received
        self.on_transcript = on_transcript
        self.on_status_change = on_status_change
        self.on_emotions = on_emotions
        self.on_assistant_end = on_assistant_end
        
        self.ws = None
        self.is_connected = False
        self._receive_task = None
        
    async def connect(self):
        """Connect to Hume EVI via WebSocket."""
        import websockets
        
        try:
            self.on_status_change("connecting")
            
            # Hume EVI WebSocket URL
            url = "wss://api.hume.ai/v0/evi/chat"
            
            # Headers for authentication
            headers = {
                "X-Hume-Api-Key": config.HUME_API_KEY,
            }
            
            self.ws = await websockets.connect(url, additional_headers=headers)
            self.is_connected = True
            self.on_status_change("connected")
            logger.info("Connected to Hume EVI WebSocket")
            
            # Send session settings
            await self._send_session_settings()
            
            # Start receiving messages
            self._receive_task = asyncio.create_task(self._receive_loop())
            
        except Exception as e:
            logger.error(f"Hume connection error: {e}")
            self.on_status_change("error")
            raise
            
    async def _send_session_settings(self):
        """Send initial session configuration."""
        settings = {
            "type": "session_settings",
            "audio": {
                "encoding": "linear16",
                "sample_rate": config.AUDIO_SAMPLE_RATE,
                "channels": 1,
            },
        }
        
        if config.HUME_CONFIG_ID:
            settings["config_id"] = config.HUME_CONFIG_ID
        
        await self.ws.send(json.dumps(settings))
        
    async def _receive_loop(self):
        """Receive and process messages from Hume."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                await self._handle_message(data)
        except Exception as e:
            if self.is_connected:
                logger.error(f"Receive loop error: {e}")
                self.on_status_change("error")
        finally:
            self.is_connected = False
            
    async def _handle_message(self, data: dict):
        """Handle incoming message from Hume."""
        msg_type = data.get("type", "")
        
        # Log only important messages (not verbose audio data)
        if msg_type not in ["audio_output", "audio_input"]:
            logger.debug(f"Hume message: {msg_type}")
        
        if msg_type == "audio_output":
            # Received audio from AI
            audio_b64 = data.get("data", "")
            if audio_b64:
                audio_data = base64.b64decode(audio_b64)
                self.on_audio_received(audio_data)
            self.on_status_change("speaking")
            
        elif msg_type == "assistant_message":
            # AI transcript
            content = data.get("message", {}).get("content", "")
            if content:
                self.on_transcript("ai", content)
                
        elif msg_type == "user_message":
            # User transcript with emotions
            content = data.get("message", {}).get("content", "")
            
            # Extract emotions from prosody/expression models
            emotions = self._extract_emotions(data)
            
            if content:
                self.on_transcript("user", content, emotions)
            
            # Also send emotions separately for real-time updates
            if self.on_emotions and emotions:
                self.on_emotions("user", emotions)
                
            self.on_status_change("listening")
            
        elif msg_type == "assistant_end":
            self.on_status_change("idle")
            if self.on_assistant_end:
                self.on_assistant_end()
            
        elif msg_type == "error":
            logger.error(f"Hume error: {data}")
            self.on_status_change("error")
    
    def _extract_emotions(self, data: dict) -> list:
        """Extract emotion scores from Hume message data."""
        emotions = []
        
        # Try to get emotions from various possible locations in the response
        # Hume EVI can include prosody, expression, and language emotion data
        
        # Check for models in the message
        models = data.get("models", {})
        
        # Prosody emotions (from voice)
        prosody = models.get("prosody", {})
        if prosody:
            predictions = prosody.get("predictions", [])
            for pred in predictions:
                for emotion in pred.get("emotions", []):
                    emotions.append({
                        "name": emotion.get("name", "Unknown"),
                        "score": emotion.get("score", 0),
                        "source": "prosody"
                    })
        
        # Language emotions (from text)
        language = models.get("language", {})
        if language:
            predictions = language.get("predictions", [])
            for pred in predictions:
                for emotion in pred.get("emotions", []):
                    emotions.append({
                        "name": emotion.get("name", "Unknown"),
                        "score": emotion.get("score", 0),
                        "source": "language"
                    })
        
        # Expression emotions (from face if available)
        expression = models.get("face", {}) or models.get("expression", {})
        if expression:
            predictions = expression.get("predictions", [])
            for pred in predictions:
                for emotion in pred.get("emotions", []):
                    emotions.append({
                        "name": emotion.get("name", "Unknown"),
                        "score": emotion.get("score", 0),
                        "source": "expression"
                    })
        
        # Also check for emotions directly in message
        message_emotions = data.get("message", {}).get("emotions", [])
        if message_emotions:
            for emotion in message_emotions:
                emotions.append({
                    "name": emotion.get("name", "Unknown"),
                    "score": emotion.get("score", 0),
                    "source": "message"
                })
        
        # Check for prosody at top level
        top_prosody = data.get("prosody", {})
        if top_prosody:
            scores = top_prosody.get("scores", {})
            for name, score in scores.items():
                emotions.append({
                    "name": name.replace("_", " ").title(),
                    "score": score,
                    "source": "prosody"
                })
        
        # Deduplicate and sort by score
        if emotions:
            # Keep highest score for each emotion name
            emotion_dict = {}
            for e in emotions:
                name = e["name"]
                if name not in emotion_dict or e["score"] > emotion_dict[name]["score"]:
                    emotion_dict[name] = e
            emotions = sorted(emotion_dict.values(), key=lambda x: x["score"], reverse=True)
        
        return emotions
            
    async def send_audio(self, audio_data: bytes):
        """Send audio to Hume."""
        if not self.is_connected or not self.ws:
            return
            
        try:
            message = {
                "type": "audio_input",
                "data": base64.b64encode(audio_data).decode('utf-8'),
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
