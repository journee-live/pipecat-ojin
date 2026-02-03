"""Minimal test of Hume 0.7.0 SDK to verify audio sending works."""

import asyncio
import os
import wave

from dotenv import load_dotenv
from hume import HumeVoiceClient

load_dotenv()


async def main():
    print("=" * 60)
    print("MINIMAL HUME 0.7.0 SDK TEST")
    print("=" * 60)

    # Read WAV file
    wav_path = "short.wav"
    print(f"\n📂 Reading: {wav_path}")
    with wave.open(wav_path, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        num_channels = wav_file.getnchannels()
        audio_data = wav_file.readframes(wav_file.getnframes())
    
    print(f"🎵 Audio: {sample_rate}Hz, {num_channels} ch, {len(audio_data)} bytes")

    # Connect to Hume
    print("\n🔌 Connecting to Hume EVI...")
    client = HumeVoiceClient(api_key=os.getenv("HUME_API_KEY"))
    
    try:
        async with client.connect(config_id=os.getenv("HUME_CONFIG_ID")) as socket:
            print("✅ Connected!")
            print(f"Socket type: {type(socket)}")
            print(f"Socket methods: {[m for m in dir(socket) if not m.startswith('_')][:10]}")
            
            # Start receiving messages
            async def receive_messages():
                count = 0
                async for message in socket:
                    print(f"\n📨 Message {count}: {type(message)}")
                    if isinstance(message, str):
                        print(f"   Content (first 200 chars): {message[:200]}")
                    count += 1
                    if count >= 5:
                        break
            
            receive_task = asyncio.create_task(receive_messages())
            
            # Wait a moment
            await asyncio.sleep(1)
            
            # Try sending audio in chunks
            print("\n🎤 Sending audio...")
            chunk_size = 4800  # 100ms at 48kHz
            chunks_sent = 0
            
            for i in range(0, min(len(audio_data), 48000), chunk_size):  # Send first 1 second
                chunk = audio_data[i:i + chunk_size]
                try:
                    await socket.send(chunk)
                    chunks_sent += 1
                    if chunks_sent % 5 == 0:
                        print(f"   Sent {chunks_sent} chunks...")
                except Exception as e:
                    print(f"❌ Error sending chunk {chunks_sent}: {e}")
                    break
                await asyncio.sleep(0.01)
            
            print(f"✅ Sent {chunks_sent} audio chunks")
            
            # Wait for responses
            print("\n⏳ Waiting for responses...")
            await asyncio.sleep(5)
            
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass
                
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
