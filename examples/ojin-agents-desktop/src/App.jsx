import React, { useState, useEffect } from 'react';
import AvatarGrid from './components/AvatarGrid';
import SessionWindow from './components/SessionWindow';

function App() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeSession, setActiveSession] = useState(null);
  const [environment, setEnvironment] = useState(null); // 'production' or 'staging'

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
      <div className="h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-gray-300 border-t-blue-500 rounded-full animate-spin mx-auto mb-4"></div>
          <div className="text-gray-600">Loading...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center p-4">
          <div className="text-red-500 text-5xl mb-4">⚠️</div>
          <div className="text-xl text-gray-900 font-semibold mb-2">Error</div>
          <div className="text-gray-600">{error}</div>
        </div>
      </div>
    );
  }

  const handleAvatarSelect = (avatar) => {
    // Add environment to avatar object
    const avatarWithEnv = {
      ...avatar,
      ojin_persona_id: environment === 'production' 
        ? avatar.ojin_persona_id_production 
        : avatar.ojin_persona_id_staging,
      environment: environment
    };
    setActiveSession(avatarWithEnv);
  };

  const handleHangUp = () => {
    setActiveSession(null);
  };

  // Show session window if there's an active session
  if (activeSession) {
    return <SessionWindow avatar={activeSession} onHangUp={handleHangUp} />;
  }

  // Show environment selection screen if not selected yet
  if (!environment) {
    return (
      <div className="h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-black flex items-center justify-center">
        <div className="text-center px-8 max-w-md">
          <div className="mb-8">
            <h1 className="text-4xl font-bold text-white mb-2">Ojin Agents Desktop</h1>
            <p className="text-gray-400">Select your environment</p>
          </div>

          <div className="space-y-4">
            <button
              onClick={() => setEnvironment('production')}
              className="w-full px-8 py-4 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-xl hover:from-blue-500 hover:to-blue-600 transition-all duration-200 font-semibold text-lg shadow-xl hover:shadow-2xl transform hover:scale-105"
            >
              🚀 Production
            </button>
            
            <button
              onClick={() => setEnvironment('staging')}
              className="w-full px-8 py-4 bg-gradient-to-r from-purple-600 to-purple-700 text-white rounded-xl hover:from-purple-500 hover:to-purple-600 transition-all duration-200 font-semibold text-lg shadow-xl hover:shadow-2xl transform hover:scale-105"
            >
              🔧 Staging
            </button>
          </div>

          <p className="text-gray-500 text-sm mt-6">
            This selection determines which API endpoints and personas to use
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      {/* Environment indicator */}
      <div className="bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`inline-block w-2 h-2 rounded-full ${environment === 'production' ? 'bg-blue-500' : 'bg-purple-500'}`}></span>
          <span className="text-sm font-medium text-gray-700">
            {environment === 'production' ? '🚀 Production' : '🔧 Staging'}
          </span>
        </div>
        <button
          onClick={() => setEnvironment(null)}
          className="text-sm text-gray-600 hover:text-gray-900"
        >
          Switch Environment
        </button>
      </div>
      
      <main className="flex-1 overflow-auto px-3 py-3">
        <AvatarGrid config={config} onAvatarSelect={handleAvatarSelect} />
      </main>
    </div>
  );
}

export default App;
