"""
Pygame renderer for Coin Collector.
Draws players, coins, HUD and simple effects. Comments edited for a
more human, slightly imperfect tone.
"""

import pygame
import math
from typing import Dict, List, Optional, Tuple

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.constants import (
    WORLD_WIDTH, WORLD_HEIGHT, PLAYER_SIZE, PLAYER_COLORS,
    COIN_SIZE, COIN_COLOR
)
from shared.protocol import Vector2, PlayerState, CoinState


# Color definitions
BACKGROUND_COLOR = (30, 30, 40)
GRID_COLOR = (50, 50, 60)
TEXT_COLOR = (255, 255, 255)
SCORE_BG_COLOR = (20, 20, 30, 200)
LOBBY_BG_COLOR = (40, 40, 50)


class GameRenderer:
    """Handles all Pygame rendering for the game."""
    
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.width = screen.get_width()
        self.height = screen.get_height()
        
        # Initialize fonts
        pygame.font.init()
        self.font_large = pygame.font.Font(None, 48)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 24)
        
        # Pre-render some text
        self.title_text = self.font_large.render("COIN COLLECTOR", True, (255, 215, 0))
    
    def render_background(self):
        """Render the game background with grid."""
        self.screen.fill(BACKGROUND_COLOR)
        
        # Draw grid
        grid_spacing = 50
        for x in range(0, WORLD_WIDTH + 1, grid_spacing):
            pygame.draw.line(self.screen, GRID_COLOR, (x, 0), (x, WORLD_HEIGHT))
        for y in range(0, WORLD_HEIGHT + 1, grid_spacing):
            pygame.draw.line(self.screen, GRID_COLOR, (0, y), (WORLD_WIDTH, y))
    
    def render_player(self, position: Vector2, color_index: int, name: str, 
                      score: int, is_local: bool = False):
        """Render a player circle with name and score."""
        color = PLAYER_COLORS[color_index % len(PLAYER_COLORS)]
        x, y = int(position.x), int(position.y)
        radius = PLAYER_SIZE // 2
        
        # Draw outer glow for local player
        if is_local:
            glow_color = tuple(min(255, c + 50) for c in color)
            pygame.draw.circle(self.screen, glow_color, (x, y), radius + 4)
        
        # Draw main circle
        pygame.draw.circle(self.screen, color, (x, y), radius)
        
        # Draw border
        border_color = tuple(min(255, c + 80) for c in color)
        pygame.draw.circle(self.screen, border_color, (x, y), radius, 3)
        
        # Draw name above player
        name_surface = self.font_small.render(name, True, TEXT_COLOR)
        name_rect = name_surface.get_rect(centerx=x, bottom=y - radius - 5)
        self.screen.blit(name_surface, name_rect)
        
        # Draw score inside player
        score_surface = self.font_small.render(str(score), True, TEXT_COLOR)
        score_rect = score_surface.get_rect(center=(x, y))
        self.screen.blit(score_surface, score_rect)
    
    def render_coin(self, position: Vector2, pulse_offset: float = 0):
        """Render a coin with optional pulsing animation."""
        x, y = int(position.x), int(position.y)
        base_radius = COIN_SIZE // 2
        
        # Pulsing effect
        pulse = math.sin(pygame.time.get_ticks() / 200.0 + pulse_offset) * 2
        radius = int(base_radius + pulse)
        
        # Draw glow
        glow_surface = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
        glow_color = (*COIN_COLOR, 50)
        pygame.draw.circle(glow_surface, glow_color, (radius * 2, radius * 2), radius * 2)
        self.screen.blit(glow_surface, (x - radius * 2, y - radius * 2))
        
        # Draw main coin
        pygame.draw.circle(self.screen, COIN_COLOR, (x, y), radius)
        
        # Draw inner circle for 3D effect
        inner_color = (255, 235, 100)
        pygame.draw.circle(self.screen, inner_color, (x - 2, y - 2), radius - 4)
        
        # Draw shine
        shine_color = (255, 255, 200)
        pygame.draw.circle(self.screen, shine_color, (x - 3, y - 3), 3)
    
    def render_hud(self, players: List[PlayerState], time_remaining: float, 
                   local_player_id: str):
        """Render the heads-up display with scores and time."""
        # Draw semi-transparent background for HUD
        hud_surface = pygame.Surface((200, 30 + len(players) * 25), pygame.SRCALPHA)
        hud_surface.fill((20, 20, 30, 200))
        self.screen.blit(hud_surface, (10, 10))
        
        # Draw timer
        minutes = int(time_remaining) // 60
        seconds = int(time_remaining) % 60
        timer_text = f"Time: {minutes:02d}:{seconds:02d}"
        timer_surface = self.font_small.render(timer_text, True, TEXT_COLOR)
        self.screen.blit(timer_surface, (20, 15))
        
        # Draw scores
        sorted_players = sorted(players, key=lambda p: p.score, reverse=True)
        for i, player in enumerate(sorted_players):
            color = PLAYER_COLORS[player.color_index % len(PLAYER_COLORS)]
            
            # Highlight local player
            if player.id == local_player_id:
                name_text = f"► {player.name}: {player.score}"
            else:
                name_text = f"  {player.name}: {player.score}"
            
            text_surface = self.font_small.render(name_text, True, color)
            self.screen.blit(text_surface, (20, 40 + i * 25))
    
    def render_lobby(self, player_count: int, required: int, player_names: List[str],
                     countdown: Optional[int] = None):
        """Render the lobby waiting screen."""
        self.screen.fill(LOBBY_BG_COLOR)
        
        # Title
        title_rect = self.title_text.get_rect(centerx=self.width // 2, y=100)
        self.screen.blit(self.title_text, title_rect)
        
        # Waiting message
        if countdown is not None:
            wait_text = f"Game starting in {countdown}..."
            wait_color = (100, 255, 100)
        else:
            wait_text = f"Waiting for players... ({player_count}/{required})"
            wait_color = TEXT_COLOR
        
        wait_surface = self.font_medium.render(wait_text, True, wait_color)
        wait_rect = wait_surface.get_rect(centerx=self.width // 2, y=180)
        self.screen.blit(wait_surface, wait_rect)
        
        # Player list
        players_title = self.font_small.render("Connected Players:", True, TEXT_COLOR)
        self.screen.blit(players_title, (self.width // 2 - 80, 250))
        
        for i, name in enumerate(player_names):
            color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
            name_surface = self.font_small.render(f"• {name}", True, color)
            self.screen.blit(name_surface, (self.width // 2 - 60, 280 + i * 30))
        
        # Instructions
        instr_text = "Use WASD or Arrow Keys to move"
        instr_surface = self.font_small.render(instr_text, True, (150, 150, 150))
        instr_rect = instr_surface.get_rect(centerx=self.width // 2, y=self.height - 50)
        self.screen.blit(instr_surface, instr_rect)
    
    def render_game_over(self, winner_name: str, final_scores: Dict[str, int],
                         players: List[PlayerState]):
        """Render the game over screen."""
        # Darken background
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        # Game Over text
        go_text = self.font_large.render("GAME OVER", True, (255, 50, 50))
        go_rect = go_text.get_rect(centerx=self.width // 2, y=150)
        self.screen.blit(go_text, go_rect)
        
        # Winner announcement
        winner_text = f"Winner: {winner_name}!"
        winner_surface = self.font_medium.render(winner_text, True, (255, 215, 0))
        winner_rect = winner_surface.get_rect(centerx=self.width // 2, y=220)
        self.screen.blit(winner_surface, winner_rect)
        
        # Final scores
        scores_title = self.font_small.render("Final Scores:", True, TEXT_COLOR)
        self.screen.blit(scores_title, (self.width // 2 - 60, 280))
        
        # Sort players by score
        sorted_players = sorted(players, key=lambda p: p.score, reverse=True)
        for i, player in enumerate(sorted_players):
            color = PLAYER_COLORS[player.color_index % len(PLAYER_COLORS)]
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "  "
            score_text = f"{i+1}. {player.name}: {player.score}"
            score_surface = self.font_small.render(score_text, True, color)
            self.screen.blit(score_surface, (self.width // 2 - 60, 310 + i * 30))
        
        # Restart hint
        hint_text = "Press SPACE to play again or ESC to quit"
        hint_surface = self.font_small.render(hint_text, True, (150, 150, 150))
        hint_rect = hint_surface.get_rect(centerx=self.width // 2, y=self.height - 50)
        self.screen.blit(hint_surface, hint_rect)
    
    def render_connecting(self):
        """Render connecting screen."""
        self.screen.fill(LOBBY_BG_COLOR)
        
        # Title
        title_rect = self.title_text.get_rect(centerx=self.width // 2, y=200)
        self.screen.blit(self.title_text, title_rect)
        
        # Connecting text with animated dots
        dots = "." * ((pygame.time.get_ticks() // 500) % 4)
        connect_text = f"Connecting to server{dots}"
        connect_surface = self.font_medium.render(connect_text, True, TEXT_COLOR)
        connect_rect = connect_surface.get_rect(centerx=self.width // 2, y=280)
        self.screen.blit(connect_surface, connect_rect)
    
    def render_disconnected(self):
        """Render disconnected screen."""
        self.screen.fill((50, 30, 30))
        
        # Error text
        error_text = "Connection Lost!"
        error_surface = self.font_large.render(error_text, True, (255, 100, 100))
        error_rect = error_surface.get_rect(centerx=self.width // 2, y=250)
        self.screen.blit(error_surface, error_rect)
        
        # Hint
        hint_text = "Press SPACE to reconnect or ESC to quit"
        hint_surface = self.font_small.render(hint_text, True, (150, 150, 150))
        hint_rect = hint_surface.get_rect(centerx=self.width // 2, y=320)
        self.screen.blit(hint_surface, hint_rect)
    
    def render_latency_indicator(self, latency_ms: int):
        """Render a latency indicator in the corner."""
        # Color based on latency
        if latency_ms < 100:
            color = (100, 255, 100)  # Green
        elif latency_ms < 200:
            color = (255, 255, 100)  # Yellow
        else:
            color = (255, 100, 100)  # Red
        
        latency_text = f"Latency: {latency_ms}ms"
        latency_surface = self.font_small.render(latency_text, True, color)
        self.screen.blit(latency_surface, (self.width - 130, 10))
