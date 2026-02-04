"""
Hume Expression Measurement API client.
Analyzes facial expressions from webcam frames.
"""

import asyncio
import base64
import json
import logging
from typing import Callable, Optional

import config

logger = logging.getLogger(__name__)


class HumeExpressionClient:
    """
    Client for Hume's Expression Measurement API.
    Sends webcam frames and receives facial expression analysis.
    """
    
    def __init__(self, on_expressions: Callable[[list], None]):
        self.on_expressions = on_expressions
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_active = False
        self._last_analysis_time = 0
        self._min_interval = 0.5  # Analyze at most every 500ms
        
    async def start(self):
        """Start the expression client."""
        self.session = aiohttp.ClientSession()
        self.is_active = True
        logger.info("Expression client started")
        
    async def stop(self):
        """Stop the expression client."""
        self.is_active = False
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("Expression client stopped")
        
    async def analyze_frame(self, frame_base64: str):
        """
        Send a frame to Hume Expression Measurement API.
        
        Args:
            frame_base64: Base64 encoded JPEG image
        """
        if not self.is_active or not self.session:
            return
            
        import time
        current_time = time.time()
        if current_time - self._last_analysis_time < self._min_interval:
            return  # Rate limiting
        self._last_analysis_time = current_time
        
        try:
            # Hume Expression Measurement API endpoint
            url = "https://api.hume.ai/v0/batch/jobs"
            
            headers = {
                "X-Hume-Api-Key": config.HUME_API_KEY,
                "Content-Type": "application/json",
            }
            
            # For streaming/real-time, we use the models endpoint directly
            # This is a simplified approach - for production, use streaming WebSocket
            await self._analyze_with_streaming(frame_base64)
            
        except Exception as e:
            logger.error(f"Expression analysis error: {e}")
            
    async def _analyze_with_streaming(self, frame_base64: str):
        """
        Use Hume's streaming API for real-time expression analysis.
        """
        try:
            import websockets
            
            url = "wss://api.hume.ai/v0/stream/models"
            
            headers = {
                "X-Hume-Api-Key": config.HUME_API_KEY,
            }
            
            async with websockets.connect(url, additional_headers=headers) as ws:
                # Send the frame for analysis
                message = {
                    "models": {
                        "face": {}  # Request facial expression analysis
                    },
                    "data": frame_base64,
                }
                
                await ws.send(json.dumps(message))
                
                # Receive the response
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(response)
                
                # Extract emotions from response
                emotions = self._extract_emotions(data)
                
                if emotions:
                    self.on_expressions(emotions)
                    
        except asyncio.TimeoutError:
            logger.warning("Expression analysis timed out")
        except Exception as e:
            logger.error(f"Streaming expression error: {e}")
            
    def _extract_emotions(self, data: dict) -> list:
        """Extract emotions from Hume API response."""
        emotions = []
        
        try:
            # Navigate the response structure
            face_data = data.get("face", {})
            predictions = face_data.get("predictions", [])
            
            for pred in predictions:
                for emotion in pred.get("emotions", []):
                    emotions.append({
                        "name": emotion.get("name", "Unknown"),
                        "score": emotion.get("score", 0),
                        "source": "expression"
                    })
                    
            # Sort by score
            emotions.sort(key=lambda x: x["score"], reverse=True)
            
        except Exception as e:
            logger.error(f"Error extracting emotions: {e}")
            
        return emotions


class HumeStreamingExpressionClient:
    """
    Persistent WebSocket connection for streaming expression analysis.
    More efficient for continuous webcam analysis.
    """
    
    def __init__(self, on_expressions: Callable[[list], None]):
        self.on_expressions = on_expressions
        self.ws = None
        self.is_connected = False
        self._receive_task = None
        self._last_send_time = 0
        self._min_interval = 0.3  # Send frames at most every 300ms
        
    async def connect(self):
        """Connect to Hume streaming API."""
        import websockets
        
        try:
            url = "wss://api.hume.ai/v0/stream/models"
            
            headers = {
                "X-Hume-Api-Key": config.HUME_API_KEY,
            }
            
            self.ws = await websockets.connect(url, additional_headers=headers)
            self.is_connected = True
            logger.info("Connected to Hume Expression Streaming API")
            
            # Start receiving responses
            self._receive_task = asyncio.create_task(self._receive_loop())
            
        except Exception as e:
            logger.error(f"Expression streaming connection error: {e}")
            self.is_connected = False
            
    async def _receive_loop(self):
        """Receive and process expression analysis results."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                emotions = self._extract_emotions(data)
                
                if emotions:
                    self.on_expressions(emotions)
                    
        except Exception as e:
            if self.is_connected:
                logger.error(f"Expression receive error: {e}")
        finally:
            self.is_connected = False
            
    async def send_frame(self, frame_base64: str):
        """Send a frame for analysis."""
        if not self.is_connected or not self.ws:
            return
            
        import time
        current_time = time.time()
        if current_time - self._last_send_time < self._min_interval:
            return  # Rate limiting
        self._last_send_time = current_time
        
        try:
            message = {
                "models": {
                    "face": {}
                },
                "data": frame_base64,
            }
            
            await self.ws.send(json.dumps(message))
            
        except Exception as e:
            logger.error(f"Error sending frame: {e}")
            
    def _extract_emotions(self, data: dict) -> list:
        """Extract emotions from Hume API response."""
        emotions = []
        
        try:
            # Check for face predictions
            face_data = data.get("face", {})
            predictions = face_data.get("predictions", [])
            
            for pred in predictions:
                for emotion in pred.get("emotions", []):
                    emotions.append({
                        "name": emotion.get("name", "Unknown"),
                        "score": emotion.get("score", 0),
                        "source": "expression"
                    })
            
            # Also check alternative response structures
            if not emotions:
                results = data.get("results", {})
                predictions = results.get("predictions", [])
                for pred in predictions:
                    models = pred.get("models", {})
                    face = models.get("face", {})
                    grouped = face.get("grouped_predictions", [])
                    for group in grouped:
                        for p in group.get("predictions", []):
                            for emotion in p.get("emotions", []):
                                emotions.append({
                                    "name": emotion.get("name", "Unknown"),
                                    "score": emotion.get("score", 0),
                                    "source": "expression"
                                })
                    
            # Sort by score
            emotions.sort(key=lambda x: x["score"], reverse=True)
            
        except Exception as e:
            logger.error(f"Error extracting emotions: {e}")
            
        return emotions
        
    async def disconnect(self):
        """Disconnect from streaming API."""
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
            
        logger.info("Disconnected from Expression Streaming API")
