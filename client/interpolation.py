"""
Entity interpolation system — keeps other players moving smooth.
We buffer server updates and lerp between them. Comments made
to sound more like a quick dev note (may be slightly rough).
"""

import time
from typing import Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass, field

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.protocol import Vector2, PlayerState, GameStateSnapshot
from shared.constants import INTERPOLATION_BUFFER_SIZE, INTERPOLATION_DELAY


@dataclass
class InterpolatedEntity:
    """
    An entity that can be interpolated between network updates.
    Stores a buffer of past positions for smooth rendering.
    """
    entity_id: str
    position_buffer: deque = field(default_factory=lambda: deque(maxlen=20))
    current_position: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    target_position: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    
    def add_snapshot(self, position: Vector2, timestamp: float):
        """Add a new position snapshot to the buffer."""
        self.position_buffer.append((timestamp, position))
    
    def get_interpolated_position(self, render_time: float) -> Vector2:
        """
        Get the interpolated position at a specific render time.
        Uses linear interpolation between buffered positions.
        """
        if len(self.position_buffer) < 2:
            # Not enough data, return latest known position
            if self.position_buffer:
                return self.position_buffer[-1][1]
            return self.current_position
        
        # Find the two snapshots to interpolate between
        # render_time should be slightly in the past
        before: Optional[Tuple[float, Vector2]] = None
        after: Optional[Tuple[float, Vector2]] = None
        
        for i, (timestamp, position) in enumerate(self.position_buffer):
            if timestamp <= render_time:
                before = (timestamp, position)
            else:
                after = (timestamp, position)
                break
        
        # Handle edge cases
        if before is None:
            # All snapshots are in the future, use the oldest
            return self.position_buffer[0][1]
        
        if after is None:
            # All snapshots are in the past, extrapolate from the last two
            if len(self.position_buffer) >= 2:
                t1, p1 = self.position_buffer[-2]
                t2, p2 = self.position_buffer[-1]
                
                # Calculate velocity and extrapolate
                dt = t2 - t1
                if dt > 0:
                    velocity_x = (p2.x - p1.x) / dt
                    velocity_y = (p2.y - p1.y) / dt
                    
                    # Limit extrapolation to prevent wild predictions
                    time_since = min(render_time - t2, 0.2)  # Max 200ms extrapolation
                    
                    return Vector2(
                        p2.x + velocity_x * time_since,
                        p2.y + velocity_y * time_since
                    )
            
            return self.position_buffer[-1][1]
        
        # Linear interpolation between before and after
        t0, p0 = before
        t1, p1 = after
        
        # Calculate interpolation factor
        dt = t1 - t0
        if dt <= 0:
            return p1
        
        t = (render_time - t0) / dt
        t = max(0, min(1, t))  # Clamp to [0, 1]
        
        # Interpolate
        return Vector2(
            p0.x + (p1.x - p0.x) * t,
            p0.y + (p1.y - p0.y) * t
        )


class InterpolationManager:
    """
    Manages interpolation for all remote entities in the game.
    Local player uses client-side prediction, remote players use interpolation.
    """
    
    def __init__(self, local_player_id: str = ""):
        self.local_player_id = local_player_id
        self.entities: Dict[str, InterpolatedEntity] = {}
        self.render_delay = INTERPOLATION_DELAY  # Render slightly in the past
        
        # Local player state (uses client-side prediction)
        self.local_position: Vector2 = Vector2(0, 0)
        self.local_velocity: Vector2 = Vector2(0, 0)
        
        # Server reconciliation
        self.last_server_position: Vector2 = Vector2(0, 0)
        self.pending_inputs: deque = deque()
    
    def set_local_player(self, player_id: str):
        """Set the local player ID."""
        self.local_player_id = player_id
    
    def process_game_state(self, state: GameStateSnapshot):
        """
        Process a new game state snapshot from the server.
        Updates interpolation buffers for all remote entities.
        """
        server_time = state.server_time
        
        for player_state in state.players:
            player_id = player_state.id
            position = player_state.position
            
            if player_id == self.local_player_id:
                # For local player, use for server reconciliation
                self.last_server_position = position
                # Could implement reconciliation here if needed
                continue
            
            # Remote player - add to interpolation buffer
            if player_id not in self.entities:
                self.entities[player_id] = InterpolatedEntity(entity_id=player_id)
            
            self.entities[player_id].add_snapshot(position, server_time)
    
    def get_render_positions(self, current_time: float) -> Dict[str, Vector2]:
        """
        Get interpolated positions for all entities at the current render time.
        """
        render_time = current_time - self.render_delay
        positions = {}
        
        for entity_id, entity in self.entities.items():
            positions[entity_id] = entity.get_interpolated_position(render_time)
        
        return positions
    
    def remove_entity(self, entity_id: str):
        """Remove an entity from interpolation tracking."""
        self.entities.pop(entity_id, None)
    
    def clear(self):
        """Clear all interpolation data."""
        self.entities.clear()


class ClientSidePrediction:
    """
    Client-side prediction for the local player.
    Provides immediate response to inputs while waiting for server confirmation.
    """
    
    def __init__(self):
        self.position: Vector2 = Vector2(0, 0)
        self.pending_inputs: deque = deque()
        self.last_processed_sequence: int = 0
    
    def apply_input(self, velocity: Vector2, delta_time: float, sequence: int):
        """Apply an input locally and store for reconciliation."""
        # Move locally
        self.position.x += velocity.x * delta_time
        self.position.y += velocity.y * delta_time
        
        # Store for reconciliation
        self.pending_inputs.append({
            'sequence': sequence,
            'velocity': velocity,
            'delta_time': delta_time
        })
    
    def reconcile_with_server(self, server_position: Vector2, last_sequence: int):
        """
        Reconcile local position with authoritative server position.
        Re-applies pending inputs that server hasn't processed yet.
        """
        # Remove acknowledged inputs
        while self.pending_inputs and self.pending_inputs[0]['sequence'] <= last_sequence:
            self.pending_inputs.popleft()
        
        # Snap to server position
        self.position = Vector2(server_position.x, server_position.y)
        
        # Re-apply pending inputs
        for input_data in self.pending_inputs:
            velocity = input_data['velocity']
            dt = input_data['delta_time']
            self.position.x += velocity.x * dt
            self.position.y += velocity.y * dt
    
    def set_position(self, position: Vector2):
        """Set the current position (e.g., from server)."""
        self.position = Vector2(position.x, position.y)
