"""
Network protocol definitions for client-server messages.
Message types, dataclasses, and helper factory functions.
"""

from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import json


class MessageType(str, Enum):
    """All possible message types in the protocol."""
    
    # Client -> Server messages
    JOIN = "join"                    # Client wants to join the game
    INPUT = "input"                  # Client sends movement input
    LEAVE = "leave"                  # Client disconnects
    
    # Server -> Client messages
    WELCOME = "welcome"              # Server acknowledges join, sends player ID
    LOBBY_UPDATE = "lobby_update"    # Update on lobby status
    GAME_START = "game_start"        # Game is starting
    GAME_STATE = "game_state"        # Full game state update
    PLAYER_JOINED = "player_joined"  # Another player joined
    PLAYER_LEFT = "player_left"      # Another player left
    COIN_SPAWNED = "coin_spawned"    # New coin appeared
    COIN_COLLECTED = "coin_collected"  # A coin was collected
    SCORE_UPDATE = "score_update"    # Score changed
    GAME_OVER = "game_over"          # Game ended


class InputDirection(str, Enum):
    """Movement input directions."""
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    NONE = "none"


@dataclass
class Vector2:
    """2D vector/position."""
    x: float
    y: float
    
    def to_dict(self) -> Dict[str, float]:
        return {"x": self.x, "y": self.y}
    
    @staticmethod
    def from_dict(data: Dict[str, float]) -> "Vector2":
        return Vector2(x=data["x"], y=data["y"])


@dataclass
class PlayerState:
    """State of a single player."""
    id: str
    position: Vector2
    score: int
    color_index: int
    name: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "position": self.position.to_dict(),
            "score": self.score,
            "color_index": self.color_index,
            "name": self.name
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "PlayerState":
        return PlayerState(
            id=data["id"],
            position=Vector2.from_dict(data["position"]),
            score=data["score"],
            color_index=data["color_index"],
            name=data["name"]
        )


@dataclass
class CoinState:
    """State of a single coin."""
    id: str
    position: Vector2
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "position": self.position.to_dict()
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "CoinState":
        return CoinState(
            id=data["id"],
            position=Vector2.from_dict(data["position"])
        )


@dataclass
class GameStateSnapshot:
    """Complete game state at a point in time."""
    timestamp: float
    server_time: float
    players: List[PlayerState]
    coins: List[CoinState]
    game_time_remaining: float
    game_started: bool
    game_over: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "server_time": self.server_time,
            "players": [p.to_dict() for p in self.players],
            "coins": [c.to_dict() for c in self.coins],
            "game_time_remaining": self.game_time_remaining,
            "game_started": self.game_started,
            "game_over": self.game_over
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "GameStateSnapshot":
        return GameStateSnapshot(
            timestamp=data["timestamp"],
            server_time=data["server_time"],
            players=[PlayerState.from_dict(p) for p in data["players"]],
            coins=[CoinState.from_dict(c) for c in data["coins"]],
            game_time_remaining=data["game_time_remaining"],
            game_started=data["game_started"],
            game_over=data["game_over"]
        )


class Message:
    """Base message class for all network communication."""
    
    def __init__(self, msg_type: MessageType, data: Optional[Dict[str, Any]] = None):
        self.type = msg_type
        self.data = data or {}
    
    def to_json(self) -> str:
        """Serialize message to JSON string."""
        return json.dumps({
            "type": self.type.value,
            "data": self.data
        })
    
    @staticmethod
    def from_json(json_str: str) -> "Message":
        """Deserialize message from JSON string."""
        obj = json.loads(json_str)
        return Message(
            msg_type=MessageType(obj["type"]),
            data=obj.get("data", {})
        )


# =============================================================================
# MESSAGE FACTORIES - Convenience functions to create specific messages
# =============================================================================

def create_join_message(player_name: str) -> Message:
    """Create a join request message."""
    return Message(MessageType.JOIN, {"name": player_name})


def create_input_message(directions: List[InputDirection], sequence: int) -> Message:
    """Create an input message with movement directions."""
    return Message(MessageType.INPUT, {
        "directions": [d.value for d in directions],
        "sequence": sequence
    })


def create_welcome_message(player_id: str, color_index: int) -> Message:
    """Create a welcome message for a new player."""
    return Message(MessageType.WELCOME, {
        "player_id": player_id,
        "color_index": color_index
    })


def create_lobby_update_message(player_count: int, required: int, names: List[str]) -> Message:
    """Create a lobby status update message."""
    return Message(MessageType.LOBBY_UPDATE, {
        "player_count": player_count,
        "required": required,
        "player_names": names
    })


def create_game_start_message(countdown: int) -> Message:
    """Create a game start countdown message."""
    return Message(MessageType.GAME_START, {"countdown": countdown})


def create_game_state_message(state: GameStateSnapshot) -> Message:
    """Create a full game state message."""
    return Message(MessageType.GAME_STATE, state.to_dict())


def create_coin_collected_message(coin_id: str, collector_id: str, new_score: int) -> Message:
    """Create a coin collected notification message."""
    return Message(MessageType.COIN_COLLECTED, {
        "coin_id": coin_id,
        "collector_id": collector_id,
        "new_score": new_score
    })


def create_game_over_message(winner_id: str, winner_name: str, final_scores: Dict[str, int]) -> Message:
    """Create a game over message."""
    return Message(MessageType.GAME_OVER, {
        "winner_id": winner_id,
        "winner_name": winner_name,
        "final_scores": final_scores
    })
