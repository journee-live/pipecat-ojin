import React, { useState, useEffect, useRef } from 'react';

function SessionWindow({ avatar, onHangUp }) {
  const [status, setStatus] = useState('connecting'); // connecting, active, error
  const [error, setError] = useState(null);
  const [transcript, setTranscript] = useState([]);
  const videoRef = useRef(null);
  const sessionRef = useRef(null);

  useEffect(() => {
    // Validate configuration
    if (!avatar.ojin_persona_id || !avatar.hume_config_id) {
      setStatus('error');
      setError('Configuration missing: ojin_persona_id or hume_config_id not set');
      return;
    }

    // Initialize bot session
    initializeSession();

    // Cleanup on unmount
    return () => {
      cleanupSession();
    };
  }, [avatar]);

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' || (e.ctrlKey && e.key === 'h')) {
        e.preventDefault();
        handleHangUp();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const initializeSession = async () => {
    try {
      setStatus('connecting');
      
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
          setStatus('active');
          setTranscript([
            { role: 'system', content: `Connected to ${avatar.name}` },
          ]);
        } else if (message.type === 'video_frame') {
          // Update video display
          updateVideoFrame(message);
        } else if (message.type === 'transcript') {
          // Update transcript
          setTranscript(prev => [...prev, message.data]);
        } else if (message.type === 'error') {
          setStatus('error');
          setError(message.message);
        } else if (message.type === 'ended') {
          console.log('Bot session ended');
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

  const cleanupSession = async () => {
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
            canvasEl.style.objectFit = 'contain';
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

  const handleHangUp = () => {
    cleanupSession();
    onHangUp();
  };

  const handleRetry = () => {
    setError(null);
    initializeSession();
  };

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

  // Main session UI
  return (
    <div className="fixed inset-0 bg-black z-50 flex flex-col">
      {/* Header */}
      <div className="bg-gray-900 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-full bg-gray-700 flex items-center justify-center">
            <span className="text-xl text-white font-semibold">
              {avatar.name.charAt(0).toUpperCase()}
            </span>
          </div>
          <div>
            <h2 className="text-white text-lg font-semibold">{avatar.name}</h2>
            <div className="flex items-center gap-2">
              {status === 'connecting' && (
                <>
                  <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></div>
                  <span className="text-yellow-500 text-sm">Connecting...</span>
                </>
              )}
              {status === 'active' && (
                <>
                  <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                  <span className="text-green-500 text-sm">Active</span>
                </>
              )}
            </div>
          </div>
        </div>

        <button
          onClick={handleHangUp}
          className="px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors font-medium"
        >
          Hang Up
        </button>
      </div>

      {/* Video/Avatar Area */}
      <div className="flex-1 bg-gradient-to-br from-gray-900 to-gray-800 flex items-center justify-center relative">
        <div ref={videoRef} className="w-full h-full flex items-center justify-center">
          {/* Video stream will be rendered here */}
          <div className="text-gray-500 text-center">
            <div className="text-6xl mb-4">🎥</div>
            <p className="text-xl">Video stream will appear here</p>
            <p className="text-sm mt-2">Persona ID: {avatar.ojin_persona_id}</p>
            <p className="text-sm">Hume Config: {avatar.hume_config_id || 'Not set'}</p>
          </div>
        </div>

        {/* Mic indicator */}
        <div className="absolute bottom-8 left-1/2 transform -translate-x-1/2 bg-gray-800 bg-opacity-75 px-4 py-2 rounded-full flex items-center gap-2">
          <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
          <span className="text-white text-sm">Microphone Active</span>
        </div>
      </div>

      {/* Transcript Area */}
      <div className="bg-gray-900 border-t border-gray-700 h-48 overflow-y-auto p-4">
        <div className="max-w-4xl mx-auto space-y-2">
          {transcript.length === 0 ? (
            <p className="text-gray-500 text-center">Conversation transcript will appear here...</p>
          ) : (
            transcript.map((message, idx) => (
              <div
                key={idx}
                className={`text-sm ${
                  message.role === 'user'
                    ? 'text-blue-400'
                    : message.role === 'assistant'
                    ? 'text-green-400'
                    : 'text-gray-400'
                }`}
              >
                <span className="font-semibold">{message.role}: </span>
                {message.content}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Keyboard hint */}
      <div className="absolute top-20 right-6 text-gray-400 text-xs">
        Press <kbd className="px-2 py-1 bg-gray-700 rounded">Esc</kbd> or{' '}
        <kbd className="px-2 py-1 bg-gray-700 rounded">Ctrl+H</kbd> to hang up
      </div>
    </div>
  );
}

export default SessionWindow;
