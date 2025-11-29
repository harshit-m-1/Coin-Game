"""
Server-side game state manager: authoritative players, coins, scores.
Single source of truth for all mutable game data.
"""

import time
import uuid
import random
import math
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.constants import (
    WORLD_WIDTH, WORLD_HEIGHT, PLAYER_SIZE, PLAYER_SPEED,
    COIN_SIZE, COIN_PICKUP_RADIUS, MAX_COINS, COIN_SPAWN_INTERVAL,
    GAME_DURATION, MIN_PLAYERS, PLAYER_COLORS
)
from shared.protocol import (
    Vector2, PlayerState, CoinState, GameStateSnapshot, InputDirection
)


@dataclass
class Player:
    """Server-side player representation."""
    id: str
    name: str
    position: Vector2
    velocity: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    score: int = 0
    color_index: int = 0
    active_inputs: Set[InputDirection] = field(default_factory=set)
    last_input_sequence: int = 0
    
    def to_state(self) -> PlayerState:
        """Convert to PlayerState for network transmission."""
        return PlayerState(
            id=self.id,
            position=Vector2(self.position.x, self.position.y),
            score=self.score,
            color_index=self.color_index,
            name=self.name
        )


@dataclass
class Coin:
    """Server-side coin representation."""
    id: str
    position: Vector2
    spawn_time: float
    
    def to_state(self) -> CoinState:
        """Convert to CoinState for network transmission."""
        return CoinState(
            id=self.id,
            position=Vector2(self.position.x, self.position.y)
        )


