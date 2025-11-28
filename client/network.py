"""
WebSocket network client for Coin Collector.
Manages comms with server. Latency is simulated with delayed queues
so the main thread doesn't freeze (not using blocking sleeps).
"""

import asyncio
import json
import time
import threading
from typing import Optional, List
from queue import Queue, Empty
from collections import deque

import websockets

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.constants import SERVER_HOST, SERVER_PORT, SIMULATED_LATENCY
from shared.protocol import (
    Message, MessageType, InputDirection,
    create_join_message, create_input_message
)


class NetworkClient:
    """
    Handles WebSocket communication with the game server.
    Runs networking in a separate thread to not block the game loop.
    Latency is simulated using delayed queues (non-blocking).
    """
    
    def __init__(self):
        self.websocket = None
        self.connected = False
        self.player_id: Optional[str] = None
        self.color_index: int = 0
        
        # Message queues for thread-safe communication
        self.incoming_messages: Queue = Queue()
        self.outgoing_messages: Queue = Queue()
        
        # Delayed queues for latency simulation (non-blocking)
        self.delayed_incoming: deque = deque()  # (deliver_at, message)
        self.delayed_outgoing: deque = deque()  # (deliver_at, json_str)
        
        # Threading
        self.network_thread: Optional[threading.Thread] = None
        self.running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Input tracking
        self.input_sequence = 0
    
    def connect(self, player_name: str):
        """Start connection to the server in a separate thread.
        Keeps the game loop responsive while networking runs."""
        self.running = True
        self.network_thread = threading.Thread(
            target=self._run_network_loop,
            args=(player_name,),
            daemon=True
        )
        self.network_thread.start()
    
    def _run_network_loop(self, player_name: str):
        """Run the asyncio event loop for networking."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self._connect_and_run(player_name))
        except Exception as e:
            print(f"[NETWORK] Error in network loop: {e}")
        finally:
            self.loop.close()
    
    async def _connect_and_run(self, player_name: str):
        """Connect to server and handle messages."""
        uri = f"ws://{SERVER_HOST}:{SERVER_PORT}"
        print(f"[NETWORK] Connecting to {uri}...")
        
        try:
            # Disable ping to avoid timeout issues with latency simulation
            async with websockets.connect(
                uri,
                ping_interval=None,  # Disable client-side ping
                ping_timeout=None
            ) as websocket:
                self.websocket = websocket
                self.connected = True
                print(f"[NETWORK] Connected!")
                
                # Send join message (with latency)
                join_msg = create_join_message(player_name)
                self._queue_outgoing(join_msg)
                
                # Run all tasks concurrently
                await asyncio.gather(
                    self._receive_loop(),
                    self._send_loop(),
                    self._process_delayed_incoming(),
                    self._process_delayed_outgoing()
                )
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[NETWORK] Connection closed: {e}")
        except Exception as e:
            print(f"[NETWORK] Connection error: {e}")
        finally:
            self.connected = False
    
    async def _receive_loop(self):
        """Receive messages from server and queue them with delay."""
        try:
            async for raw_message in self.websocket:
                # Queue message with simulated latency (non-blocking)
                deliver_at = time.time() + SIMULATED_LATENCY
                self.delayed_incoming.append((deliver_at, raw_message))
        except websockets.exceptions.ConnectionClosed:
            print("[NETWORK] Connection closed by server")
            self.connected = False
        except Exception as e:
            print(f"[NETWORK] Receive error: {e}")
            self.connected = False
    
    async def _process_delayed_incoming(self):
        """Process delayed incoming messages (simulates receive latency)."""
        while self.running and self.connected:
            current_time = time.time()
            
            # Process all messages that should be delivered by now
            while self.delayed_incoming and self.delayed_incoming[0][0] <= current_time:
                _, raw_message = self.delayed_incoming.popleft()
                try:
                    message = Message.from_json(raw_message)
                    self.incoming_messages.put(message)
                    
                    # Handle welcome message to get player ID
                    if message.type == MessageType.WELCOME:
                        self.player_id = message.data.get("player_id")
                        self.color_index = message.data.get("color_index", 0)
                        print(f"[NETWORK] Received player ID: {self.player_id}")
                        
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[NETWORK] Error parsing message: {e}")
            
            await asyncio.sleep(0.005)  # Check every 5ms
    
    async def _send_loop(self):
        """Check for outgoing messages from game thread."""
        while self.running and self.connected:
            try:
                # Check for outgoing messages (non-blocking)
                message = self.outgoing_messages.get_nowait()
                self._queue_outgoing(message)
            except Empty:
                pass
            
            await asyncio.sleep(0.005)
    
    def _queue_outgoing(self, message: Message):
        """Add message to delayed outgoing queue."""
        deliver_at = time.time() + SIMULATED_LATENCY
        self.delayed_outgoing.append((deliver_at, message.to_json()))
    
    async def _process_delayed_outgoing(self):
        """Process delayed outgoing messages (simulates send latency)."""
        while self.running and self.connected:
            current_time = time.time()
            
            while self.delayed_outgoing and self.delayed_outgoing[0][0] <= current_time:
                _, json_msg = self.delayed_outgoing.popleft()
                try:
                    await self.websocket.send(json_msg)
                except websockets.exceptions.ConnectionClosed:
                    self.connected = False
                    return
                except Exception as e:
                    print(f"[NETWORK] Error sending: {e}")
            
            await asyncio.sleep(0.005)
    
    def send_input(self, directions: List[InputDirection]):
        """Queue an input message to be sent to the server."""
        if not self.connected:
            return None
        
        self.input_sequence += 1
        message = create_input_message(directions, self.input_sequence)
        self.outgoing_messages.put(message)
        
        return self.input_sequence
    
    def get_messages(self) -> List[Message]:
        """Get all pending incoming messages (non-blocking)."""
        messages = []
        while True:
            try:
                message = self.incoming_messages.get_nowait()
                messages.append(message)
            except Empty:
                break
        return messages
    
    def disconnect(self):
        """Disconnect from the server."""
        self.running = False
        self.connected = False
        
        if self.network_thread and self.network_thread.is_alive():
            self.network_thread.join(timeout=1.0)
