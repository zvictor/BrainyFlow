from __future__ import annotations
import asyncio
import copy
import warnings
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, Tuple, Type, TypeAlias, TypeVar, Generic, Callable, Union, cast, TypedDict, Literal, overload, Awaitable, Sequence, runtime_checkable

DEFAULT_ACTION = 'default'
Action = str
SharedStore = Dict[str, Any]
G = TypeVar('G', bound=SharedStore)
L = TypeVar('L', bound=SharedStore)
T = TypeVar('T')
PrepResultT = TypeVar('PrepResultT')
ExecResultT = TypeVar('ExecResultT')
ActionT = TypeVar('ActionT', bound=str)
AnyNode: TypeAlias = 'BaseNode[G, Any, Any, Any, Any]'
class ExecutionTree(TypedDict):
    order: str
    type: str
    triggered: Optional[Dict[Action, List["ExecutionTree"]]]
class Trigger(TypedDict):
    action: Action
    forking_data: SharedStore

def _get_from_stores(key: str, primary: SharedStore, secondary: SharedStore | None = None, Error: Type[Exception] = KeyError) -> Any:
    if key in primary: return primary[key]
    if secondary is not None and key in secondary: return secondary[key]
    raise Error(f"Key '{key}' not found in store{'s' if secondary else ''}")

def _delete_from_stores(key: str, primary: SharedStore, secondary: SharedStore | None = None) -> None:
    if key not in primary and (secondary is None or key not in secondary): raise KeyError(key)
    if key in primary: del primary[key]
    if secondary is not None and key in secondary: del secondary[key]

class Memory(Generic[G, L]):
    """
    Manager of global and local state. Provides a dual-scope approach to state management:
    - Global store: Shared across the entire flow
    - Local store: Specific to a particular execution path
    """
    def __init__(self, _global: G, _local: Optional[L] = None):
        object.__setattr__(self, '_global', _global)
        object.__setattr__(self, '_local', _local if _local else cast(L, {}))
    def __getattr__(self, key: str) -> Any: return _get_from_stores(key, self._local, self._global, Error=AttributeError)
    def __getitem__(self, key: str) -> Any: return _get_from_stores(key, self._local, self._global)
    def _set_value(self, key: str, value: Any) -> None:
        assert key not in ['global', 'local', '_global', '_local', 'clone', 'create'], f"Reserved property '{key}' cannot be set"
        if key in self._local:
            del self._local[key]
        self._global[key] = value
    def __setattr__(self, name: str, value: Any) -> None: self._set_value(name, value)
    def __setitem__(self, key: str, value: Any) -> None: self._set_value(key, value)
    def __delattr__(self, key: str) -> None: _delete_from_stores(key, self._global, self._local)
    def __delitem__(self, key: str) -> None: _delete_from_stores(key, self._global, self._local)
    def __contains__(self, key: str) -> bool: return key in self._local or key in self._global
    def clone(self, forking_data: Optional[SharedStore] = None) -> Memory[G, L]:
        new_local = copy.deepcopy(self._local)
        new_local.update(copy.deepcopy(forking_data or {}))
        return Memory[G, L](self._global, cast(L, new_local))
    @property
    def local(self) -> L:
        class LocalProxy:
            def __init__(self, store: L) -> None: self.store = store
            def __getattr__(self, key: str) -> Any: return _get_from_stores(key, self.store, Error=AttributeError)
            def __getitem__(self, key: str) -> Any: return _get_from_stores(key, self.store)
            def __setattr__(self, key: str, value: Any) -> None: self.store[key] = value
            def __setitem__(self, key: str, value: Any) -> None: self.store[key] = value
            def __delattr__(self, key: str) -> None: _delete_from_stores(key, self.store)
            def __delitem__(self, key: str) -> None: _delete_from_stores(key, self.store)
            def __contains__(self, key: str) -> bool: return key in self.store
            def __eq__(self, other: object) -> bool:
                if isinstance(other, LocalProxy): return self.store == other.store
                return self.store == other
            def __repr__(self) -> str: return self.store.__repr__()
        return cast(L, LocalProxy(self._local))

@runtime_checkable
class NodeError(Protocol):
    retry_count: int = 0

