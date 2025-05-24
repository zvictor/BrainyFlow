# BrainyFlow Python Test Plan

This document outlines the testing strategy for the Python port of the `brainyflow` library, ensuring parity with the TypeScript implementation.

## 1. Goals

- Ensure the Python implementation maintains complete feature parity with the TypeScript implementation
- Verify core abstractions (`Memory`, `BaseNode`, `Node`, `Flow`, `ParallelFlow`) function identically to their TypeScript counterparts
- Validate state management, flow control, error handling, and composition work as expected
- Guarantee compatibility between Python and TypeScript versions of BrainyFlow
- Provide a comprehensive test suite that developers can use to verify changes

## 2. Testing Framework

- **Runner:** pytest
- **Assertions:** pytest's built-in assertion functionality
- **Mocks/Spies:** pytest-mock for mocking function calls
- **Fixtures:** pytest fixtures for test setup and reuse
- **Async Testing:** pytest-asyncio for testing asynchronous functionality
- **Coverage:** pytest-cov for coverage reporting

## 3. Test Categories and Cases

### 3.1. `Memory` Class

- **Initialization:**
  - `Memory()` correctly initializes global and optional local stores
  - Global and local stores are properly accessible
- **Proxy Behavior (Reading):**
  - Reads property from local store if present
  - Falls back to global store if property not in local store
  - Returns `None` if property exists in neither store
  - Correctly accesses the `local` property (internal `_local` store)
- **Proxy Behavior (Writing):**
  - Writes property to global store by default (`memory.prop = value`)
  - Removes property from local store if it exists when writing to global
  - Raises error when attempting to set reserved properties (`global`, `local`, `_global`, `_local`)
- **Cloning (`clone()`):**
  - Creates a new `Memory` instance
  - Shares the same global store reference
  - Creates a deep copy of the local store
  - Correctly merges `forking_data` (deep copied) into the new local store
  - Handles nested objects properly

### 3.2. `BaseNode` & `Node` (RetryNode)

- **Lifecycle Methods:**
  - `prep`, `exec`, `post` are called in the correct order during `run()`
  - `prep` receives the correct `Memory` instance
  - `exec` receives the result from `prep`
  - `post` receives `Memory`, `prep` result, and `exec` result
  - Default implementations of lifecycle methods do nothing and don't raise errors
- **Graph Connections:**
  - `on(action, node)` adds the node to the correct action's successors list
  - `next(node, action=DEFAULT_ACTION)` adds the node correctly
  - `get_next_nodes(action)` returns the correct list of successor nodes
  - `get_next_nodes(action)` returns an empty list if no successors exist
  - `get_next_nodes(action)` warns if a non-default action is requested but only other actions exist
- **Triggering:**
  - `trigger(action, forking_data={})` correctly stores triggers internally
  - Calling `trigger()` outside of `post` raises an error
  - `list_triggers()` correctly processes stored triggers, creating cloned memory
  - `list_triggers()` returns `[[DEFAULT_ACTION, cloned_memory]]` if no triggers were called
- **Execution (`run()`):**
  - `run(memory)` executes the full lifecycle (`prep` → `exec_runner` → `post`)
  - `run(memory, propagate=False)` returns the result of `exec_runner`
  - `run(memory, propagate=True)` returns the result of `list_triggers` (list of `[action, memory]` tuples)
  - Warns if `run()` is called on a node with successors
- **Cloning (`clone()`):**
  - Creates a deep copy of the node instance
  - Maintains the correct class hierarchy
  - Recursively clones successors
  - Handles cyclic graph structures correctly using the `seen` dictionary
- **`Node` (Retry Logic):**
  - `exec` is retried `max_retries - 1` times upon raising an exception
  - `wait` option introduces the correct delay between retries
  - `exec_fallback` is called with the final error (including `retry_count`) if all retries fail
  - `exec_fallback`'s return value becomes the `exec_res` passed to `post`
  - If `exec_fallback` raises an exception, it propagates
  - `cur_retry` property reflects the current attempt number within `exec` and `exec_fallback`

### 3.3. `Flow` Class

