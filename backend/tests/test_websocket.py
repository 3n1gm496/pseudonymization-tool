"""Tests for WebSocket real-time updates."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket

from app.main import app
from app.api.websocket import manager, get_websocket_manager


@pytest.fixture
def test_client():
    """Provide test client."""
    return TestClient(app)


def test_websocket_manager_singleton():
    """Test that get_websocket_manager returns the same instance."""
    manager1 = get_websocket_manager()
    manager2 = get_websocket_manager()
    assert manager1 is manager2


@pytest.mark.asyncio
async def test_websocket_connect_disconnect():
    """Test WebSocket connection and disconnection."""
    batch_id = "test-batch-123"
    
    # Mock WebSocket
    class MockWebSocket:
        def __init__(self):
            self.accepted = False
            self.messages = []
        
        async def accept(self):
            self.accepted = True
        
        async def send_text(self, message):
            self.messages.append(message)
    
    ws = MockWebSocket()
    
    # Connect
    await manager.connect(batch_id, ws)
    assert ws.accepted
    assert batch_id in manager.active_connections
    assert ws in manager.active_connections[batch_id]
    
    # Disconnect
    manager.disconnect(batch_id, ws)
    assert batch_id not in manager.active_connections


@pytest.mark.asyncio
async def test_broadcast_to_batch():
    """Test broadcasting messages to a batch."""
    batch_id = "test-batch-456"
    
    class MockWebSocket:
        def __init__(self):
            self.messages = []
        
        async def accept(self):
            pass
        
        async def send_text(self, message):
            self.messages.append(message)
    
    # Connect multiple clients
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    
    await manager.connect(batch_id, ws1)
    await manager.connect(batch_id, ws2)
    
    # Broadcast message
    test_message = {"type": "test", "data": "hello"}
    await manager.broadcast_to_batch(batch_id, test_message)
    
    # Verify both clients received message
    assert len(ws1.messages) == 1
    assert len(ws2.messages) == 1
    
    received1 = json.loads(ws1.messages[0])
    received2 = json.loads(ws2.messages[0])
    
    assert received1 == test_message
    assert received2 == test_message
    
    # Cleanup
    manager.disconnect(batch_id, ws1)
    manager.disconnect(batch_id, ws2)


@pytest.mark.asyncio
async def test_send_progress_update():
    """Test sending progress updates."""
    batch_id = "test-batch-789"
    
    class MockWebSocket:
        def __init__(self):
            self.messages = []
        
        async def accept(self):
            pass
        
        async def send_text(self, message):
            self.messages.append(message)
    
    ws = MockWebSocket()
    await manager.connect(batch_id, ws)
    
    # Send progress update
    await manager.send_progress_update(
        batch_id=batch_id,
        file_name="test.txt",
        progress=5,
        total_files=10,
        status="processing",
        findings_count=3
    )
    
    # Verify message
    assert len(ws.messages) == 1
    message = json.loads(ws.messages[0])
    
    assert message["type"] == "progress"
    assert message["batch_id"] == batch_id
    assert message["file_name"] == "test.txt"
    assert message["progress"] == 5
    assert message["total_files"] == 10
    assert message["status"] == "processing"
    assert message["findings_count"] == 3
    assert message["percentage"] == 50
    
    # Cleanup
    manager.disconnect(batch_id, ws)


@pytest.mark.asyncio
async def test_send_completion():
    """Test sending completion notification."""
    batch_id = "test-batch-complete"
    
    class MockWebSocket:
        def __init__(self):
            self.messages = []
        
        async def accept(self):
            pass
        
        async def send_text(self, message):
            self.messages.append(message)
    
    ws = MockWebSocket()
    await manager.connect(batch_id, ws)
    
    # Send completion
    results = {"total_findings": 10, "status": "success"}
    await manager.send_completion(batch_id, results)
    
    # Verify message
    assert len(ws.messages) == 1
    message = json.loads(ws.messages[0])
    
    assert message["type"] == "complete"
    assert message["batch_id"] == batch_id
    assert message["results"] == results
    
    # Cleanup
    manager.disconnect(batch_id, ws)


@pytest.mark.asyncio
async def test_send_error():
    """Test sending error notification."""
    batch_id = "test-batch-error"
    
    class MockWebSocket:
        def __init__(self):
            self.messages = []
        
        async def accept(self):
            pass
        
        async def send_text(self, message):
            self.messages.append(message)
    
    ws = MockWebSocket()
    await manager.connect(batch_id, ws)
    
    # Send error
    await manager.send_error(batch_id, "Something went wrong")
    
    # Verify message
    assert len(ws.messages) == 1
    message = json.loads(ws.messages[0])
    
    assert message["type"] == "error"
    assert message["batch_id"] == batch_id
    assert message["error"] == "Something went wrong"
    
    # Cleanup
    manager.disconnect(batch_id, ws)


@pytest.mark.asyncio
async def test_broadcast_to_nonexistent_batch():
    """Test broadcasting to a batch with no connections."""
    batch_id = "nonexistent-batch"
    
    # Should not raise an exception
    await manager.broadcast_to_batch(batch_id, {"type": "test"})


@pytest.mark.asyncio
async def test_dead_connection_cleanup():
    """Test that dead connections are cleaned up."""
    batch_id = "test-batch-cleanup"
    
    class MockWebSocket:
        def __init__(self, should_fail=False):
            self.messages = []
            self.should_fail = should_fail
        
        async def accept(self):
            pass
        
        async def send_text(self, message):
            if self.should_fail:
                raise Exception("Connection dead")
            self.messages.append(message)
    
    # Connect two clients, one will fail
    ws_good = MockWebSocket(should_fail=False)
    ws_bad = MockWebSocket(should_fail=True)
    
    await manager.connect(batch_id, ws_good)
    await manager.connect(batch_id, ws_bad)
    
    # Broadcast - bad connection should be removed
    await manager.broadcast_to_batch(batch_id, {"type": "test"})
    
    # Good connection should have received message
    assert len(ws_good.messages) == 1
    
    # Bad connection should have been cleaned up
    assert ws_bad not in manager.active_connections.get(batch_id, set())
    
    # Cleanup
    manager.disconnect(batch_id, ws_good)


@pytest.mark.asyncio
async def test_multiple_batches():
    """Test managing connections for multiple batches."""
    batch1 = "batch-1"
    batch2 = "batch-2"
    
    class MockWebSocket:
        def __init__(self, name):
            self.name = name
            self.messages = []
        
        async def accept(self):
            pass
        
        async def send_text(self, message):
            self.messages.append(message)
    
    ws1 = MockWebSocket("ws1")
    ws2 = MockWebSocket("ws2")
    
    # Connect to different batches
    await manager.connect(batch1, ws1)
    await manager.connect(batch2, ws2)
    
    # Broadcast to batch1
    await manager.broadcast_to_batch(batch1, {"type": "batch1-message"})
    
    # Only ws1 should receive message
    assert len(ws1.messages) == 1
    assert len(ws2.messages) == 0
    
    # Broadcast to batch2
    await manager.broadcast_to_batch(batch2, {"type": "batch2-message"})
    
    # Only ws2 should receive new message
    assert len(ws1.messages) == 1
    assert len(ws2.messages) == 1
    
    # Cleanup
    manager.disconnect(batch1, ws1)
    manager.disconnect(batch2, ws2)
