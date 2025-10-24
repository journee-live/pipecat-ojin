import React, { useState, useEffect } from 'react';
import AvatarGrid from './components/AvatarGrid';
import SessionWindow from './components/SessionWindow';

function App() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeSession, setActiveSession] = useState(null);

  useEffect(() => {
    // Load config.json
    fetch('./config.json')
      .then((response) => {
        if (!response.ok) {
          throw new Error('Failed to load config.json');
        }
        return response.json();
      })
      .then((data) => {
        setConfig(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="text-xl text-gray-600">Loading...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="text-xl text-red-600">Error: {error}</div>
        </div>
      </div>
    );
  }

  const handleAvatarSelect = (avatar) => {
    setActiveSession(avatar);
  };

  const handleHangUp = () => {
    setActiveSession(null);
  };

  // Show session window if there's an active session
  if (activeSession) {
    return <SessionWindow avatar={activeSession} onHangUp={handleHangUp} />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <h1 className="text-2xl font-bold text-gray-900">Ojin Agents Desktop</h1>
          <p className="text-sm text-gray-500 mt-1">Select a virtual bot to interact with</p>
        </div>
      </header>
      
      <main className="max-w-7xl mx-auto px-6 py-8">
        <AvatarGrid config={config} onAvatarSelect={handleAvatarSelect} />
      </main>
    </div>
  );
}

export default App;
