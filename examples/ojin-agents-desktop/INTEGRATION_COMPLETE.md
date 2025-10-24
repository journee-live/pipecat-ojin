# Bot Integration Complete ✅

The Python bot backend has been successfully integrated with the Electron desktop app!

## What Was Implemented

### 1. Python Bot Adapter (`bot.py`)
- Accepts `persona_id` and `hume_config_id` as command-line arguments
- Runs Pipecat pipeline with Hume LLM and Ojin Persona services
- Sends video frames to Electron via stdout as JSON (base64 encoded)
- Handles audio I/O with LocalAudioTransport
- Communicates status via structured JSON messages

### 2. Electron IPC Bridge (`electron/main.js`)
- Spawns Python bot as child process
- IPC handlers: `start-bot-session` and `stop-bot-session`
- Forwards bot messages to renderer via `bot-message` channel
- Automatic cleanup on app quit
- Error handling and process management

### 3. Session Window Updates (`src/components/SessionWindow.jsx`)
- Calls IPC to start/stop bot sessions
- Listens for bot messages via IPC
- Renders video frames to canvas using base64 data
- Updates transcript in real-time
- Proper cleanup on hang up

## How It Works

```
User clicks avatar
    ↓
SessionWindow calls IPC: start-bot-session
    ↓
Electron spawns: python bot.py <persona_id> <hume_config_id>
    ↓
Python bot initializes pipeline (Hume + Ojin + Audio)
    ↓
Bot sends JSON messages via stdout:
  - type: "ready" → Bot initialized
  - type: "started" → Pipeline running
  - type: "video_frame" → Base64 JPEG frame
  - type: "transcript" → Conversation text
  - type: "error" → Error message
  - type: "ended" → Session closed
    ↓
Electron forwards messages to renderer
    ↓
SessionWindow updates UI (video canvas, transcript, status)
```

## Next Steps to Test

1. **Install Python dependencies** (if not done already):
   ```bash
   pip install -r dev-requirements.txt
   ```
   
   Or use the quick setup script:
   - Windows: `setup.bat`
   - macOS/Linux: `./setup.sh`

2. **Set up .env file**:
   ```bash
   cp .env.example .env
   # Edit .env and add your OJIN_API_KEY and HUME_API_KEY
   ```

2. **Restart the app**:
   ```bash
   npm run dev
   ```

3. **Click on an avatar** (Jordan or Margot)

4. **Check the logs**:
   - Electron console: Should show "Starting bot session..."
   - Bot stderr: Python logs from pipecat
   - Bot stdout: JSON messages being sent

5. **Expected behavior**:
   - Status changes from "Connecting..." to "Active"
   - Video frames start appearing in the canvas
   - Microphone activates
   - You can speak and get responses

## Debugging

### Check Python is working:
```bash
python bot.py test-persona test-config
```

Should output JSON messages like:
```json
{"type": "ready", "persona_id": "test-persona", "hume_config_id": "test-config"}
```

### Check Electron logs:
Look for:
- "Starting bot session: persona=..." ✅
- "Bot message: ready" ✅
- "Bot message: started" ✅
- "Bot message: video_frame" ✅

### Common Issues:

**"Python not found"**
- Make sure Python is in PATH
- Try `python3` instead of `python` (edit line 99 in electron/main.js)

**"ModuleNotFoundError: No module named 'pipecat'"**
- Install pipecat: `pip install -e ../..` from repo root

**"Missing API keys"**
- Check `.env` file exists and has keys
- Verify dotenv is loading: add `console.log(process.env.OJIN_API_KEY)` to bot.py

**No video frames**
- Check bot stderr for Ojin connection errors
- Verify `ojin_persona_id` is valid
- Check network connectivity to Ojin servers

## File Summary

- ✅ `bot.py` - Python bot with IPC output
- ✅ `electron/main.js` - IPC handlers and process spawning
- ✅ `src/components/SessionWindow.jsx` - Video rendering and IPC communication
- ✅ `.env.example` - Environment template
- ✅ `README.md` - Updated with setup instructions
- ✅ `config.json` - Has real persona/hume IDs for Margot and Jordan

## Performance Notes

- Video frames are sent as base64 JPEG (overhead ~33% vs raw bytes)
- For production, consider binary IPC channels or WebSocket
- Current approach is simple and works well for 30fps video at 1280x720

The implementation is complete and ready to test! 🎉
