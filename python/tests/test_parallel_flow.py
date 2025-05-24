import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock
from brainyflow import Memory, Node, Flow, ParallelFlow, DEFAULT_ACTION, BaseNode, ExecutionTree

# Helper sleep function for async tests
async def async_sleep(seconds: float):
    await asyncio.sleep(seconds)

# --- Helper Node Implementations ---
class DelayedNode(Node):
    """Node with configurable execution delays for testing parallel execution."""
    
    def __init__(self, id_str):
        super().__init__()
        self.id = id_str
        self.prep_mock = AsyncMock()
        self.exec_mock = AsyncMock()
        self.next_node_delay = None
    
    async def prep(self, memory):
        delay = getattr(memory, 'delay', 0)
        memory[f"prep_start_{self.id}_{getattr(memory, 'id', 'main')}"] = time.time()
        await self.prep_mock(memory)
        return {"delay": delay}
    
    async def exec(self, prep_res):
        delay = prep_res["delay"]
        await async_sleep(delay)
        await self.exec_mock(prep_res)
        return f"exec_{self.id}_slept_{delay}"
    
    async def post(self, memory, prep_res, exec_res):
        memory[f"post_{self.id}_{getattr(memory, 'id', 'main')}"] = exec_res
        memory[f"prep_end_{self.id}_{getattr(memory, 'id', 'main')}"] = time.time()
        
        if self.next_node_delay is not None:
            self.trigger(DEFAULT_ACTION, {"delay": self.next_node_delay, "id": getattr(memory, 'id', None)})
        else:
            # Even if no specific forking_data for next node, pass the current branch ID
            self.trigger(DEFAULT_ACTION, {"id": getattr(memory, 'id', None)})

class MultiTriggerNode(Node):
    """Node that triggers multiple branches with configurable actions and fork data."""
    
    def __init__(self):
        super().__init__()
        self.triggers_to_fire = []
    
    def add_trigger(self, action, fork_data):
        self.triggers_to_fire.append({"action": action, "fork_data": fork_data})
    
    async def post(self, memory, prep_res, exec_res):
        memory.trigger_node_post_time = time.time()
        for t in self.triggers_to_fire:
            self.trigger(t["action"], t["fork_data"])