class BaseNode(Generic[G, L, ActionT, PrepResultT, ExecResultT], ABC):
    """
    Base class for all computational nodes in a flow.
    Implements the core lifecycle (prep, exec, post) and graph connection logic.
    
    Type Parameters:
    - G: Global memory store type
    - L: Local memory store type
    - ActionT: Type of actions this node can trigger
    - PrepResultT: Return type of prep method
    - ExecResultT: Return type of exec method
    """
    _next_id = 0
    
    def __init__(self) -> None:
        self.successors: Dict[Action, List[AnyNode[G]]] = {}  # dict of action -> list of nodes
        self._triggers: List[Trigger] = []  # list of dicts with action and forking_data
        self._locked: bool = True  # Prevent trigger calls outside post()
        self._node_order: int = BaseNode._next_id
        BaseNode._next_id += 1
    
    def clone(self, seen: Optional[Dict[AnyNode[G], AnyNode[G]]] = None) -> BaseNode[G, L, ActionT, PrepResultT, ExecResultT]:
        """Create a deep copy of the node including its successors."""
        seen = seen or {}
        if self in seen:
            return seen[self]
        
        # Create new instance maintaining class hierarchy
        cloned = type(self).__new__(type(self))
        seen[self] = cloned
        
        # Copy attributes except successors
        for key, value in self.__dict__.items():
            if key != 'successors':
                # Shallow-copy by default; deep-copy lists/dicts/sets to prevent sharing
                setattr(cloned, key, copy.deepcopy(value) if isinstance(value, (list, dict, set)) else value)
        
        # Clone successors with cycle detection
        cloned.successors = {}
        for action, nodes in self.successors.items():
            cloned.successors[action] = [
                node.clone(seen) if node else node for node in nodes
            ]
        
        return cloned
    def on(self, action: Action, node: AnyNode[G]) -> AnyNode[G]:
        """Add a successor node for a specific action."""
        if action not in self.successors:
            self.successors[action] = []
        self.successors[action].append(node)
        return node
    
    def next(self, node: AnyNode[G], action: Action = DEFAULT_ACTION) -> AnyNode[G]:
        """Convenience method equivalent to on()."""
        return self.on(action, node)
    
    def __rshift__(self, other: AnyNode[G]) -> AnyNode[G]:
        """Implement node_a >> node_b syntax for default action"""
        return self.next(other)
    
    def __sub__(self, action: Action):
        """Implement node_a - "action" syntax for action selection"""
        that = self
        class ActionLinker:
            def __rshift__(self, other: AnyNode[G]) -> AnyNode[G]:
                """Implement - "action" >> node_b syntax"""
                return that.on(action, other)
        return ActionLinker()
    
    def get_next_nodes(self, action: Action = DEFAULT_ACTION) -> List[AnyNode[G]]:
        """Get successor nodes for a specific action."""
        next_nodes = self.successors.get(action, [])
        if not next_nodes and action != DEFAULT_ACTION and self.successors:
            warnings.warn(f"Flow ends: '{action}' not found in {list(self.successors.keys())}", stacklevel=2)
        return next_nodes
    
    async def prep(self, memory: Memory[G, L]) -> PrepResultT:
        """Prepare phase - override in subclasses."""
        return cast(PrepResultT, None)
    
    async def exec(self, prep_res: PrepResultT) -> ExecResultT:
        """Execute phase - override in subclasses."""
        return cast(ExecResultT, None)
    
    async def post(self, memory: Memory[G, L], prep_res: PrepResultT, exec_res: ExecResultT) -> None:
        """Post-processing phase - override in subclasses."""
        pass
    
    def trigger(self, action: ActionT, forking_data: Optional[SharedStore] = None) -> None:
        """Trigger a successor action with optional forking data."""
        assert not self._locked, "An action can only be triggered inside post()"
        
        self._triggers.append({
            "action": action,
            "forking_data": forking_data or {}
        })
    
    def list_triggers(self, memory: Memory[G, L]) -> List[Tuple[Action, Memory[G, L]]]:
        """Process triggers or return default."""
        if not self._triggers:
            return [(DEFAULT_ACTION, memory.clone())]
        
        return [(t["action"], memory.clone(t["forking_data"])) for t in self._triggers]
    
    @abstractmethod
    async def exec_runner(self, memory: Memory[G, L], prep_res: PrepResultT) -> ExecResultT:
        """Core execution logic - must be implemented by subclasses."""
        pass
    
    @overload
    async def run(self, memory: Union[Memory[G, L], G], propagate: Literal[True]) -> List[Tuple[Action, Memory[G, L]]]: ...
    @overload
    async def run(self, memory: Union[Memory[G, L], G], propagate: Literal[False] = False) -> ExecResultT: ...
    async def run(self, memory: Union[Memory[G, L], G], propagate: bool = False) -> Union[List[Tuple[Action, Memory[G, L]]], ExecResultT]:
        """Run the node's full lifecycle (prep → exec → post)."""
        if not isinstance(memory, Memory):
            memory = Memory[G, L](memory)
        
        self._triggers = []
        prep_res = await self.prep(memory)
        exec_res = await self.exec_runner(memory, prep_res)
        
        self._locked = False
        await self.post(memory, prep_res, exec_res)
        self._locked = True
        
        if propagate:
            return self.list_triggers(memory)
        return exec_res

