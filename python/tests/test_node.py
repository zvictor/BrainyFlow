import pytest
import asyncio
from unittest.mock import AsyncMock
from brainyflow import Memory, Node, DEFAULT_ACTION

# Helper sleep function for async tests
async def async_sleep(seconds: float):
    await asyncio.sleep(seconds)

# --- Test Node Implementations ---
class SimpleNode(Node):
    """Simple test node with mocked lifecycle methods."""
    
    def __init__(self):
        super().__init__()
        self.prep = AsyncMock(return_value="prep_result")
        self.exec = AsyncMock(return_value="exec_result")
        self.post = AsyncMock()
        self.exec_fallback = AsyncMock(return_value="fallback_result")

class TriggeringNode(Node):
    """Node that triggers specific actions with optional forking data."""
    
    def __init__(self):
        super().__init__()
        self.action_to_trigger = DEFAULT_ACTION
        self.forking_data = None
    
    async def post(self, memory, prep_res, exec_res):
        if self.action_to_trigger:
            if self.forking_data:
                self.trigger(self.action_to_trigger, self.forking_data)
            else:
                self.trigger(self.action_to_trigger)

class ErrorNode(Node):
    """Node that fails a configurable number of times for testing retry logic."""
    
    def __init__(self, max_retries=1, wait=0, succeed_after=1):
        super().__init__(max_retries=max_retries, wait=wait)
        self.succeed_after = succeed_after
        self.fail_count = 0
        self.exec_fallback = AsyncMock(
            return_value=lambda prep_res, error: f"fallback_result_after_{error.retry_count}_retries"
        )
    
    async def exec(self, prep_res):
        """Fail until succeed_after threshold is reached."""
        if self.fail_count < self.succeed_after:
            self.fail_count += 1
            raise Exception(f"Planned failure {self.fail_count}")
        return "success_after_retry"

