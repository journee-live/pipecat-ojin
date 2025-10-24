import React, { useState, useEffect, useRef, useCallback } from 'react';

function SessionWindow({ avatar, onHangUp }) {
  const [status, setStatus] = useState('initializing'); // connecting, initializing, active, error, ended
  const [error, setError] = useState(null);
  const [transcript, setTranscript] = useState([]);
  const [currentMessageIndex, setCurrentMessageIndex] = useState(0);
  const [hasVideo, setHasVideo] = useState(false);
  const videoRef = useRef(null);
  const sessionRef = useRef(null);
  const firstVideoFrameReceived = useRef(false);
  const personaInitialized = useRef(false);
  const lastBotError = useRef(null);
  const lastInitializedAvatarId = useRef(null);

  // Log status changes
  useEffect(() => {
    console.log(`[SessionWindow] Status changed to: ${status}`);
  }, [status]);

  useEffect(() => {
    // Validate configuration
    if (!avatar.ojin_persona_id || !avatar.hume_config_id) {
      setStatus('error');
      setError('Configuration missing: ojin_persona_id or hume_config_id not set');
      return;
    }

    // Prevent double initialization (React StrictMode calls effects twice)
    // Check if we already initialized this specific avatar
    if (lastInitializedAvatarId.current === avatar.ojin_persona_id) {
      console.log('[SessionWindow] Session already initialized for this avatar, skipping duplicate');
      return;
    }
    
    lastInitializedAvatarId.current = avatar.ojin_persona_id;
    console.log('[SessionWindow] Initializing bot session for', avatar.name, avatar.ojin_persona_id);
    
    // Initialize bot session
    initializeSession();

    // Cleanup on unmount
    return () => {
      console.log('[SessionWindow] Cleaning up on unmount for', avatar.name);
      // Don't reset lastInitializedAvatarId here - it prevents StrictMode double init
      // It will be overwritten when a different avatar is selected
      cleanupSession();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [avatar]);

  // Define cleanupSession and handleHangUp first (before useEffects that use them)
  const cleanupSession = useCallback(async () => {
    if (sessionRef.current) {
      console.log('Cleaning up session');
      const { ipcRenderer, handleBotMessage } = sessionRef.current;
      
      // Set status to show we're stopping
      setStatus('ended');
      
      // Remove listener first to stop receiving messages
      if (handleBotMessage) {
        ipcRenderer.removeListener('bot-message', handleBotMessage);
      }
      
      // Stop bot session
      try {
        console.log('Stopping bot session...');
        await ipcRenderer.invoke('stop-bot-session');
        console.log('Bot session stopped');
      } catch (err) {
        console.error('Error stopping bot session:', err);
      }
      
      sessionRef.current = null;
    }
  }, []);

  const handleHangUp = useCallback(async () => {
    await cleanupSession();
    onHangUp();
  }, [cleanupSession, onHangUp]);

  // Rotate through initialization messages
  useEffect(() => {
    if (status === 'initializing' && avatar.initialization_messages) {
      const messages = avatar.initialization_messages;
      const interval = setInterval(() => {
        setCurrentMessageIndex((prev) => (prev + 1) % messages.length);
      }, 3000); // Change message every 3 seconds

      return () => clearInterval(interval);
    }
  }, [status, avatar.initialization_messages]);

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = async (e) => {
      if (e.key === 'Escape' || (e.ctrlKey && e.key === 'h')) {
        e.preventDefault();
        await handleHangUp();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleHangUp]);

  const initializeSession = async () => {
    try {
      // Reset for new session
      firstVideoFrameReceived.current = false;
      personaInitialized.current = false;
      lastBotError.current = null;
      setHasVideo(false);
      
      console.log('Starting bot session for:', {
        name: avatar.name,
        personaId: avatar.ojin_persona_id,
        humeConfigId: avatar.hume_config_id,
      });

      // Start bot session via IPC
      const { ipcRenderer } = window.require('electron');
      const result = await ipcRenderer.invoke('start-bot-session', {
        personaId: avatar.ojin_persona_id,
        humeConfigId: avatar.hume_config_id,
        environment: avatar.environment || 'production', // Default to production if not specified
      });

      if (!result.success) {
        throw new Error(result.error || 'Failed to start bot session');
      }

      // Listen for bot messages
      const handleBotMessage = (event, message) => {
        console.log('Bot message received:', message.type);

        if (message.type === 'ready') {
          console.log('Bot ready');
        } else if (message.type === 'started') {
          console.log('Bot pipeline started, initializing persona...');
          // Already in 'initializing' status, no need to set again
        } else if (message.type === 'persona_initialized') {
          console.log('Persona initialized!');
          personaInitialized.current = true;
          setHasVideo(true);
          setStatus('active');
          setTranscript([
            { role: 'system', content: `Connected to ${avatar.name}` },
          ]);
        } else if (message.type === 'video_frame') {
          // Update video display first
          updateVideoFrame(message);          
        } else if (message.type === 'transcript') {
          // Update transcript
          setTranscript(prev => [...prev, message.data]);
        } else if (message.type === 'error') {
          console.error('Bot error:', message.message);
          lastBotError.current = message.message;
          setStatus('error');
          setError(message.message);
        } else if (message.type === 'ended') {
          console.log('Bot session ended with code:', message.code);
          // If ended with non-zero code, treat as error
          if (message.code && message.code !== 0) {
            setStatus('error');
            setError(lastBotError.current || 'Bot session ended unexpectedly. Check console for details.');
          } else {
            setStatus('ended');
          }
          // Note: Don't call cleanupSession here as it's already called by handleHangUp
        }
      };

      ipcRenderer.on('bot-message', handleBotMessage);
      sessionRef.current = { ipcRenderer, handleBotMessage };

    } catch (err) {
      console.error('Failed to initialize session:', err);
      setStatus('error');
      setError(err.message || 'Failed to start bot session');
    }
  };

  const updateVideoFrame = (frameData) => {
    if (videoRef.current) {
      try {
        // Create image element from base64 data
        const img = new Image();
        img.onload = () => {
          const canvas = videoRef.current;
          if (!canvas) return;
          
          // If canvas doesn't exist yet, create it
          let canvasEl = canvas.querySelector('canvas');
          if (!canvasEl) {
            canvasEl = document.createElement('canvas');
            canvasEl.width = frameData.width || 1280;
            canvasEl.height = frameData.height || 720;
            canvasEl.style.width = '100%';
            canvasEl.style.height = '100%';
            canvasEl.style.objectFit = 'cover'; // Fill window while maintaining aspect ratio
            canvas.innerHTML = '';
            canvas.appendChild(canvasEl);
          }
          
          const ctx = canvasEl.getContext('2d');
          ctx.drawImage(img, 0, 0, canvasEl.width, canvasEl.height);
        };
        img.src = `data:image/jpeg;base64,${frameData.data}`;
      } catch (err) {
        console.error('Error rendering video frame:', err);
      }
    }
  };

  const handleRetry = () => {
    setError(null);
    initializeSession();
  };

  // Initializing state with rotating messages
  if (status === 'initializing') {
    const messages = avatar.initialization_messages || ['Initializing...'];
    const currentMessage = messages[currentMessageIndex];

    return (
      <div className="fixed inset-0 bg-gradient-to-br from-gray-900 via-gray-800 to-black flex items-center justify-center z-50">
        <div className="text-center px-8">
          {/* Avatar Circle */}
          <div className="mb-8 flex justify-center">
            <div className="relative">
              <div className="w-32 h-32 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-2xl">
                <span className="text-5xl text-white font-bold">
                  {avatar.name.charAt(0).toUpperCase()}
                </span>
              </div>
              {/* Animated ring */}
              <div className="absolute inset-0 rounded-full border-4 border-blue-400 animate-ping opacity-75"></div>
              <div className="absolute inset-0 rounded-full border-4 border-purple-400 animate-pulse"></div>
            </div>
          </div>

          {/* Rotating Message with fade animation */}
          <div className="h-16 flex items-center justify-center mb-8">
            <p
              key={currentMessageIndex}
              className="text-2xl text-white font-medium animate-fade-in"
              style={{
                animation: 'fadeInOut 3s ease-in-out'
              }}
            >
              {currentMessage}
            </p>
          </div>

          {/* Modern loading animation */}
          <div className="flex justify-center gap-2 mb-4">
            <div className="w-3 h-3 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
            <div className="w-3 h-3 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
            <div className="w-3 h-3 bg-pink-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
          </div>

          {/* Progress bar */}
          <div className="w-64 mx-auto h-1 bg-gray-700 rounded-full overflow-hidden">
            <div className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 animate-progress"></div>
          </div>

          {/* ESC hint */}
          <p className="text-gray-400 text-sm mt-8">
            Press <kbd className="px-2 py-1 bg-gray-700 rounded text-gray-300 text-xs">ESC</kbd> to cancel
          </p>
        </div>

        {/* Add keyframes for animations */}
        <style>{`
          @keyframes fadeInOut {
            0% { opacity: 0; transform: translateY(10px); }
            10% { opacity: 1; transform: translateY(0); }
            90% { opacity: 1; transform: translateY(0); }
            100% { opacity: 0; transform: translateY(-10px); }
          }
          @keyframes progress {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(100%); }
          }
          .animate-progress {
            animation: progress 1.5s ease-in-out infinite;
          }
        `}</style>
      </div>
    );
  }

  // Error state
  if (status === 'error') {
    return (
      <div className="fixed inset-0 bg-black flex items-center justify-center z-50">
        <div className="bg-white rounded-lg p-8 max-w-md text-center">
          <div className="text-red-500 text-5xl mb-4">⚠️</div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Connection Error</h2>
          <p className="text-gray-600 mb-6">{error}</p>
          <div className="flex gap-4 justify-center">
            <button
              onClick={handleRetry}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Retry
            </button>
            <button
              onClick={onHangUp}
              className="px-6 py-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 transition-colors"
            >
              Back to Grid
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Fullscreen video view - simple and clean
  return (
    <div className="fixed inset-0 bg-black z-50">
      {/* Fullscreen video - fills window while maintaining aspect ratio */}
      <div ref={videoRef} className="w-full h-full" style={{ 
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}>
        <style>{`
          #root canvas {
            width: 100% !important;
            height: 100% !important;
            object-fit: cover;
          }
        `}</style>
      </div>

      {/* ESC hint */}
      <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 text-gray-400 text-sm">
        Press <kbd className="px-2 py-1 bg-gray-800 rounded text-gray-300 text-xs">ESC</kbd> to hang up
      </div>
    </div>
  );
}

export default SessionWindow;