class TestParallelFlow:
    """Tests for the ParallelFlow class."""
    
    @pytest.fixture
    def setup(self):
        """Create test nodes and memory."""
        BaseNode._next_id = 0 # Reset for predictable IDs
        global_store = {"initial": "global"}
        memory_instance = Memory(global_store)
        trigger_node_instance = MultiTriggerNode() # id 0
        node_b_instance = DelayedNode("B")         # id 1
        node_c_instance = DelayedNode("C")         # id 2
        node_d_instance = DelayedNode("D")         # id 3
        
        return {
            "memory": memory_instance, 
            "global_store": global_store,
            "trigger_node": trigger_node_instance,
            "node_b": node_b_instance,
            "node_c": node_c_instance,
            "node_d": node_d_instance
        }
    
    @pytest.mark.asyncio
    async def test_execute_triggered_branches_concurrently(self, setup):
        """Should execute triggered branches concurrently using run_tasks override."""
        delay_b = 0.05
        delay_c = 0.06
        
        trigger_node = setup["trigger_node"]
        node_b = setup["node_b"]
        node_c = setup["node_c"]

        trigger_node.add_trigger("process_b", {"id": "B", "delay": delay_b})
        trigger_node.add_trigger("process_c", {"id": "C", "delay": delay_c})
        trigger_node.on("process_b", node_b)
        trigger_node.on("process_c", node_c)
        
        parallel_flow = ParallelFlow(trigger_node)
        
        start_time = time.time()
        result = await parallel_flow.run(setup["memory"])
        end_time = time.time()
        duration = end_time - start_time
        
        max_delay = max(delay_b, delay_c)
        sum_delay = delay_b + delay_c
        
        print(f"Execution Time: {duration}s (Max Delay: {max_delay}s, Sum Delay: {sum_delay}s)")
        
        assert duration < sum_delay + 0.1
        assert duration == pytest.approx(max_delay, abs=0.1)
        
        assert setup["memory"][f"post_B_B"] == f"exec_B_slept_{delay_b}"
        assert setup["memory"][f"post_C_C"] == f"exec_C_slept_{delay_c}"
        
        assert result and isinstance(result, dict), "Result should be a dictionary (ExecutionTree)"
        assert result['order'] == str(trigger_node._node_order)
        assert result['type'] == trigger_node.__class__.__name__
        
        triggered = result['triggered']
        assert triggered is not None
        assert "process_b" in triggered, "Result should contain 'process_b' key in triggered"
        assert "process_c" in triggered, "Result should contain 'process_c' key in triggered"
        
        process_b_results_list = triggered["process_b"]
        process_c_results_list = triggered["process_c"]
        
        assert isinstance(process_b_results_list, list) and len(process_b_results_list) == 1
        assert isinstance(process_c_results_list, list) and len(process_c_results_list) == 1
        
        # Check structure of individual node logs
        expected_log_b: ExecutionTree = {
            'order': str(node_b._node_order),
            'type': node_b.__class__.__name__,
            'triggered': {DEFAULT_ACTION: []} # DelayedNode is terminal for this action
        }
        expected_log_c: ExecutionTree = {
            'order': str(node_c._node_order),
            'type': node_c.__class__.__name__,
            'triggered': {DEFAULT_ACTION: []} # DelayedNode is terminal for this action
        }
        
        assert process_b_results_list[0] == expected_log_b
        assert process_c_results_list[0] == expected_log_c
        
        assert node_b.exec_mock.call_count + node_c.exec_mock.call_count == 2
    
    @pytest.mark.asyncio
    async def test_handle_mix_of_parallel_and_sequential_execution(self, setup):
        """Should handle mix of parallel and sequential execution."""
        delay_b = 0.05
        delay_c = 0.06
        delay_d = 0.03
        
        trigger_node = setup["trigger_node"]
        node_b = setup["node_b"]
        node_c = setup["node_c"]
        node_d = setup["node_d"]

        trigger_node.add_trigger("parallel_b", {"id": "B", "delay": delay_b})
        trigger_node.add_trigger("parallel_c", {"id": "C", "delay": delay_c})
        
        trigger_node.on("parallel_b", node_b)
        trigger_node.on("parallel_c", node_c)
        
        node_b.next(node_d)
        node_c.next(node_d)
        
        node_b.next_node_delay = delay_d
        node_c.next_node_delay = delay_d
        
        parallel_flow = ParallelFlow(trigger_node)
        
        start_time = time.time()
        result_mix = await parallel_flow.run(setup["memory"]) # Renamed result to result_mix
        end_time = time.time()
        duration = end_time - start_time
        
        expected_min_duration = max(delay_b, delay_c) + delay_d
        
        print(f"Mixed Execution Time: {duration}s (Expected Min: ~{expected_min_duration}s)")
        
        assert setup["memory"][f"post_B_B"] == f"exec_B_slept_{delay_b}"
        assert setup["memory"][f"post_C_C"] == f"exec_C_slept_{delay_c}"
        assert setup["memory"][f"post_D_B"] == f"exec_D_slept_{delay_d}"
        assert setup["memory"][f"post_D_C"] == f"exec_D_slept_{delay_d}"
        
        assert duration >= expected_min_duration - 0.02 # Allow small timing variance
        assert duration < expected_min_duration + 0.1
        
        assert node_d.exec_mock.call_count == 2

        # Optionally, assert the structure of result_mix if needed
        assert result_mix['order'] == str(trigger_node._node_order)
        triggered_mix = result_mix['triggered']
        assert triggered_mix is not None
        
        path_b_log = triggered_mix['parallel_b'][0]
        path_c_log = triggered_mix['parallel_c'][0]

        assert path_b_log['order'] == str(node_b._node_order)
        assert path_b_log['triggered'][DEFAULT_ACTION][0]['order'] == str(node_d._node_order)
        assert path_b_log['triggered'][DEFAULT_ACTION][0]['triggered'] == {DEFAULT_ACTION: []}

        assert path_c_log['order'] == str(node_c._node_order)
        assert path_c_log['triggered'][DEFAULT_ACTION][0]['order'] == str(node_d._node_order)
        assert path_c_log['triggered'][DEFAULT_ACTION][0]['triggered'] == {DEFAULT_ACTION: []}

