# Debugging Guide

## Overview

The app has three main components you can debug:
1. **Electron Main Process** (Node.js) - Spawns Python bot, handles IPC
2. **React Renderer** (Browser) - UI, session window, avatar grid
3. **Python Bot** (Python) - Pipecat pipeline, Ojin/Hume services

## Quick Start

### Debug the Entire App

1. In VSCode, open the Run and Debug panel (`Ctrl+Shift+D`)
2. Select **"Debug Electron Main + Renderer"**
3. Press `F5` or click the green play button
4. Set breakpoints in any JavaScript/TypeScript files
5. The app will start and pause at your breakpoints

### Debug Python Bot Only

1. Select **"Debug Python Bot (Standalone)"** from the debug dropdown
2. Press `F5`
3. Set breakpoints in `bot.py` or pipecat files
4. Bot will run standalone (not launched by Electron)
5. You'll see console output and can step through the code

## Debug Configurations

### 1. Debug Electron Main + Renderer
**What**: Full app with Electron and React
**Use when**: Testing avatar selection, session flow, UI interactions
**Breakpoints**: Set in `electron/main.js`, `src/**/*.jsx`

**Steps**:
1. Select this config
2. Press `F5`
3. App launches with debugger attached
4. All console logs appear in Debug Console

### 2. Debug Electron Main Process
**What**: Just the Electron main process
**Use when**: Debugging IPC, bot spawning, process management
**Breakpoints**: Set in `electron/main.js`

**Note**: You need to start Vite dev server separately:
```bash
npm run dev:react
```

### 3. Debug Python Bot (Standalone)
**What**: Python bot without Electron
**Use when**: Testing bot logic, Ojin/Hume connections, pipeline issues
**Breakpoints**: Set in `bot.py`, any pipecat files

**Steps**:
1. Install Python debugger: `pip install debugpy`
2. Select this config
3. Update args in launch.json with your persona/hume IDs
4. Press `F5`
5. Bot runs standalone, outputs JSON to console

**Current args** (edit in `.vscode/launch.json`):
```json
"args": [
  "3c8684f8-abca-4785-94e5-275b1e7bd722",  // persona_id
  "8f0125a9-bfea-4fa5-86f4-6899925bfdbe"   // hume_config_id
]
```

### 4. Attach to Python Bot
**What**: Attach debugger to running Python process
**Use when**: Bot is already running from Electron, you want to debug it

**Setup**:
1. Add to `bot.py` at the top:
```python
import debugpy
debugpy.listen(("localhost", 5678))
print("Waiting for debugger to attach...")
debugpy.wait_for_client()
```

2. Start app normally: `npm run dev`
3. Click an avatar to start bot
4. In VSCode, select **"Attach to Python Bot"**
5. Press `F5`
6. Debugger attaches, breakpoints work

## Debugging Scenarios

### Scenario 1: Avatar Click Not Working
**Debug**: Electron Main + Renderer
**Breakpoints**:
- `src/components/AvatarCard.jsx:5` (handleClick)
- `src/App.jsx:50` (handleAvatarSelect)
- `electron/main.js:159` (start-bot-session IPC handler)

### Scenario 2: Bot Not Starting / 403 Error
**Debug**: Python Bot (Standalone)
**Check**:
- `.env` file has correct API keys
- Persona ID and Hume Config ID are valid
- `OJIN_PROXY_URL` is correct
- `OJIN_MODE=dev` is set if needed

**Breakpoints**:
- `bot.py:90` (main function start)
- `bot.py:125` (Ojin URL construction)
- `bot.py:134` (OjinPersonaService creation)

### Scenario 3: No Video Frames Appearing
**Debug**: Python Bot + React Renderer
**Breakpoints**:
- `bot.py:44` (ElectronIPCOutput.process_frame)
- `electron/main.js:111` (bot stdout handler)
- `src/components/SessionWindow.jsx:117` (updateVideoFrame)

**Check**:
- Console logs for "Bot message: video_frame"
- Video data is base64 encoded
- Canvas element exists in SessionWindow

### Scenario 4: Audio Not Working
**Debug**: Python Bot (Standalone)
**Check**:
- PyAudio installed: `pip list | findstr pyaudio`
- Microphone permissions granted
- Audio device working in system

**Breakpoints**:
- `bot.py:96` (LocalAudioTransport creation)

## Logging and Console Output

### Electron Main Process
- **Location**: VSCode Debug Console (when debugging)
- **Location**: Terminal where you ran `npm run dev`
- **Key logs**: "Starting bot session...", "Bot message: ..."

### Python Bot
- **Location**: Electron console (stderr)
- **Location**: VSCode Debug Console (when debugging bot standalone)
- **Key logs**: Pipecat pipeline logs, Ojin connection logs

### React Renderer
- **Location**: Electron DevTools Console (auto-opens in dev mode)
- **Location**: View > Toggle Developer Tools
- **Key logs**: "Starting bot session for:", "Bot message received:"

## Tips

1. **Use `debugger;` statement** in JavaScript files to force breakpoint
2. **Use `logger.debug()` in Python** to add temporary logs
3. **Check all three consoles** when debugging (VSCode, Electron DevTools, Terminal)
4. **Test bot independently first** before debugging full app
5. **Environment variables** are read from `.env` - verify they're loaded
6. **Suppress video spam**: Video frames are automatically suppressed in debug mode to keep logs clean

### Suppressing Video Frame Logs

When debugging the Python bot standalone, video frames (base64 images) can flood your console. This is now **automatically suppressed** in the debug configuration.

If you want to see video frames in logs:
- Set `SUPPRESS_VIDEO_LOGS=false` in `.env`
- Or remove the env var from `.vscode/launch.json`

When running via Electron (`npm run dev`), video frames are always sent (not suppressed) because they need to reach the UI.

## Common Issues

### "Cannot find module 'debugpy'"
```bash
pip install debugpy
```

### Breakpoints Not Hitting
- Make sure you selected the right debug configuration
- Check file paths are correct
- Restart debugger

### Environment Variables Not Loading
- `.env` file must be in project root
- python-dotenv must be installed
- Check `.env` has no syntax errors

## Testing Workflow

1. **Test bot standalone**: Debug Python Bot (Standalone)
   - Verifies bot can connect to Ojin/Hume
   - No Electron complexity
   
2. **Test full app**: Debug Electron Main + Renderer
   - Verifies IPC communication
   - Tests full integration

3. **Fix issues**: Set breakpoints, step through, check variables

4. **Verify**: Run without debugger: `npm run dev`

## Advanced: Remote Debugging

If you need to debug the bot while it's running in production or on another machine:

1. Install debugpy on target machine
2. Add to bot.py:
```python
debugpy.listen(("0.0.0.0", 5678))
```
3. In launch.json, update host to target IP
4. Open firewall port 5678
5. Attach debugger

## Need Help?

Current issue you're seeing (HTTP 403):
- **Cause**: Ojin server rejecting connection
- **Check**: API key is valid for the persona ID
- **Check**: OJIN_MODE matches server configuration
- **Check**: Account has access to this persona

Set a breakpoint at `bot.py:125` and inspect `ojin_ws_url` to see the exact URL being used.