class Node(BaseNode[G, L, ActionT, PrepResultT, ExecResultT]):
    """
    Standard node implementation with retry capabilities.
    
    Attributes:
        max_retries: Maximum number of execution attempts
        wait: Seconds to wait between retry attempts
        cur_retry: Current retry attempt (0-indexed)
    """
    def __init__(self, max_retries: int = 1, wait: float = 0) -> None:
        """Initialize a Node with retry configuration."""
        super().__init__()
        self.max_retries = max_retries
        self.wait = wait
        self.cur_retry = 0
    
    async def exec_fallback(self, prep_res: PrepResultT, error: Exception) -> ExecResultT:
        """Called when all retry attempts fail."""
        raise error
    
    async def exec_runner(self, memory: Memory[G, L], prep_res: PrepResultT) -> ExecResultT:
        """Run exec with retry logic."""
        for attempt in range(self.max_retries):
            self.cur_retry = attempt
            try:
                return await self.exec(prep_res)
            except Exception as error:
                if not hasattr(error, 'retry_count'):
                    error.retry_count = attempt + 1 # type: ignore
                if attempt < self.max_retries - 1:
                    if self.wait > 0:
                        await asyncio.sleep(self.wait)
                    continue
                return await self.exec_fallback(prep_res, error)
        raise RuntimeError("Unreachable: exec_runner should have returned or raised in the loop") # This should never happen if max_retries > 0

class Flow(BaseNode[G, L, ActionT, PrepResultT, ExecutionTree]):
    """
    Orchestrates the execution of a graph of nodes sequentially.
    
    Attributes:
        start: The entry point node of the flow
        options: Configuration options like max_visits
        visit_counts: Tracks node visits for cycle detection
    """
    def __init__(self, start: AnyNode[G], options: Optional[Dict[str, Any]] = None) -> None:
        """Initialize a Flow with a start node and options."""
        super().__init__()
        self.start = start
        self.options = options or {"max_visits": 15}
        self.visit_counts: Dict[str, int] = {}
    
    async def exec(self, prep_res: PrepResultT) -> ExecutionTree:
        raise RuntimeError("This method should never be called in a Flow")
    
    async def exec_runner(self, memory: Memory[G, L], prep_res: PrepResultT) -> ExecutionTree:
        """Run the flow starting from the start node."""
        self.visit_counts = {}  # Reset visit counts
        return await self.run_node(self.start, memory)
    
    async def run_tasks(self, tasks: Sequence[Callable[[], Awaitable[T]]]) -> List[T]:
        """Run tasks sequentially."""
        results: List[T] = []
        for task in tasks:
            results.append(await task())
        return results
    
    async def run_nodes(self, nodes: List[AnyNode[G]], memory: Memory[G, L]) -> List[ExecutionTree]:
        """Run a list of nodes with the given memory."""
        tasks: List[Callable[[], Awaitable[ExecutionTree]]] = [
            (lambda n=node, m=memory: lambda: self.run_node(n, m))() for node in nodes
        ]
        return await self.run_tasks(tasks)
    
    async def run_node(self, node: AnyNode[G], memory: Memory[G, L]) -> ExecutionTree:
        """Run a node with cycle detection and return its execution log."""
        node_order = str(node._node_order)
        # Check for cycles
        current_visit_count = self.visit_counts.get(node_order, 0) + 1
        assert current_visit_count <= self.options["max_visits"], f"Maximum cycle count ({self.options['max_visits']}) reached for {node.__class__.__name__}#{node_order}"
        self.visit_counts[node_order] = current_visit_count
        
        cloned_node = node.clone()
        triggers = await cloned_node.run(memory.clone(), True)
        
        triggered: Dict[Action, List[ExecutionTree]] = {}
        tasks: List[Callable[[], Awaitable[Tuple[Action, List[ExecutionTree]]]]] = []
        for action, node_memory in triggers:
            next_nodes = cloned_node.get_next_nodes(action)
            if next_nodes:
                tasks.append((lambda act=action, nn_list=next_nodes, nm_mem=node_memory: \
                                 lambda: self._process_trigger(act, nn_list, nm_mem))())
            else:
                self._triggers.append({ "action": action, "forking_data": node_memory._local })
                triggered[action] = []

        tree: List[Tuple[Action, List[ExecutionTree]]] = await self.run_tasks(tasks)
        for action, resulting_node_logs in tree:
            triggered[action] = resulting_node_logs
            
        return { 'order': node_order, 'type': node.__class__.__name__, 'triggered': triggered if triggered else None }
    
    async def _process_trigger(self, action: Action, next_nodes: List[AnyNode[G]], node_memory: Memory[G, L]) -> Tuple[Action, List[ExecutionTree]]:
        """Process a single trigger by running its next_nodes."""
        return (action, await self.run_nodes(next_nodes, node_memory))

class ParallelFlow(Flow[G, L, ActionT, PrepResultT]):
    """Orchestrates execution of a graph of nodes with parallel branching."""    
    async def run_tasks(self, tasks: Sequence[Callable[[], Awaitable[T]]]) -> List[T]:
        if not tasks:
            return []
        return await asyncio.gather(*(task() for task in tasks))
