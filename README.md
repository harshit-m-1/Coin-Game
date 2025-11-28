# 🎮 Coin Collector - Multiplayer State Synchronization Game

A real-time multiplayer game demonstrating client-server architecture with authoritative server design, network latency simulation, and entity interpolation.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![WebSocket](https://img.shields.io/badge/Network-WebSocket-green.svg)
![Pygame](https://img.shields.io/badge/Graphics-Pygame-red.svg)

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Running the Game](#running-the-game)
- [Controls](#controls)
- [Technical Details](#technical-details)
- [Design Decisions](#design-decisions)

## 🎯 Overview

Coin Collector is a multiplayer game where players compete to collect coins that spawn randomly on the map. The game demonstrates:

- **Server-Authoritative Architecture**: All game state is managed by the server
- **Network Latency Simulation**: 200ms artificial latency on all messages
- **Entity Interpolation**: Smooth rendering despite network delays
- **Client-Side Prediction**: Responsive local player movement

## ✨ Features

### Game Features

- 2-4 player multiplayer support
- Random coin spawning every 3 seconds
- 2-minute timed matches
- Real-time score tracking
- Winner announcement at game end

### Technical Features

- **Server Authority**: Clients send only input intent, server validates everything
- **200ms Latency Simulation**: Both client→server and server→client
- **Entity Interpolation**: Remote players move smoothly using position buffering
- **Client-Side Prediction**: Local player responds immediately to input
- **WebSocket Communication**: Real-time bidirectional messaging

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         GAME SERVER                              │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐   │
│  │ Game State  │  │  Physics &   │  │  Network Handler      │   │
│  │ (Authority) │  │  Collisions  │  │  (WebSocket Server)   │   │
│  └─────────────┘  └──────────────┘  └───────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ WebSocket (with 200ms latency)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         GAME CLIENT                              │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐   │
│  │   Pygame    │  │ Interpolation│  │  Network Client       │   │
│  │  Renderer   │  │   Manager    │  │  (WebSocket Client)   │   │
│  └─────────────┘  └──────────────┘  └───────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Message Flow

1. **Client Input**: Client sends movement intent (e.g., "move left")
2. **Latency Delay**: 200ms artificial delay before server receives
3. **Server Processing**: Server validates and updates authoritative state
4. **State Broadcast**: Server sends game state to all clients
5. **Latency Delay**: 200ms artificial delay before client receives
6. **Client Rendering**: Client interpolates and renders smooth movement

## 📦 Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Setup

1. **Clone or navigate to the project directory:**

   ```bash
   cd coin_collector
   ```

2. **Create a virtual environment (recommended):**

   ```bash
   python -m venv venv

   # On Windows:
   venv\Scripts\activate

   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## 🎮 Running the Game

### Step 1: Start the Server

Open a terminal and run:

```bash
python server/game_server.py
```

You should see:

```
==================================================
  COIN COLLECTOR - Authoritative Game Server
==================================================
[SERVER] Initialized with 200.0ms simulated latency
[SERVER] Starting on ws://localhost:8765
[SERVER] Listening for connections...
[SERVER] Waiting for 2 players to start...
```

### Step 2: Start Client(s)

Open **two separate terminals** and run:

**Terminal 2 (Client 1):**

```bash
python client/game_client.py Player1
```

**Terminal 3 (Client 2):**

```bash
python client/game_client.py Player2
```

Or use random names:

```bash
python client/game_client.py
```

### Step 3: Play!

- When 2 players connect, the game starts after a 3-second countdown
- Collect coins to earn points
- The player with the most points after 2 minutes wins!

## 🎮 Controls

| Key   | Action     |
| ----- | ---------- |
| W / ↑ | Move Up    |
| S / ↓ | Move Down  |
| A / ← | Move Left  |
| D / → | Move Right |
| ESC   | Quit Game  |

## 🔧 Technical Details

### Network Protocol

All messages use JSON over WebSocket:

```json
{
    "type": "message_type",
    "data": { ... }
}
```

#### Message Types

| Type             | Direction     | Description          |
| ---------------- | ------------- | -------------------- |
| `join`           | Client→Server | Request to join game |
| `input`          | Client→Server | Movement input       |
| `welcome`        | Server→Client | Join confirmation    |
| `lobby_update`   | Server→Client | Lobby status         |
| `game_start`     | Server→Client | Game countdown       |
| `game_state`     | Server→Client | Full state sync      |
| `coin_collected` | Server→Client | Coin pickup event    |
| `game_over`      | Server→Client | Game end             |

### Latency Simulation

Latency is simulated at multiple points:

1. **Client Outgoing**: Messages delayed 200ms before sending
2. **Server Incoming**: Messages processed after 200ms delay
3. **Server Outgoing**: Messages delayed 200ms before sending
4. **Client Incoming**: Messages processed after 200ms delay

**Total Round-Trip Latency: ~400ms**

### Entity Interpolation

Remote players are rendered using interpolation:

1. Position snapshots are buffered with timestamps
2. Rendering happens ~100ms in the past
3. Linear interpolation between buffered positions
4. Extrapolation used when buffer runs dry

```python
# Simplified interpolation logic
render_time = current_time - interpolation_delay
position = lerp(before_position, after_position, t)
```

### Server Authority

The server is the **single source of truth** for:

- Player positions (validated from input)
- Coin positions (randomly generated)
- Collision detection (proximity checks)
- Score tracking (incremented on valid pickup)

Clients **cannot**:

- Report their own position
- Claim coin pickups directly
- Modify scores

## 📝 Design Decisions

### Why WebSocket?

- Bidirectional real-time communication
- Lower overhead than HTTP polling
- Built-in connection management
- Good Python library support (`websockets`)

### Why Pygame?

- Simple 2D graphics API
- Cross-platform support
- Easy to install and run
- Good for demonstrating game concepts

### Why Authoritative Server?

- Prevents cheating (client can't report false positions)
- Consistent game state across all clients
- Server handles all collision detection
- Matches real multiplayer game architecture

### Handling Network Issues

1. **High Latency**: Interpolation keeps visuals smooth
2. **Packet Loss**: TCP/WebSocket ensures delivery
3. **Disconnection**: Server removes player, notifies others

## 📁 Project Structure

```
coin_collector/
├── server/
│   ├── __init__.py
│   ├── game_server.py      # WebSocket server & game loop
│   └── game_state.py       # Authoritative game state
├── client/
│   ├── __init__.py
│   ├── game_client.py      # Main client application
│   ├── network.py          # WebSocket client
│   ├── renderer.py         # Pygame rendering
│   └── interpolation.py    # Smooth movement system
├── shared/
│   ├── __init__.py
│   ├── constants.py        # Shared configuration
│   └── protocol.py         # Message definitions
├── requirements.txt
└── README.md
```

## 🎥 Video Demonstration

For the video demonstration, show:

1. **Two client windows side by side**
2. **Smooth movement** despite 200ms latency
3. **Coin collection** with server validation
4. **Score synchronization** across clients
5. **Game over screen** with winner

## 🐛 Troubleshooting

### "Import could not be resolved"

Run `pip install -r requirements.txt` to install dependencies.

### "Connection refused"

Make sure the server is running before starting clients.

### Laggy movement

This is intentional! The 200ms latency simulation is working. Watch how interpolation keeps remote players smooth.

### Only one client connects

Make sure to run clients in **separate terminals**.

## AI Disclosure
Used ChatGPT to make this readme more readable