"""
Main server for Conversational AI with Lip-Sync Avatar.
Coordinates frontend, Hume.ai, and Wav2Lip processing.
"""

import asyncio
import base64
import json
import logging
import os
import time
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

import config
from hume_client import SimpleHumeClient
from wav2lip_processor import VideoFrameCache, Wav2LipProcessor
from expression_client import HumeStreamingExpressionClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Conversational AI Lip-Sync POC")

# Global state
video_cache: Optional[VideoFrameCache] = None


class ConversationSession:
    """
    Manages a single conversation session.
    Coordinates between frontend WebSocket, Hume.ai, and Wav2Lip.
    """
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.hume_client: Optional[SimpleHumeClient] = None
        self.wav2lip_processor: Optional[Wav2LipProcessor] = None
        self.expression_client: Optional[HumeStreamingExpressionClient] = None
        
        self.is_active = False
        self.current_video_time = 0.0
        self.audio_buffer = bytearray()
        
        # Track speaking state
        self.is_speaking = False
        
        # TTFB tracking - measure from when user stops speaking to first AI audio
        self.last_user_audio_time = None
        self.user_speech_end_time = None  # When user transcript is received (speech ended)
        self.ttfb_ms = None
        self.ttfb_calculated = False  # Only calculate once per turn
        
    async def start(self):
        """Start the conversation session."""
        self.is_active = True
        
        # Initialize Wav2Lip processor
        self.wav2lip_processor = Wav2LipProcessor(
            video_cache=video_cache,
            on_frame=self._on_lip_sync_frame
        )
        self.wav2lip_processor.initialize()
        self.wav2lip_processor.start_processing()
        
        # Initialize Hume client
        self.hume_client = SimpleHumeClient(
            on_audio_received=self._on_hume_audio,
            on_transcript=self._on_transcript,
            on_status_change=self._on_status_change,
            on_emotions=self._on_emotions,
            on_assistant_end=self._on_assistant_end,
        )
        
        # Initialize Expression client for facial analysis
        self.expression_client = HumeStreamingExpressionClient(
            on_expressions=self._on_face_expressions
        )
        
        # Connect to Hume in background
        asyncio.create_task(self._connect_hume())
        asyncio.create_task(self._connect_expression())
        
    async def _connect_hume(self):
        """Connect to Hume.ai."""
        try:
            await self.hume_client.connect()
        except Exception as e:
            logger.error(f"Failed to connect to Hume: {e}")
            await self._send_error(f"Failed to connect to Hume: {e}")
            
    async def _connect_expression(self):
        """Connect to Hume Expression API."""
        try:
            await self.expression_client.connect()
        except Exception as e:
            logger.warning(f"Expression API connection failed (non-critical): {e}")
    
    def _on_face_expressions(self, emotions: list):
        """Called when facial expressions are detected."""
        asyncio.create_task(self._send_emotions("user", emotions))
            
    async def stop(self):
        """Stop the conversation session."""
        self.is_active = False
        
        if self.wav2lip_processor:
            self.wav2lip_processor.stop_processing()
            
        if self.hume_client:
            await self.hume_client.disconnect()
            
        if self.expression_client:
            await self.expression_client.disconnect()
            
    async def handle_message(self, data: dict):
        """Handle incoming message from frontend."""
        msg_type = data.get("type", "")
        
        if msg_type == "audio":
            # User audio from microphone
            audio_b64 = data.get("audio", "")
            video_time = data.get("videoTime", 0.0)
            
            if audio_b64:
                audio_data = base64.b64decode(audio_b64)
                self.current_video_time = video_time
                
                # Track when user sends audio for TTFB calculation
                self.last_user_audio_time = time.time()
                
                # Send to Hume
                if self.hume_client and self.hume_client.is_connected:
                    await self.hume_client.send_audio(audio_data)
        
        elif msg_type == "webcam_frame":
            # Webcam frame for expression analysis
            frame_b64 = data.get("frame", "")
            if frame_b64 and self.expression_client and self.expression_client.is_connected:
                await self.expression_client.send_frame(frame_b64)
                    
        elif msg_type == "audio_playback_end":
            # Frontend finished playing audio
            self.is_speaking = False
            await self._send_frame_end()
            await self._send_status(speaking=False, listening=True)
            
    def _on_hume_audio(self, audio_data: bytes):
        """Called when audio is received from Hume."""
        # Calculate TTFB on first audio response of this turn
        # TTFB = time from user speech end (transcript received) to first AI audio
        if not self.ttfb_calculated and self.user_speech_end_time:
            self.ttfb_ms = int((time.time() - self.user_speech_end_time) * 1000)
            self.ttfb_calculated = True
            logger.info(f"TTFB: {self.ttfb_ms}ms (from user speech end to first AI audio)")
            
        self.is_speaking = True
        
        # Add to buffer for Wav2Lip processing
        self.audio_buffer.extend(audio_data)
        
        # Process audio for lip-sync
        if self.wav2lip_processor:
            self.wav2lip_processor.process_audio(audio_data, self.current_video_time)
            # Advance video time based on audio duration
            # 16kHz, 16-bit = 32000 bytes per second
            self.current_video_time += len(audio_data) / 32000
            
        # Send audio to frontend for playback
        asyncio.create_task(self._send_audio(audio_data))
        
    def _on_lip_sync_frame(self, frame_bytes: bytes):
        """Called when a lip-synced frame is ready (called from thread via call_soon_threadsafe)."""
        if self.is_speaking:
            # This is called from the main event loop via call_soon_threadsafe
            # so we can safely create a task here
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._send_frame(frame_bytes))
            except RuntimeError:
                # No running loop, try to get the event loop another way
                pass
            
    def _on_transcript(self, role: str, text: str, emotions: list = None):
        """Called when transcript is received."""
        if role == "user":
            # User finished speaking - mark the time for TTFB calculation
            self.user_speech_end_time = time.time()
            self.ttfb_calculated = False  # Reset for new turn
            self.ttfb_ms = None
        
        # Include TTFB for AI responses
        ttfb = self.ttfb_ms if role == "ai" else None
        asyncio.create_task(self._send_transcript(role, text, ttfb, emotions))
    
    def _on_emotions(self, role: str, emotions: list):
        """Called when emotions are detected."""
        asyncio.create_task(self._send_emotions(role, emotions))
    
    def _on_assistant_end(self):
        """Called when assistant finishes speaking."""
        asyncio.create_task(self._send_assistant_end())
        
    def _on_status_change(self, status: str):
        """Called when Hume status changes."""
        if status == "speaking":
            asyncio.create_task(self._send_status(speaking=True, listening=False))
        elif status == "listening":
            asyncio.create_task(self._send_status(speaking=False, listening=True))
        elif status == "idle":
            asyncio.create_task(self._send_status(speaking=False, listening=True))
            
    async def _send_audio(self, audio_data: bytes):
        """Send audio to frontend."""
        try:
            await self.websocket.send_json({
                "type": "audio",
                "audio": base64.b64encode(audio_data).decode('utf-8'),
            })
        except Exception as e:
            logger.error(f"Error sending audio: {e}")
            
    async def _send_frame(self, frame_bytes: bytes):
        """Send lip-synced frame to frontend."""
        try:
            await self.websocket.send_json({
                "type": "frame",
                "frame": base64.b64encode(frame_bytes).decode('utf-8'),
            })
        except Exception as e:
            logger.error(f"Error sending frame: {e}")
            
    async def _send_frame_end(self):
        """Signal end of lip-sync frames."""
        try:
            await self.websocket.send_json({
                "type": "frame_end",
            })
        except Exception as e:
            logger.error(f"Error sending frame_end: {e}")
            
    async def _send_transcript(self, role: str, text: str, ttfb_ms: Optional[int] = None, emotions: list = None):
        """Send transcript to frontend."""
        try:
            msg = {
                "type": "transcript",
                "role": role,
                "text": text,
            }
            if ttfb_ms is not None:
                msg["ttfb_ms"] = ttfb_ms
            if emotions:
                msg["emotions"] = emotions
            await self.websocket.send_json(msg)
        except Exception as e:
            logger.error(f"Error sending transcript: {e}")
    
    async def _send_emotions(self, role: str, emotions: list):
        """Send emotions update to frontend."""
        try:
            await self.websocket.send_json({
                "type": "user_emotions",
                "role": role,
                "emotions": emotions,
            })
        except Exception as e:
            logger.error(f"Error sending emotions: {e}")
    
    async def _send_assistant_end(self):
        """Send assistant turn ended signal to frontend."""
        try:
            await self.websocket.send_json({
                "type": "assistant_end",
            })
        except Exception as e:
            logger.error(f"Error sending assistant_end: {e}")
            
    async def _send_status(self, speaking: bool, listening: bool):
        """Send status update to frontend."""
        try:
            await self.websocket.send_json({
                "type": "status",
                "speaking": speaking,
                "listening": listening,
            })
        except Exception as e:
            logger.error(f"Error sending status: {e}")
            
    async def _send_error(self, message: str):
        """Send error to frontend."""
        try:
            await self.websocket.send_json({
                "type": "error",
                "message": message,
            })
        except Exception as e:
            logger.error(f"Error sending error: {e}")


