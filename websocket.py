from websockets.server import WebSocketServerProtocol, serve
import asyncio
import ssl
import logging
import json
import time
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import urlparse
from decouple import config
from typing import Dict, Set
from aiohttp import web
from aiohttp.web import middleware

# Configure logging
logger = logging.getLogger('websocket_server')
logger.setLevel(logging.INFO)

# File handler
file_handler = TimedRotatingFileHandler(
    'websocket.log', 
    when='D',
    interval=1, 
    backupCount=7
)
file_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
)
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter('%(levelname)s: %(message)s')
)
logger.addHandler(console_handler)

class DynamicWebSocketServer:
    def __init__(self):
        self.clients_by_url: Dict[str, Set[WebSocketServerProtocol]] = {}
        self.client_info: Dict[WebSocketServerProtocol, dict] = {}
        self.rooms: Dict[str, Set[WebSocketServerProtocol]] = {}  # room-based subscriptions
        logger.info("WebSocket server initialized")

    async def register(self, websocket: WebSocketServerProtocol, path: str) -> None:
        """Register a client connection with its path"""
        if path not in self.clients_by_url:
            self.clients_by_url[path] = set()
        self.clients_by_url[path].add(websocket)
        
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f'Client {client_id} connected to {path}')
        
        # Store client metadata
        self.client_info[websocket] = {
            'path': path,
            'address': client_id,
            'custom_id': None,
            'subscribed_rooms': set()  # Use set for better performance
        }
        
        # Send connection acknowledgment
        await self.send_message(websocket, json.dumps({
            'type': 'connection_established',
            'data': {
                'client_id': client_id,
                'server_time': int(time.time())
            }
        }))
        
        await self.log_connection_state()

    async def unregister(self, websocket: WebSocketServerProtocol) -> None:
        """Remove a client connection"""
        if websocket in self.client_info:
            path = self.client_info[websocket]['path']
            client_id = self.client_info[websocket]['address']
            
            # Remove from path-based clients
            if path in self.clients_by_url:
                self.clients_by_url[path].discard(websocket)
                if not self.clients_by_url[path]:
                    del self.clients_by_url[path]
            
            # Remove from all subscribed rooms
            subscribed_rooms = self.client_info[websocket].get('subscribed_rooms', set())
            for room in subscribed_rooms:
                if room in self.rooms:
                    self.rooms[room].discard(websocket)
                    if not self.rooms[room]:
                        del self.rooms[room]
            
            logger.info(f'Client {client_id} disconnected from {path}')
            del self.client_info[websocket]
            
            await self.log_connection_state()

    async def log_connection_state(self):
        """Log the current connection state"""
        logger.info(f"==== WebSocket Server Status ====")
        logger.info(f"Total connected clients: {len(self.client_info)}")
        logger.info(f"Rooms: {len(self.rooms)}")
        
        for room, clients in self.rooms.items():
            logger.info(f"  Room '{room}': {len(clients)} client(s)")
        
        for path, clients in self.clients_by_url.items():
            logger.info(f"  Path '{path}': {len(clients)} client(s)")
        
        logger.info(f"============================")

    async def handle_subscription(self, websocket: WebSocketServerProtocol, message_data: dict) -> None:
        """Handle client subscription requests"""
        try:
            action = message_data.get('type') or message_data.get('action')
            
            if action == 'subscribe':
                room = message_data.get('room')
                if room:
                    # Register client to this specific room
                    if room not in self.rooms:
                        self.rooms[room] = set()
                    self.rooms[room].add(websocket)
                    
                    # Update client info
                    self.client_info[websocket]['subscribed_rooms'].add(room)
                    
                    logger.info(f"Client {self.client_info[websocket]['address']} subscribed to room: {room}")
                    
                    # Send confirmation to client
                    await self.send_message(websocket, json.dumps({
                        'type': 'subscription_ack',
                        'data': {
                            'room': room,
                            'status': 'subscribed',
                            'message': f'Successfully subscribed to {room}'
                        }
                    }))
                    
            elif action == 'unsubscribe':
                room = message_data.get('room')
                if room and room in self.rooms and websocket in self.rooms[room]:
                    self.rooms[room].discard(websocket)
                    
                    # Update client info
                    self.client_info[websocket]['subscribed_rooms'].discard(room)
                    
                    logger.info(f"Client {self.client_info[websocket]['address']} unsubscribed from room: {room}")
                    
                    # Send confirmation
                    await self.send_message(websocket, json.dumps({
                        'type': 'subscription_ack',
                        'data': {
                            'room': room,
                            'status': 'unsubscribed'
                        }
                    }))
                    
            elif action == 'echo':
                # Handle echo request for connection testing
                await self.send_message(websocket, json.dumps({
                    'type': 'echo',
                    'data': message_data.get('data', {})
                }))
                
        except Exception as e:
            logger.error(f"Error handling subscription: {e}")
            # Send error response
            await self.send_message(websocket, json.dumps({
                'type': 'error',
                'data': {
                    'message': f'Subscription error: {str(e)}'
                }
            }))

    async def distribute_message(self, message: str, sender_path: str = "/") -> None:
        """Distribute message to relevant clients based on room or path"""
        recipients = set()
        message_data = None
        
        # Parse message to determine routing
        try:
            message_data = json.loads(message)
            room = message_data.get('room')
            
            if room:
                # Room-based routing
                if room in self.rooms:
                    recipients.update(self.rooms[room])
                logger.info(f'Broadcasting to room "{room}": {len(recipients)} recipients')
            else:
                # Path-based routing (fallback)
                for path, clients in self.clients_by_url.items():
                    if path == sender_path or path.startswith(sender_path):
                        recipients.update(clients)
                logger.info(f'Broadcasting to path "{sender_path}": {len(recipients)} recipients')
                
        except json.JSONDecodeError:
            # Not JSON, use path-based routing
            for path, clients in self.clients_by_url.items():
                if path == sender_path or path.startswith(sender_path):
                    recipients.update(clients)
            logger.info(f'Broadcasting non-JSON message to path "{sender_path}": {len(recipients)} recipients')
        
        # Send to all recipients
        if recipients:
            # Log the message being sent
            if message_data:
                logger.info(f'Sending message of type "{message_data.get("type")}" to {len(recipients)} clients')
            else:
                logger.info(f'Sending raw message to {len(recipients)} clients')
                
            results = await asyncio.gather(
                *[self.send_message(client, message) for client in recipients],
                return_exceptions=True
            )
            
            # Log any errors
            errors = [r for r in results if isinstance(r, Exception)]
            if errors:
                logger.error(f'Failed to send to {len(errors)} clients: {errors}')
        else:
            logger.warning(f'No recipients found for message. Room: {message_data.get("room") if message_data else "none"}, Path: {sender_path}')

    async def send_message(self, websocket: WebSocketServerProtocol, message: str) -> None:
        """Send a message to a specific client"""
        try:
            if websocket.closed:
                logger.warning(f'Attempted to send to closed connection: {self.client_info.get(websocket, {}).get("address", "unknown")}')
                return
                
            await websocket.send(message)
            logger.debug(f'Message sent to {self.client_info.get(websocket, {}).get("address", "unknown")}')
        except Exception as e:
            logger.error(f'Error sending message to {self.client_info.get(websocket, {}).get("address", "unknown")}: {e}')
            await self.unregister(websocket)

    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str) -> None:
        """Main connection handler"""
        try:
            await self.register(websocket, path)
            
            async for message in websocket:
                logger.debug(f'Received message from {self.client_info[websocket]["address"]}: {message}')
                
                # Try to parse message as JSON
                try:
                    message_data = json.loads(message)
                    
                    # Check if this is a subscription message
                    action = message_data.get('type') or message_data.get('action')
                    if action in ['subscribe', 'unsubscribe', 'echo']:
                        await self.handle_subscription(websocket, message_data)
                        continue
                        
                except json.JSONDecodeError:
                    # Not JSON, proceed with regular message handling
                    logger.debug(f'Received non-JSON message: {message}')
                    
                # Regular message distribution
                await self.distribute_message(message, path)
                
        except Exception as e:
            logger.error(f'Connection handler error: {e}')
        finally:
            await self.unregister(websocket)

    async def check_origin(self, websocket: WebSocketServerProtocol) -> bool:
        """Validate connection origin"""
        allowed_hosts = config('ALLOWED_HOSTS', default='*', cast=str)
        
        if allowed_hosts == '*':
            return True
            
        origin = websocket.request_headers.get('Origin')
        if not origin:
            logger.warning(f'Missing Origin header from {websocket.remote_address}')
            return False
            
        parsed_origin = urlparse(origin)
        origin_host = parsed_origin.hostname
        if parsed_origin.port:
            origin_host += f":{parsed_origin.port}"
            
        return origin_host in allowed_hosts.split(',')

