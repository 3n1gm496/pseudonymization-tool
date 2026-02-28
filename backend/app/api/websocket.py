"""WebSocket endpoint for real-time batch processing updates."""

from __future__ import annotations

import asyncio
import json
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Track active WebSocket connections per batch_id
_active_connections: Dict[str, Set[WebSocket]] = {}


class ConnectionManager:
    """Manages WebSocket connections for batch progress updates."""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, batch_id: str, websocket: WebSocket):
        """Connect a client to batch updates."""
        await websocket.accept()
        
        if batch_id not in self.active_connections:
            self.active_connections[batch_id] = set()
        
        self.active_connections[batch_id].add(websocket)
        logger.info(f"WebSocket connected for batch {batch_id}", 
                   connections=len(self.active_connections[batch_id]))
    
    def disconnect(self, batch_id: str, websocket: WebSocket):
        """Disconnect a client from batch updates."""
        if batch_id in self.active_connections:
            self.active_connections[batch_id].discard(websocket)
            
            if not self.active_connections[batch_id]:
                del self.active_connections[batch_id]
            
            logger.info(f"WebSocket disconnected for batch {batch_id}")
    
    async def broadcast_to_batch(self, batch_id: str, message: dict):
        """Broadcast a message to all clients watching a batch."""
        if batch_id not in self.active_connections:
            return
        
        message_json = json.dumps(message)
        dead_connections = set()
        
        for connection in self.active_connections[batch_id]:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.error(f"Error sending WebSocket message: {e}")
                dead_connections.add(connection)
        
        # Clean up dead connections
        for dead_conn in dead_connections:
            self.disconnect(batch_id, dead_conn)
    
    async def send_progress_update(
        self,
        batch_id: str,
        file_name: str,
        progress: int,
        total_files: int,
        status: str,
        findings_count: int = 0
    ):
        """Send a progress update to all clients watching a batch."""
        await self.broadcast_to_batch(batch_id, {
            "type": "progress",
            "batch_id": batch_id,
            "file_name": file_name,
            "progress": progress,
            "total_files": total_files,
            "status": status,
            "findings_count": findings_count,
            "percentage": round((progress / total_files) * 100) if total_files > 0 else 0
        })
    
    async def send_completion(self, batch_id: str, results: dict):
        """Send batch completion notification."""
        await self.broadcast_to_batch(batch_id, {
            "type": "complete",
            "batch_id": batch_id,
            "results": results
        })
    
    async def send_error(self, batch_id: str, error_message: str):
        """Send error notification."""
        await self.broadcast_to_batch(batch_id, {
            "type": "error",
            "batch_id": batch_id,
            "error": error_message
        })


# Global connection manager instance
manager = ConnectionManager()


@router.websocket("/ws/batch/{batch_id}")
async def websocket_batch_updates(websocket: WebSocket, batch_id: str):
    """WebSocket endpoint for real-time batch processing updates.
    
    Clients connect with batch_id and receive:
    - progress updates as files are processed
    - completion notification when batch finishes
    - error notifications if issues occur
    """
    await manager.connect(batch_id, websocket)
    
    try:
        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client ping/pong to keep connection alive
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                
                # Echo back ping messages
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            
            except asyncio.TimeoutError:
                # Send keepalive if no client activity
                try:
                    await websocket.send_text(json.dumps({
                        "type": "keepalive",
                        "batch_id": batch_id
                    }))
                except:
                    break
    
    except WebSocketDisconnect:
        manager.disconnect(batch_id, websocket)
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(batch_id, websocket)


def get_websocket_manager() -> ConnectionManager:
    """Get the global WebSocket connection manager."""
    return manager
