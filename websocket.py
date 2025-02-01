from websockets.server import WebSocketServerProtocol, serve
import asyncio
import ssl
import logging
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import urlparse
from decouple import config
from typing import Dict, Set

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

    async def register(self, websocket: WebSocketServerProtocol, path: str) -> None:
        """Register a client connection with its path"""
        if path not in self.clients_by_url:
            self.clients_by_url[path] = set()
        self.clients_by_url[path].add(websocket)
        
        client_id = websocket.remote_address
        logger.info(f'Client {client_id} connected to {path}')
        
        # Store client metadata
        self.client_info[websocket] = {
            'path': path,
            'address': client_id,
            'custom_id': None  # Can be set via authentication
        }

    async def unregister(self, websocket: WebSocketServerProtocol) -> None:
        """Remove a client connection"""
        if websocket in self.client_info:
            path = self.client_info[websocket]['path']
            if path in self.clients_by_url:
                self.clients_by_url[path].remove(websocket)
                if not self.clients_by_url[path]:
                    del self.clients_by_url[path]
            
            client_id = self.client_info[websocket]['address']
            logger.info(f'Client {client_id} disconnected from {path}')
            del self.client_info[websocket]

    async def distribute_message(self, message: str, sender_path: str) -> None:
        """Distribute message to relevant clients based on path hierarchy"""
        recipients = set()
        
        # Find all paths that match or are subpaths
        for path, clients in self.clients_by_url.items():
            if path == sender_path or path.startswith(sender_path):
                recipients.update(clients)
        
        if recipients:
            await asyncio.gather(
                *[self.send_message(client, message) for client in recipients],
                return_exceptions=True
            )

    async def send_message(self, websocket: WebSocketServerProtocol, message: str) -> None:
        """Send a message to a specific client"""
        try:
            await websocket.send(message)
            logger.debug(f'Message sent to {self.client_info[websocket]["address"]}')
        except Exception as e:
            logger.error(f'Error sending message to {self.client_info[websocket]["address"]}: {e}')
            await self.unregister(websocket)

    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str) -> None:
        """Main connection handler"""
        try:
            # Optional: Implement custom authentication here
            # auth_status = await self.authenticate(websocket)
            # if not auth_status:
            #     await websocket.close(1008, "Authentication failed")
            #     return

            await self.register(websocket, path)
            
            async for message in websocket:
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

async def start_server():
    server = DynamicWebSocketServer()
    
    # SSL Configuration
    ssl_context = None
    if config('USE_SSL', default=False, cast=bool):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(
            config('SSL_CERT_PATH', default='cert.pem'),
            config('SSL_KEY_PATH', default='key.pem')
        )

    # Server Configuration
    host = config('WS_HOST', default='0.0.0.0')
    port = config('WS_PORT', default=8765, cast=int)
    
    async with serve(
        server.handle_connection,
        host=host,
        port=port,
        ssl=ssl_context,
        ping_interval=30,
        ping_timeout=30,
        max_size=2**20,  # 1 MiB message size limit
    ) as ws_server:
        logger.info(f'WebSocket Server running on {"wss" if ssl_context else "ws"}://{host}:{port}')
        await ws_server.wait_closed()

if __name__ == '__main__':
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        logger.info("Server shutdown initiated")