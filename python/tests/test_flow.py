import pytest
from unittest.mock import AsyncMock
from brainyflow import Memory, Node, Flow, DEFAULT_ACTION, BaseNode

# --- Helper Node Implementations ---
class BaseTestNode(Node):
    """Basic test node with mocked lifecycle methods."""
    
    def __init__(self, id_str):
        super().__init__()
        self.id = id_str
        self.prep_mock = AsyncMock(return_value=f"prep_{self.id}")
        self.exec_mock = AsyncMock(return_value=f"exec_{self.id}")
        self.post_mock = AsyncMock()
    
    async def prep(self, memory):
        memory[f"prep_{self.id}"] = True
        await self.prep_mock(memory)
        return f"prep_{self.id}"
    
    async def exec(self, prep_res):
        assert prep_res == f"prep_{self.id}"
        return await self.exec_mock(prep_res)
    
    async def post(self, memory, prep_res, exec_res):
        assert prep_res == f"prep_{self.id}"
        assert exec_res == f"exec_{self.id}"
        memory[f"post_{self.id}"] = True
        await self.post_mock(memory, prep_res, exec_res)
        # Default trigger is implicit


class BranchingNode(BaseTestNode):
    """Node that triggers a specific action with optional forking data."""
    
    def __init__(self, id_str):
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