- **Initialization:**
  - Stores the `start` node correctly
  - Sets default `max_visits` if not provided
- **Execution (`run()`):**
  - Starts execution from the `start` node
  - Executes nodes sequentially based on `DEFAULT_ACTION` triggers
  - Executes nodes based on specific named action triggers
  - Correctly clones node instances before running them
  - Correctly clones memory for each triggered path, applying `forking_data`
  - Propagates state changes in the global store correctly
  - Isolates state changes in the local store to specific branches
  - Aggregates results into the correct nested structure
  - Handles terminal nodes (nodes with no further triggers or successors) correctly
- **Cycle Detection:**
  - Raises an error if a node is visited more than `max_visits` times during a single `run()`
  - `visit_counts` are reset for each `run()`
- **Flow as Node (Nesting):**
  - A `Flow` instance can be used as a node within another `Flow`
  - The parent flow correctly executes the nested flow's `prep`, `exec_runner` (which runs the sub-flow), and `post`
  - The nested flow's final state updates the shared memory correctly
  - The nested flow's `post` method can trigger successors in the parent flow
- **`run_tasks` (Sequential):**
  - Executes tasks provided to it one after another, awaiting each completion

### 3.4. `ParallelFlow` Class

- **`run_tasks` (Parallel):**
  - Overrides `run_tasks` to execute provided tasks concurrently using `asyncio.gather`
  - Verify that branches triggered by a single node run in parallel
  - Ensure results from parallel branches are correctly aggregated
  - Test state updates from parallel branches
  - Validate timing of parallel vs sequential execution
  - Test combination of parallel and sequential processing

## 4. Test Structure

The test suite will be organized into modules corresponding to the main components of BrainyFlow:

```
python/tests/
├── conftest.py              # Shared fixtures and utilities
├── design.md                # This test design document
├── test_memory.py           # Memory tests
├── test_node.py             # BaseNode and Node tests
├── test_flow.py             # Flow tests
└── test_parallel_flow.py    # ParallelFlow tests
```

Each test module will use fixtures defined in `conftest.py` for common setup and teardown operations, such as creating Memory instances, simple nodes, and basic flows.

Helper classes will be defined for testing specific behaviors, such as:

- `TestNode`: A basic node implementation for testing node lifecycle
- `BranchingNode`: A node that can be configured to trigger specific actions
- `DelayedNode`: A node with configurable execution delays for testing parallel execution
- `ErrorNode`: A node that fails a configurable number of times for testing retry logic

## 5. Python-Specific Adaptations

Several adaptations will be necessary to account for language differences:

1. **Naming Conventions:**

   - TypeScript: camelCase methods (e.g., `getNextNodes`)
   - Python: snake_case methods (e.g., `get_next_nodes`)

2. **Property Access:**

   - TypeScript: Uses JavaScript's Proxy API
   - Python: Uses `__getattr__`, `__setattr__`, and `__getattribute__`

3. **Deep Cloning:**

   - TypeScript: Uses `structuredClone`
   - Python: Uses `copy.deepcopy`

4. **Async Implementation:**

   - TypeScript: Uses JavaScript's Promise system
   - Python: Uses asyncio with async/await

5. **Type Hinting:**
   - Python: Use type annotations (PEP 484) that correspond to TypeScript types
   - Use typing.TypeVar and Generic for generic type parameters

## 6. Execution

Tests can be run using pytest:

```bash
cd python
pytest tests/
```

For focused testing of specific components:

```bash
pytest tests/test_memory.py          # Test just Memory
pytest tests/test_node.py            # Test just Node
pytest tests/test_flow.py            # Test just Flow
pytest tests/test_parallel_flow.py   # Test just ParallelFlow
```

For coverage reporting:

```bash
pytest tests/ --cov=brainyflow --cov-report=html
```

## 7. Testing Utilities

The test suite will include several utilities in `conftest.py`:

- `async_sleep`: A utility function to simulate delays in async functions
- Mock functions for spying on method calls
- Helper functions for time-based assertions in parallel execution tests
- Fixtures for commonly used test objects

These utilities will ensure that tests are consistent, reliable, and accurately reflect the behavior of both the TypeScript and Python implementations.
