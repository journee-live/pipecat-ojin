import asyncio
import os
from dotenv import load_dotenv
from hume import HumeVoiceClient

load_dotenv()

async def test():
    client = HumeVoiceClient(api_key=os.getenv("HUME_API_KEY"))
    socket = await client.connect(config_id=os.getenv("HUME_CONFIG_ID")).__aenter__()
    
    print("Waiting for messages...")
    count = 0
    async for message in socket:
        print(f"\nMessage {count}:")
        print(f"  Type: {type(message)}")
        print(f"  Value: {message}")
        if hasattr(message, '__dict__'):
            print(f"  Attributes: {message.__dict__}")
        count += 1
        if count >= 3:
            break
    
    await socket.close()

asyncio.run(test())
