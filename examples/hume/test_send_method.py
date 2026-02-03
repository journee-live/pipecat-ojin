import asyncio
import inspect
from hume import HumeVoiceClient
from hume._voice.voice_socket import VoiceSocket

# Check send method signature
print("VoiceSocket.send signature:")
print(inspect.signature(VoiceSocket.send))
print("\nVoiceSocket.send docstring:")
print(VoiceSocket.send.__doc__)