# Create CORS middleware for the HTTP server
@middleware
async def cors_middleware(request, handler):
    response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS, PUT, DELETE'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response

# Handle OPTIONS requests for CORS preflight
async def handle_options(request):
    return web.Response(status=204)

# HTTP Server for message push
async def handle_push(request):
    """HTTP endpoint to push messages to WebSocket clients"""
    try:
        # Get the JSON data from the request
        data = await request.json()
        
        # Validate data
        if not isinstance(data, dict):
            logger.error(f'Invalid data format received: {data}')
            return web.Response(status=400, text='Invalid data format')
        
        logger.info(f'HTTP Push request received: {json.dumps(data, indent=2)}')
        
        # Special handling for ping messages
        if data.get('type') == 'ping':
            logger.info(f'Received ping request from {data.get("data", {}).get("source", "unknown")}')
            return web.Response(
                status=200, 
                text=json.dumps({
                    'status': 'ok',
                    'message': 'Server is online',
                    'timestamp': int(time.time())
                }),
                content_type='application/json'
            )
        
        # Determine the room/path to send the message to
        room = data.get('room', '/')
        logger.info(f'Broadcasting message to room: {room}')
        
        # Convert data to string for WebSocket transmission
        message = json.dumps(data)
        
        # Distribute the message
        await server.distribute_message(message, room)
        
        return web.Response(
            status=200, 
            text=json.dumps({
                'status': 'ok',
                'message': 'Message sent',
                'room': room,
                'recipients': len(server.rooms.get(room, set()))
            }),
            content_type='application/json'
        )
    except Exception as e:
        logger.error(f'Error handling push request: {e}')
        return web.Response(status=500, text=str(e))

