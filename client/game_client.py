"""
Main game client for Coin Collector.
Integrates Pygame rendering, networking and interpolation.
"""

import pygame
import sys
import time
import math
import random
from typing import Dict, List, Optional, Set

# Add parent directory to path for imports
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.constants import (
    WORLD_WIDTH, WORLD_HEIGHT, PLAYER_SIZE, PLAYER_SPEED,
    PLAYER_COLORS, CLIENT_TICK_RATE, SIMULATED_LATENCY,
    COIN_PICKUP_RADIUS
)
from shared.protocol import (
    Message, MessageType, InputDirection, Vector2,
    PlayerState, CoinState, GameStateSnapshot
)

from network import NetworkClient
from renderer import GameRenderer
from interpolation import InterpolationManager, ClientSidePrediction


class GameState:
    """Client-side game state."""
    CONNECTING = "connecting"
    LOBBY = "lobby"
    PLAYING = "playing"
    GAME_OVER = "game_over"
    DISCONNECTED = "disconnected"


class CoinCollectorClient:
    """Main game client class."""
    
    def __init__(self, player_name: str = "Player"):
        self.player_name = player_name
        
        # Initialize Pygame
        pygame.init()
        pygame.display.set_caption(f"Coin Collector - {player_name}")
        self.screen = pygame.display.set_mode((WORLD_WIDTH, WORLD_HEIGHT))
        self.clock = pygame.time.Clock()
        
        # Initialize components
        self.renderer = GameRenderer(self.screen)
        self.network = NetworkClient()
        self.interpolation = InterpolationManager()
        self.prediction = ClientSidePrediction()
        
        # Game state
        self.state = GameState.CONNECTING
        self.running = True
        
        # Player data
        self.local_player_id: Optional[str] = None
        self.local_color_index: int = 0
        self.local_position = Vector2(WORLD_WIDTH / 2, WORLD_HEIGHT / 2)
        self.local_score = 0
        
        # Game data
        self.players: Dict[str, PlayerState] = {}
        self.coins: Dict[str, CoinState] = {}
        self.predicted_collected_coins: Set[str] = set()  # Coins we predict we've collected
        self.confirmed_collected_coins: Set[str] = set()  # Coins confirmed collected by server
        self.time_remaining: float = 0
        
        # Lobby data
        self.lobby_player_count: int = 0
        self.lobby_required: int = 2
        self.lobby_player_names: List[str] = []
        self.countdown: Optional[int] = None
        
        # Game over data
        self.winner_name: str = ""
        self.final_scores: Dict[str, int] = {}
        
        # Input tracking
        self.active_inputs: Set[InputDirection] = set()
        self.input_sequence = 0
        self.last_input_time = 0
        
        # Timing
        self.last_update_time = time.time()
        self.server_time_offset = 0
        
        # Latency measurement
        self.measured_latency_ms = int(SIMULATED_LATENCY * 2 * 1000)  # Start with expected value
        self.last_input_send_time = 0  # When we last sent input
        self.pending_latency_measurement = False
    
    def start(self):
        """Kick things off for the client."""
        print(f"[CLIENT] Starting as '{self.player_name}'")
        
        # Connect to server
        self.network.connect(self.player_name)
        
        # Main game loop
        self.run()
    
    def restart_game(self):
        """Restart the game by reconnecting to the server.
        (This is a quick and dirty reconnect flow.)"""
        print("[CLIENT] Restarting game...")
        
        # Disconnect existing connection
        self.network.disconnect()
        
        # Reset client state
        self.state = GameState.CONNECTING
        self.local_player_id = None
        self.local_color_index = 0
        self.local_position = Vector2(WORLD_WIDTH / 2, WORLD_HEIGHT / 2)
        self.local_score = 0
        self.players.clear()
        self.coins.clear()
        self.predicted_collected_coins.clear()
        self.confirmed_collected_coins.clear()
        self.time_remaining = 0
        self.active_inputs.clear()
        self.countdown = None
        self.winner_name = ""
        self.final_scores = {}
        self.interpolation.clear()
        self.measured_latency_ms = int(SIMULATED_LATENCY * 2 * 1000)
        self.pending_latency_measurement = False
        
        # Create new network client and connect
        self.network = NetworkClient()
        self.network.connect(self.player_name)
    
    def run(self):
        """Main game loop."""
        while self.running:
            # Calculate delta time
            current_time = time.time()
            delta_time = current_time - self.last_update_time
            self.last_update_time = current_time
            
            # Handle events
            self.handle_events()
            
            # Process network messages
            self.process_network_messages()
            
            # Update game state
            self.update(delta_time)
            
            # Render
            self.render()
            
            # Update display
            pygame.display.flip()
            
            # Cap frame rate
            self.clock.tick(CLIENT_TICK_RATE)
        
        # Cleanup
        self.cleanup()
    
    def handle_events(self):
        """Handle Pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            
            elif event.type == pygame.KEYDOWN:
                self.handle_key_down(event.key)
            
            elif event.type == pygame.KEYUP:
                self.handle_key_up(event.key)
    
    def handle_key_down(self, key):
        """Handle key press."""
        # Movement keys
        if key in (pygame.K_w, pygame.K_UP):
            self.active_inputs.add(InputDirection.UP)
        elif key in (pygame.K_s, pygame.K_DOWN):
            self.active_inputs.add(InputDirection.DOWN)
        elif key in (pygame.K_a, pygame.K_LEFT):
            self.active_inputs.add(InputDirection.LEFT)
        elif key in (pygame.K_d, pygame.K_RIGHT):
            self.active_inputs.add(InputDirection.RIGHT)
        
        # Special keys
        elif key == pygame.K_ESCAPE:
            self.running = False
        
        elif key == pygame.K_SPACE:
            if self.state == GameState.GAME_OVER:
                # Restart - disconnect and reconnect to server
                self.restart_game()
            elif self.state == GameState.DISCONNECTED:
                # Reconnect
                self.restart_game()
    
    def handle_key_up(self, key):
        """Handle key release."""
        if key in (pygame.K_w, pygame.K_UP):
            self.active_inputs.discard(InputDirection.UP)
        elif key in (pygame.K_s, pygame.K_DOWN):
            self.active_inputs.discard(InputDirection.DOWN)
        elif key in (pygame.K_a, pygame.K_LEFT):
            self.active_inputs.discard(InputDirection.LEFT)
        elif key in (pygame.K_d, pygame.K_RIGHT):
            self.active_inputs.discard(InputDirection.RIGHT)
    
    def process_network_messages(self):
        """Process incoming network messages."""
        # Check connection status
        if not self.network.connected and self.state != GameState.DISCONNECTED:
            if self.state != GameState.CONNECTING:
                self.state = GameState.DISCONNECTED
            return
        
        # Get player ID when available
        if self.network.player_id and not self.local_player_id:
            self.local_player_id = self.network.player_id
            self.local_color_index = self.network.color_index
            self.interpolation.set_local_player(self.local_player_id)
            print(f"[CLIENT] Assigned player ID: {self.local_player_id}")
        
        # Process messages
        messages = self.network.get_messages()
        for message in messages:
            self.handle_server_message(message)
    
    def handle_server_message(self, message: Message):
        """Handle a message from the server."""
        
        if message.type == MessageType.WELCOME:
            self.state = GameState.LOBBY
            print("[CLIENT] Joined lobby")
        
        elif message.type == MessageType.LOBBY_UPDATE:
            self.lobby_player_count = message.data.get("player_count", 0)
            self.lobby_required = message.data.get("required", 2)
            self.lobby_player_names = message.data.get("player_names", [])
        
        elif message.type == MessageType.GAME_START:
            self.countdown = message.data.get("countdown")
            print(f"[CLIENT] Game starting in {self.countdown}...")
        
        elif message.type == MessageType.GAME_STATE:
            self.handle_game_state(message.data)
        
        elif message.type == MessageType.COIN_COLLECTED:
            coin_id = message.data.get("coin_id")
            collector_id = message.data.get("collector_id")
            new_score = message.data.get("new_score")
            
            # Mark as confirmed collected (prevents stale state updates from re-adding)
            self.confirmed_collected_coins.add(coin_id)
            
            # Remove coin locally (server confirmed it's collected)
            self.coins.pop(coin_id, None)
            # Also clear from predictions (server is authoritative)
            self.predicted_collected_coins.discard(coin_id)
            
            # Update score if it's us
            if collector_id == self.local_player_id:
                self.local_score = new_score
                print(f"[CLIENT] Collected coin! Score: {new_score}")
            else:
                # Another player collected this coin
                print(f"[CLIENT] Another player collected coin {coin_id[:8]}")
        
        elif message.type == MessageType.GAME_OVER:
            self.state = GameState.GAME_OVER
            self.winner_name = message.data.get("winner_name", "Unknown")
            self.final_scores = message.data.get("final_scores", {})
            print(f"[CLIENT] Game Over! Winner: {self.winner_name}")
    
    def handle_game_state(self, data: dict):
        """Handle a full game state update from server."""
        snapshot = GameStateSnapshot.from_dict(data)
        current_time = time.time()
        
        # Measure latency when we receive a game state update
        if self.pending_latency_measurement and self.last_input_send_time > 0:
            # Round-trip time = now - when we sent the input
            rtt = current_time - self.last_input_send_time
            # Smooth the measurement (exponential moving average)
            self.measured_latency_ms = int(self.measured_latency_ms * 0.7 + (rtt * 1000) * 0.3)
            self.pending_latency_measurement = False
        
        # Update game state
        if snapshot.game_started and self.state == GameState.LOBBY:
            self.state = GameState.PLAYING
            self.countdown = None
            print("[CLIENT] Game started!")
            
            # Initialize local position from server when game starts
            for player_state in snapshot.players:
                if player_state.id == self.local_player_id:
                    self.local_position = Vector2(player_state.position.x, player_state.position.y)
                    break
        
        if snapshot.game_over and self.state == GameState.PLAYING:
            self.state = GameState.GAME_OVER
        
        # Update time
        self.time_remaining = snapshot.game_time_remaining
        
        # Calculate server time offset
        self.server_time_offset = time.time() - snapshot.server_time
        
        # Update players
        self.players.clear()
        for player_state in snapshot.players:
            self.players[player_state.id] = player_state
            
            # Update local player data from server (authoritative)
            if player_state.id == self.local_player_id:
                # Score is always authoritative from server
                self.local_score = player_state.score
                
                # Position reconciliation strategy:
                # With 200ms simulated latency, the server position is always ~400ms behind
                # (200ms for input to reach server + 200ms for state to come back)
                # 
                # We ONLY correct position for anti-cheat (extreme discrepancy).
                # Normal gameplay fully trusts client-side prediction.
                # Coins are collected server-side so position doesn't need to be exact.
                
                server_pos = player_state.position
                dx = server_pos.x - self.local_position.x
                dy = server_pos.y - self.local_position.y
                distance = math.sqrt(dx * dx + dy * dy)
                
                # Only correct if absurdly far off (cheating or major desync)
                # At 200px/s speed and 400ms latency, legitimate difference can be ~80px
                # We use 200px threshold to only catch actual cheats/desyncs
                if distance > 200:
                    print(f"[CLIENT] Large position desync ({distance:.0f}px), correcting...")
                    self.local_position = Vector2(server_pos.x, server_pos.y)
        
        # Process interpolation for remote players
        self.interpolation.process_game_state(snapshot)
        
        # Update coins - server is authoritative
        # Get the set of coin IDs from server
        server_coin_ids = {coin_state.id for coin_state in snapshot.coins}
        
        # Clear stale predictions (coins server no longer has = confirmed collected)
        self.predicted_collected_coins &= server_coin_ids
        
        # Also clean up confirmed_collected if server no longer has those coins
        # (they're now definitely gone, no risk of stale updates)
        self.confirmed_collected_coins &= server_coin_ids
        
        # Update coins from server, but filter out confirmed collected coins
        # (in case a stale game_state arrives after COIN_COLLECTED message)
        self.coins.clear()
        for coin_state in snapshot.coins:
            if coin_state.id not in self.confirmed_collected_coins:
                self.coins[coin_state.id] = coin_state
    
    def update(self, delta_time: float):
        """Update game logic."""
        if self.state != GameState.PLAYING:
            return
        
        current_time = time.time()
        
        # Send input to server at a reasonable rate
        if current_time - self.last_input_time >= 1.0 / 30.0:  # 30 times per second
            if self.active_inputs:
                self.network.send_input(list(self.active_inputs))
                # Start latency measurement when sending input while moving
                if not self.pending_latency_measurement:
                    self.last_input_send_time = current_time
                    self.pending_latency_measurement = True
            else:
                # Send empty input to signal no movement
                self.network.send_input([])
            self.last_input_time = current_time
        
        # Client-side prediction for local player
        velocity = Vector2(0, 0)
        if InputDirection.UP in self.active_inputs:
            velocity.y -= PLAYER_SPEED
        if InputDirection.DOWN in self.active_inputs:
            velocity.y += PLAYER_SPEED
        if InputDirection.LEFT in self.active_inputs:
            velocity.x -= PLAYER_SPEED
        if InputDirection.RIGHT in self.active_inputs:
            velocity.x += PLAYER_SPEED
        
        # Normalize diagonal movement
        if velocity.x != 0 and velocity.y != 0:
            length = math.sqrt(velocity.x ** 2 + velocity.y ** 2)
            velocity.x = (velocity.x / length) * PLAYER_SPEED
            velocity.y = (velocity.y / length) * PLAYER_SPEED
        
        # Apply predicted movement
        self.local_position.x += velocity.x * delta_time
        self.local_position.y += velocity.y * delta_time
        
        # Clamp to world bounds
        half_size = PLAYER_SIZE / 2
        self.local_position.x = max(half_size, min(WORLD_WIDTH - half_size, self.local_position.x))
        self.local_position.y = max(half_size, min(WORLD_HEIGHT - half_size, self.local_position.y))
        
        # Client-side coin collection prediction
        # Check if we're touching any coins and predict collection
        for coin_id, coin in list(self.coins.items()):
            if coin_id in self.predicted_collected_coins:
                continue  # Already predicted this one
            
            dx = self.local_position.x - coin.position.x
            dy = self.local_position.y - coin.position.y
            distance = math.sqrt(dx * dx + dy * dy)
            
            if distance < COIN_PICKUP_RADIUS:
                # Predict we collected this coin!
                self.predicted_collected_coins.add(coin_id)
                print(f"[CLIENT] Predicted coin collection: {coin_id[:8]}")
    
    def render(self):
        """Render the current game state."""
        if self.state == GameState.CONNECTING:
            self.renderer.render_connecting()
        
        elif self.state == GameState.LOBBY:
            self.renderer.render_lobby(
                self.lobby_player_count,
                self.lobby_required,
                self.lobby_player_names,
                self.countdown
            )
        
        elif self.state == GameState.PLAYING:
            self.render_game()
        
        elif self.state == GameState.GAME_OVER:
            self.render_game()  # Render game in background
            self.renderer.render_game_over(
                self.winner_name,
                self.final_scores,
                list(self.players.values())
            )
        
        elif self.state == GameState.DISCONNECTED:
            self.renderer.render_disconnected()
        
        # Always show latency indicator (using measured latency)
        self.renderer.render_latency_indicator(self.measured_latency_ms)
    
    def render_game(self):
        """Render the main game."""
        # Background
        self.renderer.render_background()
        
        # Get interpolated positions for remote players
        render_time = time.time()
        interpolated_positions = self.interpolation.get_render_positions(render_time)
        
        # Render coins (skip predicted collected ones for instant feedback)
        visible_coins = [(cid, coin) for cid, coin in self.coins.items() 
                         if cid not in self.predicted_collected_coins]
        for i, (coin_id, coin) in enumerate(visible_coins):
            self.renderer.render_coin(coin.position, pulse_offset=i * 0.5)
        
        # Render players
        for player_id, player_state in self.players.items():
            if player_id == self.local_player_id:
                # Render local player with predicted position
                self.renderer.render_player(
                    self.local_position,
                    self.local_color_index,
                    self.player_name,
                    self.local_score,
                    is_local=True
                )
            else:
                # Render remote player with interpolated position
                position = interpolated_positions.get(player_id, player_state.position)
                self.renderer.render_player(
                    position,
                    player_state.color_index,
                    player_state.name,
                    player_state.score,
                    is_local=False
                )
        
        # Render HUD
        self.renderer.render_hud(
            list(self.players.values()),
            self.time_remaining,
            self.local_player_id or ""
        )
    
    def cleanup(self):
        """Clean up resources."""
        print("[CLIENT] Shutting down...")
        self.network.disconnect()
        pygame.quit()


def main():
    """Entry point for the client."""
    # Get player name from command line or use default
    if len(sys.argv) > 1:
        player_name = sys.argv[1]
    else:
        # Generate random name
        adjectives = ["Swift", "Brave", "Clever", "Lucky", "Bold", "Quick"]
        nouns = ["Fox", "Bear", "Wolf", "Eagle", "Lion", "Tiger"]
        player_name = f"{random.choice(adjectives)}{random.choice(nouns)}"
    
    print("=" * 50)
    print("  COIN COLLECTOR - Game Client")
    print(f"  Player: {player_name}")
    print("=" * 50)
    
    # Create and start client
    client = CoinCollectorClient(player_name)
    client.start()


if __name__ == "__main__":
    main()