class GameState:
    """
    Authoritative game state manager.
    All game logic and validation happens here.
    """
    
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.coins: Dict[str, Coin] = {}
        
        # Game timing
        self.game_started: bool = False
        self.game_over: bool = False
        self.game_start_time: float = 0
        self.last_coin_spawn: float = 0
        self.last_update_time: float = time.time()
        
        # Color assignment tracking
        self.next_color_index: int = 0
    
    def add_player(self, player_id: str, name: str) -> Player:
        """Add a new player to the game."""
        # Find spawn position (spread players out)
        spawn_positions = [
            Vector2(WORLD_WIDTH * 0.25, WORLD_HEIGHT * 0.25),
            Vector2(WORLD_WIDTH * 0.75, WORLD_HEIGHT * 0.25),
            Vector2(WORLD_WIDTH * 0.25, WORLD_HEIGHT * 0.75),
            Vector2(WORLD_WIDTH * 0.75, WORLD_HEIGHT * 0.75),
        ]
        
        player_count = len(self.players)
        spawn_pos = spawn_positions[player_count % len(spawn_positions)]
        
        # Assign color
        color_index = self.next_color_index % len(PLAYER_COLORS)
        self.next_color_index += 1
        
        player = Player(
            id=player_id,
            name=name,
            position=spawn_pos,
            color_index=color_index
        )
        
        self.players[player_id] = player
        return player
    
    def remove_player(self, player_id: str) -> Optional[Player]:
        """Remove a player from the game."""
        return self.players.pop(player_id, None)
    
    def get_player(self, player_id: str) -> Optional[Player]:
        """Get a player by ID."""
        return self.players.get(player_id)
    
    def process_input(self, player_id: str, directions: List[InputDirection], sequence: int):
        """
        Process player input - SERVER AUTHORITATIVE.
        Client only sends intent, server validates and applies.
        """
        player = self.players.get(player_id)
        if not player or self.game_over or not self.game_started:
            return
        
        # Only process if this is a newer input
        if sequence <= player.last_input_sequence:
            return
        
        player.last_input_sequence = sequence
        player.active_inputs = set(directions)
    
    def update(self, delta_time: float) -> List[Dict]:
        """
        Update game state - called every server tick.
        Returns list of events that occurred (coin pickups, etc.)
        """
        events = []
        
        if not self.game_started or self.game_over:
            return events
        
        current_time = time.time()
        
        # Update player positions based on their inputs
        for player in self.players.values():
            velocity = Vector2(0, 0)
            
            if InputDirection.UP in player.active_inputs:
                velocity.y -= PLAYER_SPEED
            if InputDirection.DOWN in player.active_inputs:
                velocity.y += PLAYER_SPEED
            if InputDirection.LEFT in player.active_inputs:
                velocity.x -= PLAYER_SPEED
            if InputDirection.RIGHT in player.active_inputs:
                velocity.x += PLAYER_SPEED
            
            # Normalize diagonal movement
            if velocity.x != 0 and velocity.y != 0:
                length = math.sqrt(velocity.x ** 2 + velocity.y ** 2)
                velocity.x = (velocity.x / length) * PLAYER_SPEED
                velocity.y = (velocity.y / length) * PLAYER_SPEED
            
            # Apply velocity
            new_x = player.position.x + velocity.x * delta_time
            new_y = player.position.y + velocity.y * delta_time
            
            # Clamp to world bounds
            half_size = PLAYER_SIZE / 2
            player.position.x = max(half_size, min(WORLD_WIDTH - half_size, new_x))
            player.position.y = max(half_size, min(WORLD_HEIGHT - half_size, new_y))
        
        # Check coin collisions - SERVER AUTHORITATIVE
        # Use a set to track which coins to remove (prevents double collection)
        coins_to_remove = set()
        for coin_id, coin in self.coins.items():
            if coin_id in coins_to_remove:
                continue  # Already being collected this tick
                
            for player in self.players.values():
                # Calculate distance between player and coin centers
                dx = player.position.x - coin.position.x
                dy = player.position.y - coin.position.y
                distance = math.sqrt(dx * dx + dy * dy)
                
                if distance < COIN_PICKUP_RADIUS:
                    # Coin collected!
                    player.score += 1
                    coins_to_remove.add(coin_id)
                    events.append({
                        "type": "coin_collected",
                        "coin_id": coin_id,
                        "player_id": player.id,
                        "new_score": player.score
                    })
                    break  # Only one player can collect a coin
        
        for coin_id in coins_to_remove:
            del self.coins[coin_id]
        
        # Spawn new coins periodically
        if current_time - self.last_coin_spawn >= COIN_SPAWN_INTERVAL:
            if len(self.coins) < MAX_COINS:
                self._spawn_coin()
            self.last_coin_spawn = current_time
        
        # Check game over condition
        elapsed = current_time - self.game_start_time
        if elapsed >= GAME_DURATION:
            self.game_over = True
            events.append({"type": "game_over"})
        
        return events
    
    def _spawn_coin(self):
        """Spawn a new coin at a random position."""
        margin = COIN_SIZE
        coin = Coin(
            id=str(uuid.uuid4())[:8],
            position=Vector2(
                random.uniform(margin, WORLD_WIDTH - margin),
                random.uniform(margin, WORLD_HEIGHT - margin)
            ),
            spawn_time=time.time()
        )
        self.coins[coin.id] = coin
    
    def start_game(self):
        """Start the game."""
        self.game_started = True
        self.game_start_time = time.time()
        self.last_coin_spawn = time.time()
        
        # Spawn initial coins
        for _ in range(3):
            self._spawn_coin()
    
    def get_time_remaining(self) -> float:
        """Get remaining game time in seconds."""
        if not self.game_started:
            return GAME_DURATION
        elapsed = time.time() - self.game_start_time
        return max(0, GAME_DURATION - elapsed)
    
    def get_snapshot(self) -> GameStateSnapshot:
        """Get current game state snapshot for network transmission."""
        return GameStateSnapshot(
            timestamp=time.time(),
            server_time=time.time(),
            players=[p.to_state() for p in self.players.values()],
            coins=[c.to_state() for c in self.coins.values()],
            game_time_remaining=self.get_time_remaining(),
            game_started=self.game_started,
            game_over=self.game_over
        )
    
    def get_winner(self) -> Optional[Player]:
        """Get the player with the highest score."""
        if not self.players:
            return None
        return max(self.players.values(), key=lambda p: p.score)
    
    def can_start(self) -> bool:
        """Check if game can start (enough players)."""
        return len(self.players) >= MIN_PLAYERS
    
    def reset(self):
        """Reset the game state for a new game."""
        self.players.clear()
        self.coins.clear()
        self.game_started = False
        self.game_over = False
        self.game_start_time = 0
        self.last_coin_spawn = 0
        self.next_color_index = 0