class TestBaseNodeAndNode:
    """Tests for BaseNode and Node classes."""
    
    @pytest.fixture
    def memory(self):
        """Create a test memory instance."""
        global_store = {"initial": "global"}
        return Memory(global_store)

    class TestLifecycleMethods:
        """Tests for node lifecycle methods (prep, exec, post)."""
        
        async def test_call_prep_exec_post_in_order_with_correct_arguments(self, memory):
            """Should call prep, exec, post in order with correct arguments."""
            node = SimpleNode()
            
            # Mock post to properly handle exec_res assertion
            node.post = AsyncMock()
            
            exec_result = await node.run(memory)
            
            # Check results
            assert exec_result == "exec_result"
            
            # Check method calls
            node.prep.assert_called_once()
            node.exec.assert_called_once()
            node.post.assert_called_once()
            
            # Check arguments passed
            node.prep.assert_called_with(memory)
            node.exec.assert_called_with("prep_result")
            node.post.assert_called_with(memory, "prep_result", "exec_result")
        
        async def test_handle_nodes_with_partial_lifecycle_methods(self, memory):
            """Should handle nodes with only some lifecycle methods implemented."""
            
            class PartialNode(Node):
                async def prep(self, memory):
                    memory.prep_done = True
                    return "partial_prep"
                
                # No exec method
                
                async def post(self, memory, prep_res, exec_res):
                    memory.post_done = True
                    assert prep_res == "partial_prep"
                    assert exec_res is None  # None in Python, not undefined as in TS
            
            node = PartialNode()
            result = await node.run(memory)
            
            assert result is None
            assert memory.prep_done is True
            assert memory.post_done is True

    class TestSyntaxSugar:
        """Tests for Python-specific syntax sugar."""
        
        async def test_default_transition_operator(self):
            """Should support node_a >> node_b syntax."""
            node_a = SimpleNode()
            node_b = SimpleNode()
            
            node_a >> node_b
            
            assert node_a.get_next_nodes() == [node_b]
            assert node_a.get_next_nodes("other") == []

        async def test_named_action_transition_operator(self):
            """Should support node_a - "action" >> node_b syntax."""
            node_a = SimpleNode()
            node_b = SimpleNode()
            node_c = SimpleNode()
            
            node_a - "success" >> node_b
            node_a - "error" >> node_c
            
            assert node_a.get_next_nodes("success") == [node_b]
            assert node_a.get_next_nodes("error") == [node_c]
            assert node_a.get_next_nodes() == []

        async def test_combined_operators(self):
            """Should support combining default and named transitions."""
            node_a = SimpleNode()
            node_b = SimpleNode()
            node_c = SimpleNode()
            node_d = SimpleNode()
            
            # Mix operators
            node_a >> node_b
            node_a - "alt" >> node_c
            node_b >> node_d
            
            assert node_a.get_next_nodes() == [node_b]
            assert node_a.get_next_nodes("alt") == [node_c]
            assert node_b.get_next_nodes() == [node_d]
            assert node_c.get_next_nodes() == []
            assert node_d.get_next_nodes() == []

    class TestGraphConnections:
        """Tests for node connection methods (on, next, get_next_nodes)."""
        
        @pytest.fixture
        def nodes(self):
            """Create test nodes."""
            return {
                "A": SimpleNode(),
                "B": SimpleNode(),
                "C": SimpleNode()
            }
        
        def test_on_adds_successor_correctly(self, nodes):
            """on(action, node) should add the node to the correct action's successors list."""
            node_a, node_b = nodes["A"], nodes["B"]
            
            returned_node = node_a.on("success", node_b)
            
            assert returned_node is node_b
            successors = node_a.get_next_nodes("success")
            assert successors == [node_b]
            assert node_a.get_next_nodes(DEFAULT_ACTION) == []
        
        def test_next_adds_successor_correctly(self, nodes):
            """next(node, action?) should add the node correctly."""
            node_a, node_b, node_c = nodes["A"], nodes["B"], nodes["C"]
            
            # Default action
            returned_node_default = node_a.next(node_b)
            # Named action
            returned_node_named = node_a.next(node_c, "custom")
            
            assert returned_node_default is node_b
            assert returned_node_named is node_c
            assert node_a.get_next_nodes(DEFAULT_ACTION) == [node_b]
            assert node_a.get_next_nodes("custom") == [node_c]
            assert node_a.get_next_nodes("other") == []
        
        def test_get_next_nodes_returns_correct_successors(self, nodes):
            """get_next_nodes(action) should return the correct list of successor nodes."""
            node_a, node_b, node_c = nodes["A"], nodes["B"], nodes["C"]
            
            node_a.on("a", node_b)
            node_a.on("a", node_c)
            node_a.on("b", node_b)
            
            assert node_a.get_next_nodes("a") == [node_b, node_c]
            assert node_a.get_next_nodes("b") == [node_b]
            assert node_a.get_next_nodes("c") == []
            assert node_a.get_next_nodes() == []  # Default action
        
        def test_get_next_nodes_returns_empty_list_if_no_successors(self, nodes):
            """get_next_nodes(action) should return an empty list if no successors exist."""
            assert nodes["A"].get_next_nodes("any") == []
        
        def test_get_next_nodes_warns_if_nondefault_action_but_only_others_exist(self, nodes):
            """Should warn if non-default action requested but only other actions exist."""
            node_a, node_b = nodes["A"], nodes["B"]

            node_a.on("action1", node_b)
            with pytest.warns(UserWarning, match="not found in"):
                node_a.get_next_nodes("non_existent_action")


    class TestTriggering:
        """Tests for node triggering (trigger, list_triggers)."""
        
        async def test_store_triggers_internally_via_trigger(self, memory):
            """trigger(action, forking_data) should store triggers internally."""
            node = TriggeringNode()
            node.action_to_trigger = "my_action"
            node.forking_data = {"key": "value"}
            
            # Run with propagate=True to get triggers
            triggers = await node.run(memory, propagate=True)
            
            assert len(triggers) == 1
            action, triggered_memory = triggers[0]
            
            assert action == "my_action"
            assert isinstance(triggered_memory, Memory)
            assert triggered_memory.key == "value"  # Check forking_data applied locally
            assert triggered_memory.local["key"] == "value"
            # Original memory should not have 'key'
            with pytest.raises(AttributeError, match="Key 'key' not found in stores"):
                _ = memory.key
        
        async def test_trigger_throws_error_if_called_outside_post(self, memory):
            """trigger() should throw an error if called outside post()."""
            node = TriggeringNode()
            
            with pytest.raises(Exception, match="An action can only be triggered inside post"):
                node.trigger("test")
        
        async def test_list_triggers_returns_default_action_if_no_trigger_called(self, memory):
            """list_triggers() should return DEFAULT_ACTION if no trigger was called."""
            node = TriggeringNode()
            node.action_to_trigger = None  # Ensure trigger is not called in post
            
            triggers = await node.run(memory, propagate=True)
            
            assert len(triggers) == 1
            action, triggered_memory = triggers[0]
            
            assert action == DEFAULT_ACTION
            assert isinstance(triggered_memory, Memory)
            assert triggered_memory is not memory  # Should be a clone
            assert triggered_memory.local == {}  # No forking data
        
        async def test_list_triggers_handles_multiple_triggers(self, memory):
            """list_triggers() should handle multiple triggers."""
            
            class MultiTriggerNode(Node):
                async def post(self, memory, prep_res, exec_res):
                    self.trigger("action1", {"data1": 1})
                    self.trigger("action2", {"data2": 2})
            
            node = MultiTriggerNode()
            triggers = await node.run(memory, propagate=True)
            
            assert len(triggers) == 2
            
            # Find triggers by action
            trigger1 = next((t for t in triggers if t[0] == "action1"), None)
            trigger2 = next((t for t in triggers if t[0] == "action2"), None)
            
            assert trigger1 is not None
            assert trigger1[1].data1 == 1
            assert trigger1[1].local == {"data1": 1}
            
            assert trigger2 is not None
            assert trigger2[1].data2 == 2
            assert trigger2[1].local == {"data2": 2}

    class TestExecution:
        """Tests for node execution (run method)."""
        
        async def test_run_with_propagate_false_returns_exec_result(self, memory):
            """run(memory, propagate=False) should return execRunner result."""
            node = SimpleNode()
            
            # Override mocks with real methods to ensure correct behavior
            async def mock_prep(mem):
                return "prep_result"
            
            async def mock_exec(prep_res):
                assert prep_res == "prep_result"
                return "exec_result"
            
            node.prep = mock_prep
            node.exec = mock_exec
            
            result = await node.run(memory, propagate=False)
            
            assert result == "exec_result"
        
        async def test_run_defaults_to_returning_exec_result(self, memory):
            """run(memory) should default to returning execRunner result."""
            node = SimpleNode()
            
            # Override mocks with real methods
            async def mock_prep(mem):
                return "prep_result"
            
            async def mock_exec(prep_res):
                assert prep_res == "prep_result"
                return "exec_result"
            
            node.prep = mock_prep
            node.exec = mock_exec
            
            result = await node.run(memory)  # Omitted propagate
            
            assert result == "exec_result"
        
        async def test_run_with_propagate_true_returns_list_triggers_result(self, memory):
            """run(memory, propagate=True) should return list_triggers result."""
            node = TriggeringNode()
            node.action_to_trigger = "test_action"
            
            triggers = await node.run(memory, propagate=True)
            
            assert len(triggers) == 1
            assert triggers[0][0] == "test_action"
            assert isinstance(triggers[0][1], Memory)
        
        async def test_run_accepts_global_store_directly(self):
            """run() should accept global store directly."""
            node = SimpleNode()
            
            # Create an async mock for prep that captures the memory argument
            captured_memory = None
            async def mock_prep(mem):
                nonlocal captured_memory
                captured_memory = mem
                return "prep_result"
            
            node.prep = mock_prep
            
            # Global store
            global_store = {"count": 5, "initial": "global_val"}
            
            await node.run(global_store)  # Pass global store object directly
            
            assert isinstance(captured_memory, Memory)
            assert captured_memory.initial == "global_val"
            assert captured_memory.count == 5
            assert captured_memory.local == {}

    class TestCloning:
        """Tests for node cloning (clone method)."""
        
        def test_create_deep_copy_of_node_instance(self):
            """clone() should create a deep copy of the node instance."""
            node_a = SimpleNode()
            node_a.custom_prop = "original_value"
            
            clone_a = node_a.clone()
            
            assert clone_a is not node_a
            assert isinstance(clone_a, SimpleNode)
            assert clone_a.custom_prop == "original_value"
            
            # Modify original, clone should be unaffected
            node_a.custom_prop = "modified_value"
            assert clone_a.custom_prop == "original_value"
        
        def test_recursively_clone_successors(self):
            """clone() should recursively clone successors."""
            node_a = SimpleNode()
            node_b = SimpleNode()
            node_c = SimpleNode()
            
            node_a.next(node_b)
            node_b.on("action", node_c)
            
            clone_a = node_a.clone()
            clone_b = clone_a.get_next_nodes(DEFAULT_ACTION)[0]
            clone_c = clone_b.get_next_nodes("action")[0]
            
            assert clone_b is not None
            assert clone_c is not None
            assert clone_b is not node_b
            assert clone_c is not node_c
            assert isinstance(clone_b, SimpleNode)
            assert isinstance(clone_c, SimpleNode)
        
        def test_handle_cyclic_graph_structures(self):
            """clone() should handle cyclic graph structures using the seen dictionary."""
            node_a = SimpleNode()
            node_b = SimpleNode()
            
            node_a.next(node_b)
            node_b.next(node_a)  # Create cycle
            
            # Should not raise RecursionError
            clone_a = node_a.clone()
            
            assert clone_a is not None
            clone_b = clone_a.get_next_nodes(DEFAULT_ACTION)[0]
            assert clone_b is not None
            
            clone_a_from_b = clone_b.get_next_nodes(DEFAULT_ACTION)[0]
            assert clone_a_from_b is not None
            
            # Check that the cycle points back to the *cloned* instance of A
            assert clone_a_from_b is clone_a
    
    class TestNodeRetry:
        """Tests for Node retry logic."""
        
        async def test_retry_exec_on_failure(self):
            """exec should be retried max_retries-1 times upon failure."""
            node = ErrorNode(max_retries=3, succeed_after=2)  # Succeed on 3rd attempt (after 2 failures)
            
            result = await node.run(Memory({}))
            
            assert result == "success_after_retry"
            assert node.fail_count == 2  # Should have failed twice
        
        async def test_call_exec_fallback_when_all_retries_fail(self):
            """exec_fallback should be called when all retries fail."""
            node = ErrorNode(max_retries=2, succeed_after=10)  # Will never succeed naturally
            
            # Mock fallback to return a specific value
            async def mock_fallback(prep_res, error):
                assert hasattr(error, "retry_count")
                assert error.retry_count == node.max_retries  # noqa: F821
                return "fallback_called"

            node.exec_fallback = mock_fallback
            
            result = await node.run(Memory({}))
            
            assert result == "fallback_called"
            assert node.fail_count == 2  # Should have failed max_retries times
        
        async def test_wait_between_retries(self):
            """Should wait between retries if wait option is provided."""
            node = ErrorNode(max_retries=2, wait=0.05, succeed_after=10)  # Will use fallback
            
            start_time = asyncio.get_event_loop().time()
            
            # Mock fallback to avoid external dependencies
            async def mock_fallback(prep_res, error):
                return "fallback_after_wait"
            
            node.exec_fallback = mock_fallback
            
            result = await node.run(Memory({}))
            
            end_time = asyncio.get_event_loop().time()
            elapsed = end_time - start_time
            
            assert result == "fallback_after_wait"
            assert elapsed >= 0.05  # Should have waited at least 0.05s between retries
            assert node.fail_count == 2
        
        async def test_propagate_exec_fallback_error(self):
            """If exec_fallback raises an exception, it should propagate."""
            node = ErrorNode(max_retries=2, succeed_after=10)  # Will never succeed naturally
            
            # Mock fallback to throw an error
            async def mock_fallback(prep_res, error):
                raise ValueError("Fallback error")
            
            node.exec_fallback = mock_fallback
            
            with pytest.raises(ValueError, match="Fallback error"):
                await node.run(Memory({}))
