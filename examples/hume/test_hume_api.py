import asyncio
from hume import HumeVoiceClient
import os
from dotenv import load_dotenv

load_dotenv()

async def test():
    client = HumeVoiceClient(api_key=os.getenv("HUME_API_KEY"))
    socket = await client.connect(config_id=os.getenv("HUME_CONFIG_ID")).__aenter__()
    print("Socket type:", type(socket))
    print("Socket methods:", [m for m in dir(socket) if not m.startswith('_')])
    await socket.close()

asyncio.run(test())
