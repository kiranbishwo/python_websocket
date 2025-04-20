# WebSocket Server and Client Application

This project implements a real-time communication system using WebSockets, with a server built in Python using the `websockets` library.

## Features

- Dynamic WebSocket server that supports room-based messaging
- Path-based subscription model for flexible communication channels
- Client authentication support
- Message distribution based on path hierarchy
- Configurable SSL/TLS support
- Comprehensive logging with daily rotation
- Multiple client support for testing

## Project Structure

```
WEBSOCKET/
├── venv/                  # Python virtual environment
├── .env                   # Environment configuration file
├── .gitignore             # Git ignore file
├── index.html             # Main HTML page
├── readme.md              # This documentation file
├── requirements.txt       # Python dependencies
├── websocket_bridge.log   # Bridge log file
├── websocket_client.py    # Test client implementation
├── websocket.log          # Main WebSocket server log
├── websocket.log.2025-02-03  # Rotated log files
├── websocket.log.2025-02-06
├── websocket.log.2025-02-08
└── websocket.py           # Main WebSocket server implementation
```

## Prerequisites

- Python 3.7+
- pip (Python package installer)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/kiranbishwo/python_websocket.git
   cd python_websocket
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On macOS/Linux
   source venv/bin/activate
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

The application uses `python-decouple` for configuration management. Set up your `.env` file in the root directory with the following variables:

```
# WebSocket Server Configuration
WS_HOST=0.0.0.0
WS_PORT=8765
ALLOWED_HOSTS=*

# SSL Configuration (optional)
USE_SSL=False
SSL_CERT_PATH=cert.pem
SSL_KEY_PATH=key.pem
```

## Running the Application

### 1. Start the WebSocket Server

```bash
python websocket.py
```

The server will start and listen for connections at the configured host and port.

### 2. (Optional) Run the Test Client

```bash
python websocket_client.py
```

This script creates multiple test clients that connect to the WebSocket server.

## WebSocket API

### Client Authentication

```json
{
  "user_id": "<user_identifier>"
}
```

### Join a Room

```json
{
  "type": "command",
  "command": "join",
  "room": "<room_name>"
}
```

### Send a Chat Message

```json
{
  "type": "chat",
  "content": "<message_content>"
}
```

## SSL/TLS Configuration

To enable secure WebSocket connections (WSS):

1. Set `USE_SSL=True` in your `.env` file
2. Provide the paths to your SSL certificate and key:
   ```
   SSL_CERT_PATH=path/to/cert.pem
   SSL_KEY_PATH=path/to/key.pem
   ```

## Dependencies

The `requirements.txt` file should contain:

```
websockets
python-decouple
```

## Logging

The WebSocket server logs information to:
- Console (for quick debugging)
- `websocket.log` file with daily rotation (7-day retention)

## Development Notes

- The WebSocket server supports dynamic path-based routing
- Messages are distributed to clients based on path hierarchy
- The client connection handler can be extended with custom authentication