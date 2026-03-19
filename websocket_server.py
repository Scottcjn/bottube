import asyncio
import websockets
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Set, Optional
import jwt
import redis
from dataclasses import dataclass, asdict
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ChatMessage:
    id: str
    user_id: str
    username: str
    message: str
    timestamp: str
    message_type: str = "chat"
    super_chat_amount: Optional[float] = None
    rtc_amount: Optional[float] = None

@dataclass
class PremiereInfo:
    premiere_id: str
    title: str
    scheduled_time: str
    current_viewers: int
    status: str

class WebSocketServer:
    def __init__(self, host="localhost", port=8765, redis_url="redis://localhost:6379"):
        self.host = host
        self.port = port
        self.clients: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.room_clients: Dict[str, Set[str]] = {}
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.jwt_secret = "your-jwt-secret-key"
        
    async def register_client(self, websocket, client_id: str, room_id: str):
        """Register a new WebSocket client"""
        self.clients[client_id] = websocket
        
        if room_id not in self.room_clients:
            self.room_clients[room_id] = set()
        self.room_clients[room_id].add(client_id)
        
        logger.info(f"Client {client_id} joined room {room_id}")
        
        # Send current room info
        await self.send_room_info(client_id, room_id)

    async def unregister_client(self, client_id: str, room_id: str):
        """Unregister a WebSocket client"""
        if client_id in self.clients:
            del self.clients[client_id]
            
        if room_id in self.room_clients:
            self.room_clients[room_id].discard(client_id)
            if not self.room_clients[room_id]:
                del self.room_clients[room_id]
                
        logger.info(f"Client {client_id} left room {room_id}")

    async def send_to_client(self, client_id: str, message: dict):
        """Send message to specific client"""
        if client_id in self.clients:
            try:
                await self.clients[client_id].send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"Client {client_id} connection closed")
                await self.cleanup_client(client_id)

    async def broadcast_to_room(self, room_id: str, message: dict, exclude_client: Optional[str] = None):
        """Broadcast message to all clients in a room"""
        if room_id not in self.room_clients:
            return
            
        disconnected_clients = []
        
        for client_id in self.room_clients[room_id]:
            if client_id == exclude_client:
                continue
                
            try:
                await self.send_to_client(client_id, message)
            except Exception as e:
                logger.error(f"Error sending to client {client_id}: {e}")
                disconnected_clients.append(client_id)
        
        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.cleanup_client(client_id)

    async def cleanup_client(self, client_id: str):
        """Clean up disconnected client"""
        if client_id in self.clients:
            del self.clients[client_id]
            
        for room_id in list(self.room_clients.keys()):
            if client_id in self.room_clients[room_id]:
                self.room_clients[room_id].remove(client_id)
                if not self.room_clients[room_id]:
                    del self.room_clients[room_id]

    async def handle_chat_message(self, client_id: str, room_id: str, data: dict):
        """Handle incoming chat message"""
        try:
            message = ChatMessage(
                id=str(uuid.uuid4()),
                user_id=data.get("user_id"),
                username=data.get("username"),
                message=data.get("message"),
                timestamp=datetime.utcnow().isoformat(),
                message_type=data.get("message_type", "chat"),
                super_chat_amount=data.get("super_chat_amount"),
                rtc_amount=data.get("rtc_amount")
            )
            
            # Store message in Redis for persistence
            await self.store_chat_message(room_id, message)
            
            # Handle super chat with RTC
            if message.super_chat_amount and message.rtc_amount:
                await self.process_super_chat(message, room_id)
            
            # Broadcast to room
            response = {
                "type": "chat_message",
                "data": asdict(message)
            }
            
            await self.broadcast_to_room(room_id, response, exclude_client=client_id)
            
            # Send confirmation to sender
            await self.send_to_client(client_id, {
                "type": "message_sent",
                "data": {"message_id": message.id}
            })
            
        except Exception as e:
            logger.error(f"Error handling chat message: {e}")
            await self.send_to_client(client_id, {
                "type": "error",
                "data": {"message": "Failed to send message"}
            })

    async def store_chat_message(self, room_id: str, message: ChatMessage):
        """Store chat message in Redis"""
        try:
            key = f"chat:{room_id}"
            await asyncio.to_thread(
                self.redis.lpush,
                key,
                json.dumps(asdict(message))
            )
            # Keep only last 1000 messages
            await asyncio.to_thread(self.redis.ltrim, key, 0, 999)
        except Exception as e:
            logger.error(f"Error storing chat message: {e}")

    async def get_chat_history(self, room_id: str, limit: int = 50):
        """Get chat history from Redis"""
        try:
            key = f"chat:{room_id}"
            messages = await asyncio.to_thread(
                self.redis.lrange,
                key,
                0,
                limit - 1
            )
            return [json.loads(msg) for msg in reversed(messages)]
        except Exception as e:
            logger.error(f"Error getting chat history: {e}")
            return []

    async def process_super_chat(self, message: ChatMessage, room_id: str):
        """Process super chat with RTC integration"""
        try:
            # Here you would integrate with your RTC payment system
            # This is a placeholder for the actual RTC transaction
            
            # Highlight super chat message
            super_chat_data = {
                "type": "super_chat",
                "data": {
                    "message": asdict(message),
                    "highlight_duration": min(message.super_chat_amount * 10, 300)  # Max 5 minutes
                }
            }
            
            await self.broadcast_to_room(room_id, super_chat_data)
            
            # Store super chat for analytics
            await self.store_super_chat(room_id, message)
            
        except Exception as e:
            logger.error(f"Error processing super chat: {e}")

    async def store_super_chat(self, room_id: str, message: ChatMessage):
        """Store super chat for analytics"""
        try:
            key = f"super_chat:{room_id}"
            super_chat_data = {
                "message_id": message.id,
                "user_id": message.user_id,
                "amount": message.super_chat_amount,
                "rtc_amount": message.rtc_amount,
                "timestamp": message.timestamp
            }
            await asyncio.to_thread(
                self.redis.lpush,
                key,
                json.dumps(super_chat_data)
            )
        except Exception as e:
            logger.error(f"Error storing super chat: {e}")

    async def handle_premiere_countdown(self, room_id: str, premiere_data: dict):
        """Handle premiere countdown updates"""
        try:
            premiere_info = PremiereInfo(
                premiere_id=premiere_data.get("premiere_id"),
                title=premiere_data.get("title"),
                scheduled_time=premiere_data.get("scheduled_time"),
                current_viewers=len(self.room_clients.get(room_id, [])),
                status=premiere_data.get("status", "waiting")
            )
            
            # Calculate countdown
            scheduled_time = datetime.fromisoformat(premiere_info.scheduled_time.replace('Z', '+00:00'))
            current_time = datetime.utcnow().replace(tzinfo=scheduled_time.tzinfo)
            time_until_premiere = (scheduled_time - current_time).total_seconds()
            
            countdown_data = {
                "type": "premiere_countdown",
                "data": {
                    "premiere_info": asdict(premiere_info),
                    "countdown_seconds": max(0, int(time_until_premiere)),
                    "is_live": time_until_premiere <= 0
                }
            }
            
            await self.broadcast_to_room(room_id, countdown_data)
            
        except Exception as e:
            logger.error(f"Error handling premiere countdown: {e}")

    async def send_room_info(self, client_id: str, room_id: str):
        """Send current room information to client"""
        try:
            # Get chat history
            chat_history = await self.get_chat_history(room_id)
            
            # Get room stats
            viewer_count = len(self.room_clients.get(room_id, []))
            
            room_info = {
                "type": "room_info",
                "data": {
                    "room_id": room_id,
                    "viewer_count": viewer_count,
                    "chat_history": chat_history
                }
            }
            
            await self.send_to_client(client_id, room_info)
            
        except Exception as e:
            logger.error(f"Error sending room info: {e}")

    def verify_jwt_token(self, token: str) -> Optional[dict]:
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            return payload
        except jwt.InvalidTokenError:
            return None

    async def handle_client(self, websocket, path):
        """Handle WebSocket client connection"""
        client_id = None
        room_id = None
        
        try:
            # Wait for authentication message
            auth_message = await websocket.recv()
            auth_data = json.loads(auth_message)
            
            if auth_data.get("type") != "auth":
                await websocket.send(json.dumps({
                    "type": "error",
                    "data": {"message": "Authentication required"}
                }))
                return
            
            # Verify token
            token = auth_data.get("token")
            user_data = self.verify_jwt_token(token)
            
            if not user_data:
                await websocket.send(json.dumps({
                    "type": "error", 
                    "data": {"message": "Invalid token"}
                }))
                return
            
            client_id = user_data.get("user_id", str(uuid.uuid4()))
            room_id = auth_data.get("room_id")
            
            if not room_id:
                await websocket.send(json.dumps({
                    "type": "error",
                    "data": {"message": "Room ID required"}
                }))
                return
            
            # Register client
            await self.register_client(websocket, client_id, room_id)
            
            # Send authentication success
            await websocket.send(json.dumps({
                "type": "auth_success",
                "data": {"client_id": client_id, "room_id": room_id}
            }))
            
            # Handle messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    message_type = data.get("type")
                    
                    if message_type == "chat_message":
                        await self.handle_chat_message(client_id, room_id, data.get("data", {}))
                    
                    elif message_type == "premiere_countdown":
                        await self.handle_premiere_countdown(room_id, data.get("data", {}))
                    
                    elif message_type == "ping":
                        await self.send_to_client(client_id, {"type": "pong"})
                    
                    else:
                        logger.warning(f"Unknown message type: {message_type}")
                        
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Client disconnected")
        except Exception as e:
            logger.error(f"Error in client handler: {e}")
        finally:
            if client_id and room_id:
                await self.unregister_client(client_id, room_id)

    async def start_countdown_updater(self):
        """Start background task for premiere countdown updates"""
        while True:
            try:
                # Get all active premieres from Redis
                premiere_keys = await asyncio.to_thread(
                    self.redis.keys,
                    "premiere:*"
                )
                
                for key in premiere_keys:
                    room_id = key.split(":")[1]
                    if room_id in self.room_clients:
                        premiere_data = await asyncio.to_thread(
                            self.redis.hgetall,
                            key
                        )
                        if premiere_data:
                            await self.handle_premiere_countdown(room_id, premiere_data)
                
                await asyncio.sleep(1)  # Update every second
                
            except Exception as e:
                logger.error(f"Error in countdown updater: {e}")
                await asyncio.sleep(5)

    async def start_server(self):
        """Start the WebSocket server"""
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")
        
        # Start countdown updater task
        asyncio.create_task(self.start_countdown_updater())
        
        # Start WebSocket server
        async with websockets.serve(self.handle_client, self.host, self.port):
            logger.info(f"WebSocket server running on ws://{self.host}:{self.port}")
            await asyncio.Future()  # Run forever

if __name__ == "__main__":
    server = WebSocketServer()
    asyncio.run(server.start_server())