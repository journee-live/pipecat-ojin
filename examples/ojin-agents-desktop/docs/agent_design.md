# Agent Selection Flow — Desktop App

## Overview
When a user selects an agent, open a fullscreen window that runs a voice/chat bot using the persona defined in `config.json`. Provide a visible “Hang Up” control to end the session and return to the avatar grid.

## Requirements
- Fullscreen session window opens on agent selection.
- Bot behavior mirrors `examples/ojin-chatbot/bot.py` but uses `persona_id` from `config.json`.
- Prominent “Hang Up” button.
- On hang up: immediately terminate the session and return to the avatar grid.
- Handle unexpected disconnects and show a retry or back-to-grid option.

## Configuration
- `config.json` must include for each avatar:
  - `ojin_persona_id` (string): Persona used for the session.
  - `hume_config_id` (string): Hume configuration identifier used by the session.
  - Any additional transport/LLM/TTS settings required by the bot runtime.

## Flow
1. User selects an agent from the avatar grid.
2. App reads `ojin_persona_id` and `hume_config_id` from `config.json`.
3. Launch bot session in a fullscreen window.
4. User interacts with the agent.
5. User taps “Hang Up” or session ends.
6. Clean up session resources and return to avatar grid.

## UI
- Fullscreen modal/page with:
  - Agent header (name/avatar).
  - Conversation area (transcript).
  - Mic indicator / call status.
  - “Hang Up” button (primary, bottom or top-right).
- Keyboard shortcut: Esc or Ctrl+H to hang up.

## Error Handling
- If bot fails to start: show error with “Retry” and “Back to Grid.”
- If mid-session error: show notice and auto-return to grid after cleanup.
- If `ojin_persona_id` or `hume_config_id` is missing: show configuration error with “Back to Grid.”

## Implementation Notes
- Reuse logic from `examples/ojin-chatbot/bot.py` where possible.
- Abstract persona selection to a single function that reads from `config.json`.
- Ensure proper teardown of media streams and sockets on hang up.

## Open Questions
- Should we show a pre-join device check?
- Do we persist transcripts per session?