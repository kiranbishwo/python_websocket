import asyncio
import json
import websockets
import random
from datetime import datetime

async def connect_to_server(user_id: str):
    """Connect to WebSocket server and handle messages"""
    uri = "ws://localhost:8765"
    
    async with websockets.connect(uri) as websocket:
        # Send authentication message
        auth_message = {
            "user_id": user_id
        }
        await websocket.send(json.dumps(auth_message))
        
        # Join a room
        join_command = {
            "type": "command",
            "command": "join",
            "room": "test_room"
        }
        await websocket.send(json.dumps(join_command))
        
        # Send a chat message
        chat_message = {
            "type": "chat",
            "content": f"Hello from {user_id}!"
        }
        await websocket.send(json.dumps(chat_message))
        
        # Listen for messages
        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)
                print(f"\nReceived message: {data}")
                
            except websockets.exceptions.ConnectionClosed:
                print("Connection closed")
                break

async def main():
    """Run multiple test clients"""
    # Create multiple clients
    clients = [f"user_{i}" for i in range(3)]
    await asyncio.gather(*(connect_to_server(client) for client in clients))

if __name__ == "__main__":
    asyncio.run(main())