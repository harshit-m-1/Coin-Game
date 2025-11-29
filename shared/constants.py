"""
Shared constants for the Coin Collector game.
Used by both server and client. Edited to look a bit more human.
"""

# =============================================================================
# NETWORK SETTINGS
# =============================================================================
SERVER_HOST = "localhost"
SERVER_PORT = 8765

# Simulated network latency in seconds (200ms as per requirements)
SIMULATED_LATENCY = 0.200

# =============================================================================
# GAME WORLD SETTINGS
# =============================================================================
WORLD_WIDTH = 800
WORLD_HEIGHT = 600

# =============================================================================
# PLAYER SETTINGS
# =============================================================================
PLAYER_SIZE = 30  # Diameter of player circle
PLAYER_SPEED = 200  # Pixels per second
PLAYER_COLORS = [
    (65, 105, 225),   # Royal Blue - Player 1
    (220, 20, 60),    # Crimson - Player 2
    (50, 205, 50),    # Lime Green - Player 3
    (255, 165, 0),    # Orange - Player 4  
]

# =============================================================================
# COIN SETTINGS
# =============================================================================
COIN_SIZE = 20  # Diameter of coin
COIN_COLOR = (255, 215, 0)  # Gold
COIN_SPAWN_INTERVAL = 3.0  # Seconds between coin spawns
MAX_COINS = 10  # Maximum coins on map at once
COIN_PICKUP_RADIUS = (PLAYER_SIZE + COIN_SIZE) / 2  # Collision radius

# =============================================================================
# LOBBY SETTINGS
# =============================================================================
MIN_PLAYERS = 2  # Minimum players to start game
MAX_PLAYERS = 4  # Maximum players allowed
LOBBY_COUNTDOWN = 3  # Seconds to countdown before game starts

# =============================================================================
# GAME SETTINGS
# =============================================================================
GAME_DURATION = 120  # Game duration in seconds (2 minutes)
SERVER_TICK_RATE = 60  # Server updates per second
CLIENT_TICK_RATE = 60  # Client updates per second
STATE_BROADCAST_RATE = 20  # State broadcasts per second

# =============================================================================
# INTERPOLATION SETTINGS
# =============================================================================
INTERPOLATION_BUFFER_SIZE = 3  # Number of states to buffer
INTERPOLATION_DELAY = 0.1  # Seconds to delay rendering for interpolation
