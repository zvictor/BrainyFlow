import pytest
import warnings
import logging
import asyncio
from unittest.mock import AsyncMock
from brainyflow import Memory, Node, Flow, DEFAULT_ACTION

@pytest.fixture(autouse=True)
def capture_warnings(caplog):
    """Ensure warnings are captured in logs."""
    caplog.set_level(logging.WARNING)
    warnings.filterwarnings("always")
    return caplog

def pytest_addoption(parser):
    parser.addini("asyncio_mode", default="auto", help="default asyncio mode")

# Helper sleep function for async tests
async def async_sleep(seconds: float):
    """Utility function to simulate delays in async functions."""
    await asyncio.sleep(seconds)

# --- Common Test Node Implementations ---
class BaseTestNode(Node):
    """Basic node implementation for testing node lifecycle."""
    
    def __init__(self, id_str="test"):
        super().__init__()
        self.id = id_str
        self.prep_mock = AsyncMock(return_value=f"prep_{self.id}")
        self.exec_mock = AsyncMock(return_value=f"exec_{self.id}")
        self.post_mock = AsyncMock()
    
    async def prep(self, memory):
        """Setup phase that marks memory and returns ID-based result."""
        memory[f"prep_{self.id}"] = True
        await self.prep_mock(memory)
        return f"prep_{self.id}"
    
    async def exec(self, prep_res):
        """Execute phase that returns ID-based result."""
        assert prep_res == f"prep_{self.id}"
        return await self.exec_mock(prep_res)
    
    async def post(self, memory, prep_res, exec_res):
        """Post-processing phase that marks memory."""
        assert prep_res == f"prep_{self.id}"
        assert exec_res == f"exec_{self.id}"
        memory[f"post_{self.id}"] = True
        await self.post_mock(memory, prep_res, exec_res)
        # Default trigger is implicit

class BranchingNode(BaseTestNode):
    """Node that triggers a specific action with optional forking data."""
    
    def __init__(self, id_str="branch"):
        super().__init__(id_str)
        self.action = DEFAULT_ACTION
        self.fork_data = None
    
    def set_trigger(self, action, fork_data=None):
        """Configure which action this node will trigger."""
        self.action = action
        self.fork_data = fork_data
    
    async def post(self, memory, prep_res, exec_res):
        await super().post(memory, prep_res, exec_res)  # Call base post
        if self.fork_data is not None:
            self.trigger(self.action, self.fork_data)
        else:
            self.trigger(self.action)

class DelayedNode(Node):
    """Node with configurable execution delays for testing parallel execution."""
    
    def __init__(self, id_str):
        super().__init__()
        self.id = id_str
        self.prep_mock = AsyncMock()
        self.exec_mock = AsyncMock()
        self.next_node_delay = None
    
    async def prep(self, memory):
        # Read delay from local memory (passed via forkingData)
        delay = getattr(memory, 'delay', 0)
        memory[f"prep_start_{self.id}_{getattr(memory, 'id', 'main')}"] = True
        await self.prep_mock(memory)
        return {"delay": delay}
    
    async def exec(self, prep_res):
        delay = prep_res["delay"]
        await async_sleep(delay)
        await self.exec_mock(prep_res)
        return f"exec_{self.id}_slept_{delay}"
    
    async def post(self, memory, prep_res, exec_res):
        memory[f"post_{self.id}_{getattr(memory, 'id', 'main')}"] = exec_res
        memory[f"prep_end_{self.id}_{getattr(memory, 'id', 'main')}"] = True
        
        # Trigger default successor, passing the intended delay for the *next* node if set
        if self.next_node_delay is not None:
            self.trigger(DEFAULT_ACTION, {"delay": self.next_node_delay, "id": getattr(memory, 'id', None)})
        else:
            self.trigger(DEFAULT_ACTION, {"id": getattr(memory, 'id', None)})

class MultiTriggerNode(Node):
    """Node that triggers multiple branches with configurable actions and fork data."""
    
    def __init__(self):
        super().__init__()
        self.triggers_to_fire = []
    
    def add_trigger(self, action, fork_data):
        self.triggers_to_fire.append({"action": action, "fork_data": fork_data})
    
    async def prep(self, memory):
        return None
    
    async def exec(self, prep_res):
        return None
    
    async def post(self, memory, prep_res, exec_res):
        memory.trigger_node_post_time = True
        for t in self.triggers_to_fire:
            self.trigger(t["action"], t["fork_data"])

class ErrorNode(Node):
    """Node that fails a configurable number of times for testing retry logic."""
    
    def __init__(self, max_retries=1, wait=0, succeed_after=1):
        super().__init__(max_retries=max_retries, wait=wait)
        self.succeed_after = succeed_after
        self.fail_count = 0
        self.exec_fallback = AsyncMock(return_value="fallback_result")
    
    async def exec(self, prep_res):
        """Fail until succeed_after threshold is reached."""
        if self.fail_count < self.succeed_after:
            self.fail_count += 1
            raise Exception(f"Planned failure {self.fail_count}")
        return "success_after_retry"

# --- Common test fixtures ---
@pytest.fixture
def memory():
    """Create a test memory instance."""
    global_store = {"initial": "global"}
    return Memory(global_store)

@pytest.fixture
def test_nodes():
    """Create a set of test nodes."""
    return {
        "A": TestNode("A"),
        "B": TestNode("B"),
        "C": TestNode("C"),
        "D": TestNode("D")
    }

@pytest.fixture
def branching_node():
    """Create a branching node."""
    return BranchingNode("Branch")