# Main server startup
async def start_server():
    global server
    server = DynamicWebSocketServer()
    
    # SSL Configuration
    ssl_context = None
    if config('USE_SSL', default=False, cast=bool):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(
            config('SSL_CERT_PATH', default='cert.pem'),
            config('SSL_KEY_PATH', default='key.pem')
        )

    # WebSocket Server Configuration
    ws_host = config('WS_HOST', default='0.0.0.0')
    ws_port = config('WS_PORT', default=8765, cast=int)
    
    # HTTP Server Configuration
    http_host = config('HTTP_HOST', default='0.0.0.0')
    http_port = config('HTTP_PORT', default=8766, cast=int)
    
    # Create aiohttp app for HTTP endpoint with CORS middleware
    app = web.Application(middlewares=[cors_middleware])
    
    # Routes
    app.router.add_post('/push', handle_push)
    app.router.add_options('/push', handle_options)
    
    # Start the HTTP server
    http_runner = web.AppRunner(app)
    await http_runner.setup()
    http_site = web.TCPSite(http_runner, http_host, http_port)
    await http_site.start()
    logger.info(f'HTTP Server running on http://{http_host}:{http_port}')
    
    # Start the WebSocket server with proper error handling
    try:
        async with serve(
            server.handle_connection,
            host=ws_host,
            port=ws_port,
            ssl=ssl_context,
            ping_interval=30,
            ping_timeout=30,
            max_size=2**20,  # 1 MiB message size limit
            compression=None,  # Disable compression for debugging
        ) as ws_server:
            logger.info(f'WebSocket Server running on {"wss" if ssl_context else "ws"}://{ws_host}:{ws_port}')
            
            # Keep server running
            await asyncio.Future()  # Run forever
            
    except Exception as e:
        logger.error(f'WebSocket server error: {e}')
    finally:
        # Cleanup HTTP server
        await http_runner.cleanup()

if __name__ == '__main__':
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        logger.info("Server shutdown initiated")