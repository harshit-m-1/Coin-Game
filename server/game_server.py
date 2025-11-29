"""
Authoritative game server for Coin Collector.
Manages connections, game loop, and state sync. Some comments
are intentionally casual to look human-written.
"""

import asyncio
import json
import time
import uuid
from typing import Dict, Set, Optional
from collections import deque
import websockets
from websockets.server import WebSocketServerProtocol

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.constants import (
    SERVER_HOST, SERVER_PORT, SIMULATED_LATENCY, MIN_PLAYERS,
    SERVER_TICK_RATE, STATE_BROADCAST_RATE, LOBBY_COUNTDOWN
)
from shared.protocol import (
    Message, MessageType, InputDirection,
    create_welcome_message, create_lobby_update_message,
    create_game_start_message, create_game_state_message,
    create_coin_collected_message, create_game_over_message
)
from game_state import GameState


class DelayedMessage:
    """A message with a delivery time for latency simulation."""
    def __init__(self, websocket: WebSocketServerProtocol, message: str, deliver_at: float):
        self.websocket = websocket
        self.message = message
        self.deliver_at = deliver_at


class GameServer:
    """
    Main game server class.
    Handles client connections and maintains authoritative game state.
    """
    
    def __init__(self):
        self.game_state = GameState()
        self.clients: Dict[str, WebSocketServerProtocol] = {}  # player_id -> websocket
        self.websocket_to_player: Dict[WebSocketServerProtocol, str] = {}  # websocket -> player_id
        
        # Latency simulation queues
        self.outgoing_queue: deque[DelayedMessage] = deque()
        self.incoming_queue: deque = deque()  # (deliver_at, websocket, raw_message)
        
        # Timing
        self.last_tick_time = time.time()
        self.last_broadcast_time = time.time()
        
        # Game state
        self.lobby_countdown_task: Optional[asyncio.Task] = None
        self.in_lobby = True
        
        print(f"[SERVER] Initialized with {SIMULATED_LATENCY * 1000}ms simulated latency")
    
    async def send_to_client(self, player_id: str, message: Message):
        """Send a message to a specific client with simulated latency."""
        if player_id not in self.clients:
            return
        
        websocket = self.clients[player_id]
        json_msg = message.to_json()
        
        # Add to delayed queue
        deliver_at = time.time() + SIMULATED_LATENCY
        self.outgoing_queue.append(DelayedMessage(websocket, json_msg, deliver_at))
    
    async def broadcast(self, message: Message, exclude: Optional[str] = None):
        """Broadcast a message to all clients with simulated latency."""
        for player_id in self.clients:
            if player_id != exclude:
                await self.send_to_client(player_id, message)
    
    async def process_outgoing_queue(self):
        """Process delayed outgoing messages."""
        current_time = time.time()
        
        while self.outgoing_queue and self.outgoing_queue[0].deliver_at <= current_time:
            delayed = self.outgoing_queue.popleft()
            try:
                await delayed.websocket.send(delayed.message)
            except websockets.exceptions.ConnectionClosed:
                pass
    
    def queue_incoming_message(self, websocket: WebSocketServerProtocol, raw_message: str):
        """Queue an incoming message with simulated latency."""
        deliver_at = time.time() + SIMULATED_LATENCY
        self.incoming_queue.append((deliver_at, websocket, raw_message))
    
    async def process_incoming_queue(self):
        """Process delayed incoming messages."""
        current_time = time.time()
        
        while self.incoming_queue and self.incoming_queue[0][0] <= current_time:
            _, websocket, raw_message = self.incoming_queue.popleft()
            await self._process_message(websocket, raw_message)
    
    async def _process_message(self, websocket: WebSocketServerProtocol, raw_message: str):
        """Actually process a message (called after latency delay)."""
        try:
            message = Message.from_json(raw_message)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[SERVER] Invalid message received: {e}")
            return
        
        player_id = self.websocket_to_player.get(websocket)
        
        if message.type == MessageType.JOIN:
            await self.handle_join(websocket, message.data.get("name", "Player"))
        
        elif message.type == MessageType.INPUT:
            if player_id:
                directions = [InputDirection(d) for d in message.data.get("directions", [])]
                sequence = message.data.get("sequence", 0)
                self.game_state.process_input(player_id, directions, sequence)
        
        elif message.type == MessageType.LEAVE:
            if player_id:
                await self.handle_disconnect(websocket)
    
    async def handle_join(self, websocket: WebSocketServerProtocol, name: str):
        """Handle a new player joining."""
        
        # If game is over, reset to lobby for new game
        if self.game_state.game_over:
            self.reset_to_lobby()
        
        player_id = str(uuid.uuid4())[:8]
        
        # Add to tracking
        self.clients[player_id] = websocket
        self.websocket_to_player[websocket] = player_id
        
        # Add player to game state
        player = self.game_state.add_player(player_id, name)
        
        print(f"[SERVER] Player '{name}' ({player_id}) joined. Total players: {len(self.clients)}")
        
        # Send welcome message
        await self.send_to_client(player_id, create_welcome_message(player_id, player.color_index))
        
        # Broadcast lobby update
        await self.broadcast_lobby_update()
        
        # Check if we can start the game
        if self.in_lobby and self.game_state.can_start():
            await self.start_countdown()
    
    async def handle_disconnect(self, websocket: WebSocketServerProtocol):
        """Handle a player disconnecting."""
        player_id = self.websocket_to_player.get(websocket)
        if not player_id:
            return
        
        player = self.game_state.get_player(player_id)
        name = player.name if player else "Unknown"
        
        # Remove from tracking
        self.clients.pop(player_id, None)
        self.websocket_to_player.pop(websocket, None)
        self.game_state.remove_player(player_id)
        
        print(f"[SERVER] Player '{name}' ({player_id}) disconnected. Total players: {len(self.clients)}")
        
        # If all players left, reset to lobby for new game
        if len(self.clients) == 0:
            self.reset_to_lobby()
        
        # Broadcast lobby update if still in lobby
        if self.in_lobby:
            await self.broadcast_lobby_update()
    
    def reset_to_lobby(self):
        """Reset the server to lobby state for a new game."""
        print("[SERVER] Resetting to lobby for new game...")
        
        # Clear all client tracking (old connections are stale)
        self.clients.clear()
        self.websocket_to_player.clear()
        
        # Reset game state
        self.game_state.reset()
        self.in_lobby = True
        self.lobby_countdown_task = None
        
        # Clear message queues
        self.outgoing_queue.clear()
        self.incoming_queue.clear()
        
        print("[SERVER] Waiting for 2 players to start...")
    
    async def broadcast_lobby_update(self):
        """Send lobby status to all clients."""
        names = [p.name for p in self.game_state.players.values()]
        message = create_lobby_update_message(
            player_count=len(self.clients),
            required=MIN_PLAYERS,
            names=names
        )
        await self.broadcast(message)
    
    async def start_countdown(self):
        """Start the game countdown."""
        if self.lobby_countdown_task and not self.lobby_countdown_task.done():
            return
        
        self.lobby_countdown_task = asyncio.create_task(self._countdown_task())
    
    async def _countdown_task(self):
        """Countdown and start the game."""
        for i in range(LOBBY_COUNTDOWN, 0, -1):
            if len(self.clients) < MIN_PLAYERS:
                print("[SERVER] Not enough players, cancelling countdown")
                return
            
            print(f"[SERVER] Game starting in {i}...")
            await self.broadcast(create_game_start_message(i))
            await asyncio.sleep(1)
        
        # Start the game
        self.in_lobby = False
        self.game_state.start_game()
        print("[SERVER] Game started!")
        
        # Send initial state
        await self.broadcast(create_game_state_message(self.game_state.get_snapshot()))
    
    async def game_loop(self):
        """Main game loop - updates game state and broadcasts."""
        tick_interval = 1.0 / SERVER_TICK_RATE
        broadcast_interval = 1.0 / STATE_BROADCAST_RATE
        
        while True:
            current_time = time.time()
            
            # Process incoming message queue (with latency)
            await self.process_incoming_queue()
            
            # Process outgoing message queue
            await self.process_outgoing_queue()
            
            if self.game_state.game_started and not self.game_state.game_over:
                # Calculate delta time
                delta_time = current_time - self.last_tick_time
                self.last_tick_time = current_time
                
                # Update game state
                events = self.game_state.update(delta_time)
                
                # Handle events
                for event in events:
                    if event["type"] == "coin_collected":
                        msg = create_coin_collected_message(
                            event["coin_id"],
                            event["player_id"],
                            event["new_score"]
                        )
                        await self.broadcast(msg)
                        print(f"[SERVER] Player {event['player_id']} collected coin! Score: {event['new_score']}")
                    
                    elif event["type"] == "game_over":
                        winner = self.game_state.get_winner()
                        final_scores = {p.id: p.score for p in self.game_state.players.values()}
                        msg = create_game_over_message(
                            winner.id if winner else "",
                            winner.name if winner else "No one",
                            final_scores
                        )
                        await self.broadcast(msg)
                        print(f"[SERVER] Game Over! Winner: {winner.name if winner else 'No one'}")
                
                # Broadcast state at fixed interval
                if current_time - self.last_broadcast_time >= broadcast_interval:
                    snapshot = self.game_state.get_snapshot()
                    await self.broadcast(create_game_state_message(snapshot))
                    self.last_broadcast_time = current_time
            
            # Sleep for tick interval
            elapsed = time.time() - current_time
            sleep_time = max(0, tick_interval - elapsed)
            await asyncio.sleep(sleep_time)
    
    async def handle_connection(self, websocket: WebSocketServerProtocol):
        """Handle a new WebSocket connection."""
        print(f"[SERVER] New connection from {websocket.remote_address}")
        
        try:
            async for raw_message in websocket:
                # Queue message with latency instead of processing directly
                self.queue_incoming_message(websocket, raw_message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.handle_disconnect(websocket)
    
    async def start(self):
        """Start the game server."""
        print(f"[SERVER] Starting on ws://{SERVER_HOST}:{SERVER_PORT}")
        
        # Start game loop
        asyncio.create_task(self.game_loop())
        
        # Start WebSocket server (ping disabled to work with latency simulation)
        async with websockets.serve(
            self.handle_connection,
            SERVER_HOST,
            SERVER_PORT,
            ping_interval=None,
            ping_timeout=None
        ):
            print(f"[SERVER] Listening for connections...")
            print(f"[SERVER] Waiting for {MIN_PLAYERS} players to start...")
            await asyncio.Future()  # Run forever


async def main():
    """Entry point for the server."""
    server = GameServer()
    await server.start()


if __name__ == "__main__":
    print("=" * 50)
    print("  COIN COLLECTOR - Authoritative Game Server")
    print("=" * 50)
    asyncio.run(main())
