import asyncio
import os
from dotenv import load_dotenv
from hume import HumeVoiceClient

load_dotenv()

async def test():
    client = HumeVoiceClient(api_key=os.getenv("HUME_API_KEY"))
    socket = await client.connect(config_id=os.getenv("HUME_CONFIG_ID")).__aenter__()
    
    print("Connected, waiting for initial messages...")
    
    # Wait for initial metadata
    async def receive_messages():
        try:
            async for message in socket:
                print(f"Received: {message[:200] if isinstance(message, (str, bytes)) else message}")
        except Exception as e:
            print(f"Receive error: {e}")
    
    # Start receiving in background
    receive_task = asyncio.create_task(receive_messages())
    
    await asyncio.sleep(2)
    
    # Try sending some audio (silence)
    print("Sending audio...")
    silence = b'\x00' * 1600  # 100ms of silence at 16kHz
    try:
        await socket.send(silence)
        print("Audio sent successfully")
    except Exception as e:
        print(f"Send error: {e}")
    
    await asyncio.sleep(3)
    
    receive_task.cancel()
    await socket.close()

asyncio.run(test())