class TestFlow:
    """Tests for the Flow class."""
    
    @pytest.fixture
    def memory(self):
        """Create a test memory instance."""
        global_store = {"initial": "global"}
        return Memory(global_store)
    
    @pytest.fixture
    def nodes(self):
        """Create test nodes.
        IMPORTANT: Reset BaseNode._next_id to ensure predictable orders for tests.
        This should ideally be handled by a session-scoped or test-scoped fixture
        if node creation order varies significantly across test files or setup.
        For now, we assume it's reset or nodes are created fresh with predictable IDs.
        """
        # Resetting for test predictability. If BaseNode is imported by multiple test files,
        # this might need a more robust solution (e.g. pytest_runtest_setup fixture).
        BaseNode._next_id = 0 
        return {
            "A": BaseTestNode("A"),
            "B": BaseTestNode("B"),
            "C": BaseTestNode("C"),
            "D": BaseTestNode("D")
        }
    
    @pytest.fixture
    def branching_node_fixture(self):
        # Separate fixture for branching node to control its _node_order independently if needed
        BaseNode._next_id = 0 # Example of resetting if it's the first node in a test
        return BranchingNode("Branch")


    class TestInitialization:
        """Tests for Flow initialization."""
        
        def test_store_start_node_and_default_options(self, nodes):
            """Should store the start node and default options."""
            flow = Flow(nodes["A"])
            assert flow.start == nodes["A"]
            assert getattr(flow, "options", {}).get("max_visits") == 15
        
        def test_accept_custom_options(self, nodes):
            """Should accept custom options."""
            flow = Flow(nodes["A"], {"max_visits": 10})
            assert flow.start == nodes["A"]
            assert getattr(flow, "options", {}).get("max_visits") == 10
    
    class TestSequentialExecution:
        """Tests for sequential execution of nodes."""
        
        async def test_execute_nodes_sequentially_following_default_actions(self, nodes, memory):
            """Should execute nodes sequentially following default actions."""
            nodes["A"].next(nodes["B"])
            nodes["B"].next(nodes["C"])  # A -> B -> C
            
            flow = Flow(nodes["A"])
            await flow.run(memory)
            
            # Verify execution order via mocks
            assert nodes["A"].prep_mock.call_count == 1
            assert nodes["A"].exec_mock.call_count == 1
            assert nodes["A"].post_mock.call_count == 1
            assert nodes["B"].prep_mock.call_count == 1
            assert nodes["B"].exec_mock.call_count == 1
            assert nodes["B"].post_mock.call_count == 1
            assert nodes["C"].prep_mock.call_count == 1
            assert nodes["C"].exec_mock.call_count == 1
            assert nodes["C"].post_mock.call_count == 1
            
            # Verify memory changes
            assert memory.prep_A is True
            assert memory.post_A is True
            assert memory.prep_B is True
            assert memory.post_B is True
            assert memory.prep_C is True
            assert memory.post_C is True
        
        async def test_stop_execution_if_node_has_no_successor(self, nodes, memory):
            """Should stop execution if a node has no successor for the triggered action."""
            nodes["A"].next(nodes["B"])  # A -> B (B has no successor)
            
            flow = Flow(nodes["A"])
            await flow.run(memory)
            
            assert nodes["A"].post_mock.call_count == 1
            assert nodes["B"].post_mock.call_count == 1
            assert nodes["C"].prep_mock.call_count == 0  # C should not run
    
    class TestConditionalBranching:
        """Tests for conditional branching."""
        
        async def test_follow_correct_path_based_on_triggered_action(self, nodes, memory):
            """Should follow the correct path based on triggered action."""
            # Reset BaseNode ID for predictable IDs in this test
            BaseNode._next_id = 0
            branching_node = BranchingNode("Branch") # id_Branch = 0
            # nodes A, B, C, D are created by fixture, their IDs will be 0,1,2,3 if nodes fixture is used first
            # If branching_node is created first, its ID will be 0.
            # Let's use fresh nodes for clarity here if IDs matter deeply for the test logic.
            # For this test, memory state check is primary.
            
            node_b_local = BaseTestNode("B_local") # id_B_local = 1
            node_c_local = BaseTestNode("C_local") # id_C_local = 2

            branching_node.on("path_B", node_b_local)
            branching_node.on("path_C", node_c_local)
            
            # Test path B
            branching_node.set_trigger("path_B")
            flow_b = Flow(branching_node)
            memory_b = Memory({})
            await flow_b.run(memory_b)
            
            assert memory_b.post_Branch is True
            assert memory_b.post_B_local is True
            assert getattr(memory_b, "post_C_local", None) is None
            
            # Test path C
            # Re-create branching_node or use a new Flow instance to reset visit counts
            # and ensure post_mock counts are fresh for this path.
            BaseNode._next_id = 0 # Reset again if we want same ID for branching_node
            branching_node_for_c = BranchingNode("Branch") # id = 0
            node_b_for_c = BaseTestNode("B_for_C") # id = 1
            node_c_for_c = BaseTestNode("C_for_C") # id = 2
            branching_node_for_c.on("path_B", node_b_for_c)
            branching_node_for_c.on("path_C", node_c_for_c)

            branching_node_for_c.set_trigger("path_C")
            flow_c = Flow(branching_node_for_c) 
            memory_c = Memory({})
            await flow_c.run(memory_c)
            
            assert memory_c.post_Branch is True
            assert getattr(memory_c, "post_B_for_C", None) is None
            assert memory_c.post_C_for_C is True
    
    class TestMemoryHandling:
        """Tests for memory handling."""
        
        async def test_propagate_global_memory_changes(self, nodes, memory):
            """Should propagate global memory changes."""
            async def modify_memory(mem, prep_res, exec_res):  
                mem.global_A = "set_by_A"
            
            nodes["A"].post_mock.side_effect = modify_memory
            
            async def verify_memory(mem):
                assert mem.global_A == "set_by_A"
            
            nodes["B"].prep_mock.side_effect = verify_memory
            
            nodes["A"].next(nodes["B"])
            flow = Flow(nodes["A"])
            await flow.run(memory)
            
            assert memory.global_A == "set_by_A"
            assert nodes["B"].prep_mock.call_count == 1
        
        async def test_isolate_local_memory_using_forking_data(self, nodes, memory):
            """Should isolate local memory using forkingData."""
            BaseNode._next_id = 0
            branching_node = BranchingNode("Branch") # id 0
            node_b_local = BaseTestNode("B_local")   # id 1
            node_c_local = BaseTestNode("C_local")   # id 2

            branching_node.on("path_B", node_b_local)
            branching_node.on("path_C", node_c_local)
            
            async def check_b_memory(mem):
                assert mem.local_data == "for_B"
                assert mem.common_local == "common"
                assert mem.local["local_data"] == "for_B"
            
            async def check_c_memory(mem):
                assert mem.local_data == "for_C"
                assert mem.common_local == "common"
                assert mem.local["local_data"] == "for_C"
            
            node_b_local.prep_mock.side_effect = check_b_memory
            node_c_local.prep_mock.side_effect = check_c_memory
            
            branching_node.set_trigger("path_B", {"local_data": "for_B", "common_local": "common"})
            flow_b = Flow(branching_node)
            memory_b = Memory({"global_val": 1})
            await flow_b.run(memory_b)
            
            assert node_b_local.prep_mock.call_count == 1
            assert node_c_local.prep_mock.call_count == 0
            assert getattr(memory_b, "local_data", None) is None
            assert getattr(memory_b, "common_local", None) is None
            
            # For path C, use a new branching_node instance or reset mocks for clarity
            BaseNode._next_id = 0
            branching_node_for_c = BranchingNode("BranchC") # id 0
            # node_b_local and node_c_local are not reused here to avoid mock call count confusion
            node_b_for_c_path = BaseTestNode("B_for_C_Path") # id 1
            node_c_for_c_path = BaseTestNode("C_for_C_Path") # id 2
            node_c_for_c_path.prep_mock.side_effect = check_c_memory


            branching_node_for_c.on("path_B", node_b_for_c_path)
            branching_node_for_c.on("path_C", node_c_for_c_path)
            branching_node_for_c.set_trigger("path_C", {"local_data": "for_C", "common_local": "common"})
            
            flow_c = Flow(branching_node_for_c)
            memory_c = Memory({"global_val": 1})
            await flow_c.run(memory_c)
            
            assert node_c_for_c_path.prep_mock.call_count == 1
            assert getattr(memory_c, "local_data", None) is None
            assert getattr(memory_c, "common_local", None) is None
    
    class TestCycleDetection:
        """Tests for cycle detection."""
        
        async def test_execute_loop_maxvisits_times_before_error(self, nodes):
            """Should execute a loop exactly maxVisits times before error."""
            loop_count = [0] 
            
            async def increment_count(mem):
                loop_count[0] += 1
                mem.count = loop_count[0]
            
            nodes["A"].prep_mock.side_effect = increment_count
            nodes["A"].next(nodes["A"]) 
            
            max_visits = 3
            flow = Flow(nodes["A"], {"max_visits": max_visits})
            loop_memory = Memory({})
            
            with pytest.raises(AssertionError, match=f"Maximum cycle count \\({max_visits}\\) reached for {nodes['A'].__class__.__name__}#{nodes['A']._node_order}"):
                await flow.run(loop_memory)
            
            assert loop_count[0] == max_visits
            assert loop_memory.count == max_visits
        
        async def test_error_immediately_if_loop_exceeds_maxvisits(self, nodes):
            """Should throw error immediately if loop exceeds max_visits (e.g. max_visits=2)."""
            nodes["A"].next(nodes["A"]) 
            
            max_visits = 2
            flow = Flow(nodes["A"], {"max_visits": max_visits})
            loop_memory = Memory({})
            
            with pytest.raises(AssertionError, match=f"Maximum cycle count \\({max_visits}\\) reached for {nodes['A'].__class__.__name__}#{nodes['A']._node_order}"):
                await flow.run(loop_memory)
    
    class TestFlowAsNode:
        """Tests for using a Flow as a Node (nesting)."""
        
        async def test_execute_nested_flow_as_single_node_step(self, nodes, memory):
            """Should execute a nested flow as a single node step."""
            nodes["B"].next(nodes["C"])
            sub_flow = Flow(nodes["B"])
            
            nodes["A"].next(sub_flow)
            sub_flow.next(nodes["D"]) 
            
            main_flow = Flow(nodes["A"])
            await main_flow.run(memory)
            
            assert nodes["A"].post_mock.call_count == 1
            assert nodes["B"].post_mock.call_count == 1
            assert nodes["C"].post_mock.call_count == 1
            assert nodes["D"].post_mock.call_count == 1
            
            assert memory.post_A is True
            assert memory.post_B is True
            assert memory.post_C is True
            assert memory.post_D is True
        
        async def test_nested_flow_prep_post_wrap_subflow_execution(self, nodes, memory):
            """Should run nested flow's prep/post methods around sub-flow execution."""
            nodes["B"].next(nodes["C"])
            sub_flow = Flow(nodes["B"])
            
            sub_flow.prep = AsyncMock()
            sub_flow.post = AsyncMock()
            
            async def subflow_prep(mem):
                mem.subflow_prep = True
                return None # PrepResultT for Flow is not used by its exec_runner
            
            async def subflow_post(mem, prep_res, exec_res):
                mem.subflow_post = True
                # exec_res here is the ExecutionTree from the sub_flow's execution
                return None 
            
            sub_flow.prep.side_effect = subflow_prep
            sub_flow.post.side_effect = subflow_post
            
            nodes["A"].next(sub_flow).next(nodes["D"])
            main_flow = Flow(nodes["A"])
            
            await main_flow.run(memory)
            
            assert memory.subflow_prep is True
            assert memory.post_B is True
            assert memory.post_C is True
            assert memory.subflow_post is True
            assert memory.post_D is True
            
            assert sub_flow.prep.call_count == 1
            sub_flow.post.assert_called_once() # Check it was called
            # To check args: sub_flow.post.assert_called_with(memory, None, ANY) # prep_res is None, exec_res is the log

        async def test_nested_flow_propagates_terminal_action_to_parent_flow(self, memory):
            """Should propagate a terminal action from a sub-flow to the parent flow."""
            BaseNode._next_id = 0
            main_start_node = BaseTestNode("MainStart") # id 0
            sub_node_a = BaseTestNode("SubA")           # id 1
            
            sub_node_b = BranchingNode("SubB")          # id 2
            sub_node_b.set_trigger("sub_flow_completed")
            
            main_end_node = BaseTestNode("MainEnd")     # id 3

            sub_node_a.next(sub_node_b)
            sub_flow = Flow(start=sub_node_a)           # id 4 (Flow itself is a BaseNode)

            main_start_node.next(sub_flow)
            sub_flow.on("sub_flow_completed", main_end_node)

            main_flow = Flow(start=main_start_node)     # id 5
            await main_flow.run(memory)

            assert memory["post_MainStart"] is True
            assert memory["post_SubA"] is True
            assert memory["post_SubB"] is True
            assert memory["post_MainEnd"] is True

            main_start_node.post_mock.assert_called_once()
            sub_node_a.post_mock.assert_called_once()
            sub_node_b.post_mock.assert_called_once() 
            main_end_node.post_mock.assert_called_once()
    
    class TestResultAggregation:
        """Tests for result aggregation using ExecutionTree."""
        
        async def test_return_correct_nested_actions_structure_for_simple_flow(self, nodes, memory):
            """Should return correct structure for a simple flow A -> B."""
            node_a = nodes["A"]
            node_b = nodes["B"]
            node_a.next(node_b)
            
            flow = Flow(node_a)
            result = await flow.run(memory)
            
            expected = {
                'order': str(node_a._node_order),
                'type': node_a.__class__.__name__,
                'triggered': {
                    DEFAULT_ACTION: [
                        {
                            'order': str(node_b._node_order),
                            'type': node_b.__class__.__name__,
                            'triggered': {DEFAULT_ACTION: []} # Node B is terminal
                        }
                    ]
                }
            }
            assert result == expected
        
        async def test_return_correct_structure_for_branching_flow(self, nodes):
            """Should return correct structure for branching flow."""
            # Reset BaseNode ID for predictable IDs
            BaseNode._next_id = 0
            branching_node = BranchingNode("Branch") # id 0
            node_b = BaseTestNode("B_local_branch")      # id 1
            node_c = BaseTestNode("C_local_branch")      # id 2
            node_d = BaseTestNode("D_local_branch")      # id 3

            branching_node.on("path_B", node_b)
            branching_node.on("path_C", node_c)
            node_b.next(node_d) 
            
            # Test path B: Branch -> B -> D
            branching_node.set_trigger("path_B")
            flow_b = Flow(branching_node)
            result_b = await flow_b.run(Memory({}))
            
            expected_b = {
                'order': str(branching_node._node_order),
                'type': branching_node.__class__.__name__,
                'triggered': {
                    "path_B": [
                        {
                            'order': str(node_b._node_order),
                            'type': node_b.__class__.__name__,
                            'triggered': {
                                DEFAULT_ACTION: [
                                    {
                                        'order': str(node_d._node_order),
                                        'type': node_d.__class__.__name__,
                                        'triggered': {DEFAULT_ACTION: []} # Node D is terminal
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
            assert result_b == expected_b
            
            # Test path C: Branch -> C
            # Need to use a new branching_node or flow to reset visit counts
            BaseNode._next_id = 0
            branching_node_c_path = BranchingNode("BranchCPath") # id 0
            node_b_c_path = BaseTestNode("B_CPath")              # id 1 (unused for path C trigger)
            node_c_c_path = BaseTestNode("C_CPath")              # id 2
            node_d_c_path = BaseTestNode("D_CPath")              # id 3 (unused for path C trigger)

            branching_node_c_path.on("path_B", node_b_c_path)
            branching_node_c_path.on("path_C", node_c_c_path)
            # node_b_c_path.next(node_d_c_path) # Not relevant for path C test

            branching_node_c_path.set_trigger("path_C")
            flow_c = Flow(branching_node_c_path)
            result_c = await flow_c.run(Memory({}))
            
            expected_c = {
                'order': str(branching_node_c_path._node_order),
                'type': branching_node_c_path.__class__.__name__,
                'triggered': {
                    "path_C": [
                        {
                            'order': str(node_c_c_path._node_order),
                            'type': node_c_c_path.__class__.__name__,
                            'triggered': {DEFAULT_ACTION: []} # Node C is terminal
                        }
                    ]
                }
            }
            assert result_c == expected_c
        
        async def test_return_correct_structure_for_multi_trigger(self, nodes, memory):
            """Should return correct structure for multi-trigger (fan-out)."""
            BaseNode._next_id = 0
            class MultiTrigger(BaseTestNode): # Inherits BaseTestNode, so uses its _node_order
                async def post(self, memory, prep_res, exec_res):
                    await super().post(memory, prep_res, exec_res)
                    self.trigger("out1")
                    self.trigger("out2")
            
            multi_node = MultiTrigger("Multi") # id 0
            node_b = BaseTestNode("B_multi")       # id 1
            node_c = BaseTestNode("C_multi")       # id 2
            
            multi_node.on("out1", node_b)
            multi_node.on("out2", node_c)
            
            flow = Flow(multi_node)
            result = await flow.run(memory)
            
            expected_triggered = {
                "out1": [
                    {
                        'order': str(node_b._node_order),
                        'type': node_b.__class__.__name__,
                        'triggered': {DEFAULT_ACTION: []} # Node B is terminal
                    }
                ],
                "out2": [
                    {
                        'order': str(node_c._node_order),
                        'type': node_c.__class__.__name__,
                        'triggered': {DEFAULT_ACTION: []} # Node C is terminal
                    }
                ]
            }
            
            assert result['order'] == str(multi_node._node_order)
            assert result['type'] == multi_node.__class__.__name__
            assert result['triggered'] is not None
            assert set(result['triggered'].keys()) == {"out1", "out2"}
            assert result['triggered']["out1"] == expected_triggered["out1"]
            assert result['triggered']["out2"] == expected_triggered["out2"]

