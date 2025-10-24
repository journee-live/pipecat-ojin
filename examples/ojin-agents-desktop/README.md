# Ojin Agents Desktop

A cross-platform desktop application for accessing virtual bot avatars powered by Ojin Oris technology.

## Features

- ✅ Cross-platform support (Windows & macOS)
- ✅ System tray integration with background running
- ✅ Modern React + TailwindCSS interface
- ✅ Categorized avatar grid display
- ✅ Configurable avatars via `config.json`

## Prerequisites

- Node.js (v18 or higher)
- npm or yarn
- Python 3.8+ with pip
- Pipecat and dependencies installed

## Quick Setup

**Option 1: Use setup scripts**

Windows:
```bash
setup.bat
```

macOS/Linux:
```bash
chmod +x setup.sh
./setup.sh
```

**Option 2: Use npm scripts**
```bash
npm run setup:all
```

These will automatically install Node.js and Python dependencies, and create your `.env` file.

## Manual Installation

1. Create Python virtual environment:
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

2. Install Node.js dependencies:
```bash
npm install
```

3. Install Python dependencies:

**Option A: For local development (recommended)**
```bash
pip install -r dev-requirements.txt
```

**Option B: Using published package**
```bash
pip install -r requirements.txt
```

The requirements include:
- `pipecat-ai[ojin,silero,hume]` - Pipecat with Ojin, Silero VAD, and Hume extensions
- `pyaudio` - Audio I/O
- `opencv-python` - Image processing
- `python-dotenv` - Environment variable loading
- Other dependencies

3. Configure environment variables:
```bash
cp .env.example .env
```

Edit `.env` and add your API keys:
- `OJIN_API_KEY`: Your Ojin API key
- `HUME_API_KEY`: Your Hume AI API key

4. Update `config.json` with your persona and Hume config IDs

## Development

Run the app in development mode:

```bash
npm run dev
```

This will:
- Start the Vite dev server on http://localhost:5173
- Launch Electron with hot reload enabled
- Open DevTools automatically

## Debugging

See **[DEBUGGING.md](./DEBUGGING.md)** for detailed debugging instructions.

**Quick Start**:
1. Open VSCode Run and Debug panel (`Ctrl+Shift+D`)
2. Select **"Debug Electron Main + Renderer"**
3. Press `F5`
4. Set breakpoints in any `.js`, `.jsx`, or `.py` files

**Debug configurations available**:
- Debug Electron Main + Renderer (full app)
- Debug Electron Main Process (IPC, process management)
- Debug Python Bot (Standalone) (bot logic only)
- Attach to Python Bot (attach to running bot)

## Available Scripts

- `npm run dev` - Start development mode (React + Electron)
- `npm run setup:python` - Install Python dependencies only
- `npm run setup:all` - Install both Node.js and Python dependencies
- `npm run test:bot` - Test bot script directly (outputs JSON messages)
- `npm run build` - Build React app for production
- `npm run build:win` - Build Windows installer
- `npm run build:mac` - Build macOS installer
- `npm run build:all` - Build for all platforms

## Building

### Build for Windows:
```bash
npm run build:win
```

### Build for macOS:
```bash
npm run build:mac
```

### Build for both platforms:
```bash
npm run build:all
```

Built installers will be in the `dist-installer` directory.

## Configuration

Edit `config.json` to customize avatars:

```json
{
  "version": "1.0.0",
  "main_tags": ["Category 1", "Category 2"],
  "avatars": [
    {
      "id": "unique_id",
      "name": "Avatar Name",
      "description": "Description text",
      "image": "path/to/image.jpg",
      "tags": ["Category 1"],
      "ojin_persona_id": "persona_id_from_ojin",
      "hume_config_id": "hume_config_id_from_hume"
    }
  ]
}
```

## Project Structure

```
ojin-agents-desktop/
├── electron/           # Electron main process
│   └── main.js
├── src/               # React application
│   ├── components/
│   │   ├── AvatarCard.jsx
│   │   └── AvatarGrid.jsx
│   ├── App.jsx
│   ├── main.jsx
│   └── index.css
├── build/             # App icons
├── config.json        # Avatar configuration
├── package.json
└── vite.config.js
```

## System Tray

The app minimizes to the system tray instead of closing. Right-click the tray icon to:
- Show the app window
- Quit the application

## Tech Stack

- **Electron**: Desktop framework
- **React**: UI library
- **Vite**: Build tool
- **TailwindCSS**: Styling
- **electron-builder**: Packaging and distribution

## Notes

- Avatar images should be placed in a `public` folder or use absolute URLs
- The app prevents multiple instances from running
- DevTools are enabled in development mode only

## Usage

1. Start the app with `npm run dev`
2. Click on any avatar card to start a session
3. The bot session window opens fullscreen
4. Python bot process starts automatically
5. Video stream appears when connected
6. Speak to interact with the bot
7. Click "Hang Up" or press `Esc` to end the session

## Bot Architecture

- **Python Backend** (`bot.py`): Pipecat pipeline with Hume LLM and Ojin video
- **Electron IPC**: Spawns Python process and bridges video/audio data
- **Video Rendering**: Base64 JPEG frames sent via stdout → Canvas display
- **Audio**: LocalAudioTransport handles microphone input and speaker output

## Troubleshooting

### "Failed to start bot session"
- Verify Python is in your PATH
- Check `.env` file has valid API keys
- Look for Python errors in the Electron console

### "ModuleNotFoundError"
- Make sure you ran `pip install -r dev-requirements.txt` or `npm run setup:python`
- Check that all dependencies installed successfully
- Try reinstalling: `pip install -r dev-requirements.txt --force-reinstall`
- Test the bot directly: `npm run test:bot` (should output JSON messages)

### PyAudio installation issues (Windows)
If PyAudio fails to install:
```bash
# Option 1: Use pipwin
pip install pipwin
pipwin install pyaudio

# Option 2: Download wheel from https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
pip install PyAudio-0.2.14-cp311-cp311-win_amd64.whl
```

### No video stream
- Ensure `ojin_persona_id` and `hume_config_id` are correct in `config.json`
- Check bot stderr logs for connection errors
- Verify API keys are valid and have correct permissions

### Audio issues
- Check system microphone permissions
- Ensure microphone is not used by another app
- Verify audio device is working