# Active sessions
sessions: Dict[int, ConversationSession] = {}


@app.on_event("startup")
async def startup():
    """Initialize on server startup."""
    global video_cache
    
    logger.info("Starting Conversational AI Lip-Sync Server...")
    
    # Load video frames
    video_path = os.path.join(os.path.dirname(__file__), config.IDLE_VIDEO_PATH)
    video_cache = VideoFrameCache(video_path)
    
    try:
        video_cache.load()
        logger.info("Video cache loaded successfully")
    except FileNotFoundError:
        logger.warning(f"Idle video not found at {video_path}")
        logger.warning("Please place your idle video at: assets/idle.mp4")
        # Create empty cache for testing
        video_cache.frames = []
        video_cache.frame_count = 0
        

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on server shutdown."""
    logger.info("Shutting down server...")
    
    # Stop all sessions
    for session in sessions.values():
        await session.stop()
    sessions.clear()


@app.get("/")
async def root():
    """Serve the main page."""
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "static", "index.html")
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for conversation."""
    await websocket.accept()
    
    session_id = id(websocket)
    session = ConversationSession(websocket)
    sessions[session_id] = session
    
    logger.info(f"New session: {session_id}")
    
    try:
        await session.start()
        
        while True:
            data = await websocket.receive_json()
            await session.handle_message(data)
            
    except WebSocketDisconnect:
        logger.info(f"Session disconnected: {session_id}")
    except Exception as e:
        logger.error(f"Session error: {e}")
    finally:
        await session.stop()
        del sessions[session_id]


# Mount static files
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

# Mount assets (for idle video)
assets_dir = os.path.join(os.path.dirname(__file__), "assets")
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
else:
    os.makedirs(assets_dir, exist_ok=True)
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


def main():
    """Run the server."""
    logger.info(f"Starting server on http://{config.HOST}:{config.PORT}")
    uvicorn.run(
        "server:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
