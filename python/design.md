# BrainyFlow Python Library Design

This document outlines the design of the BrainyFlow Python library, a framework for building and executing computational graphs, particularly suited for asynchronous workflows like AI agent interactions or complex data processing pipelines.

## Core Concepts

BrainyFlow is built around the concepts of Nodes, Flows, and Memory management.

- **Nodes:** Represent individual units of computation or logic within the graph.
- **Flows:** Orchestrate the execution sequence of connected nodes.
- **Memory:** Manages the state shared across nodes during execution, with support for both global and local scopes.

## Components

### 1. Memory (`brainyflow.Memory`)

Manages the state accessible to nodes during execution.

- **Dual Scope:**
  - `_global`: A dictionary representing the shared state across the entire flow execution.
  - `_local`: A dictionary representing state specific to a particular execution path or branch. Useful for passing data between directly connected nodes without polluting the global scope or for managing state in parallel branches.
- **Attribute Access:** Provides attribute-style access (`memory.my_var`) via `__getattr__`, prioritizing the local scope and falling back to the global scope. Setting attributes via `__setattr__` always writes to the global scope, removing the key from local if it exists. Reserved names (`global`, `local`, `_global`, `_local`) cannot be set.
- **Dictionary Access:** Supports dictionary-style access (`memory['my_key']`) via `__getitem__` with the same scope prioritization for getting values. Setting values via `__setitem__` always writes to the global scope, removing the key from local if it exists.
- **Membership Testing:** Supports the `in` operator via `__contains__` to check for key existence in either local or global scope.
- **Local Property:** The `local` property provides direct read access to the `_local` dictionary.
- **Cloning:** The `clone(forking_data=None)` method creates a new `Memory` instance. The global store is shared by reference, while the local store is deep-copied. Optional `forking_data` can be provided to initialize or update the new local store. This is crucial for branching and parallel execution to ensure state isolation where needed.

### 2. BaseNode (`brainyflow.BaseNode`)

The abstract base class for all nodes in the graph.

- **Lifecycle Methods:** Defines the standard execution lifecycle for a node:
  - `prep(memory)`: Asynchronous preparation phase. Can be used to fetch data, initialize resources, etc. Receives the current `Memory`. Returns a result (`prep_res`).
  - `exec(prep_res)`: Asynchronous execution phase (intended to be overridden by subclasses like `Node`). Performs the core logic. Receives the result from `prep`. Returns a result (`exec_res`).
  - `post(memory, prep_res, exec_res)`: Asynchronous post-processing phase. Can be used for cleanup, logging, or triggering subsequent nodes. Receives `Memory` and results from `prep` and `exec`.
- **Graph Connectivity:**
  - `successors`: A dictionary mapping action strings (e.g., 'success', 'failure', 'default') to lists of successor nodes.
  - `on(action, node)` / `next(node, action='default')`: Methods to define connections between nodes based on actions. Returns the added node for chaining.
  - `__rshift__` (`>>`): Syntactic sugar for connecting to the `DEFAULT_ACTION`.
  - `__sub__` (`-`) and `ActionLinker`: Syntactic sugar for connecting via specific actions (`node - "action" >> next_node`).
  - `get_next_nodes(action=DEFAULT_ACTION)`: Retrieves the list of successor nodes for a given action.
- **Triggering:**
  - `trigger(action, forking_data=None)`: Called _only_ within the `post` method to specify which action(s) should be taken next and optionally pass data (`forking_data`) into the local memory of the subsequent branch(es). Attempting to call outside `post` raises a `RuntimeError`.
  - `list_triggers(memory)`: Returns a list of `(action, memory_clone)` tuples based on calls to `trigger`. If no triggers are called, it defaults to the `DEFAULT_ACTION` with a clone of the current memory.
- **Execution Runner:**
  - `exec_runner(memory, prep_res)`: Abstract method that must be implemented by subclasses to define the core execution logic, potentially including features like retries.
  - `run(memory, propagate=False)`: Executes the full node lifecycle (`prep`, `exec_runner`, `post`). If `propagate` is `True` (used internally by `Flow`), returns the list of triggers; otherwise, returns the result of `exec_runner`. Warns if called on a node with successors outside a `Flow`. Accepts a dictionary or `Memory` object for initial memory.
- **Cloning:** `clone(seen=None)` method for deep copying the node and its successor graph, handling cycles using the `seen` dictionary.
- **Identification:** Each node instance gets a unique, sequential `_node_order` ID upon creation.

### 3. Node (`brainyflow.Node`)

A concrete implementation of `BaseNode` that adds retry logic.

- **Retry Mechanism:**
  - `max_retries`: Maximum number of times `exec` will be attempted (default 1, meaning one attempt).
  - `wait`: Delay (in seconds) between retry attempts (default 0).
  - `cur_retry`: Tracks the current retry attempt number (0-indexed).
- **Error Handling:**
  - `exec_fallback(prep_res, error)`: An asynchronous method called if all retry attempts fail. The default implementation re-raises the final error (wrapped in `NodeError` which includes the `retry_count`). Subclasses can override this for custom fallback behavior.
- **Execution:** Implements `exec_runner` to incorporate the retry logic around calling the node's `exec` method.

### 4. Flow (`brainyflow.Flow`)

Orchestrates the execution of a graph of connected nodes sequentially. Inherits from `BaseNode` but overrides execution logic.

- **Entry Point:** Initialized with a `start` node.
- **Execution Logic:**
  - `run_node(node, memory)`: Executes a single node within the flow context. It clones the node, runs its lifecycle (`run(memory, propagate=True)`), checks for cycles, and processes the resulting triggers by recursively calling `run_nodes` for successors.
  - `run_nodes(nodes, memory)`: Executes a list of nodes sequentially for a given branch using the provided memory.
  - `run_tasks(tasks)`: Executes a list of asynchronous task functions (lambdas wrapping `run_node` or `_process_trigger`) sequentially.
  - `exec_runner(memory, prep_res)`: Overrides the base implementation to start the flow execution from the `start` node by calling `run_node`. Resets `visit_counts`.
  - `_process_trigger(action, next_nodes, node_memory)`: Helper method to handle the results of a single trigger, running subsequent nodes if they exist.
- **Cycle Detection:** Uses `visit_counts` and `options['max_visits']` (default 5) to prevent infinite loops by limiting the number of times any single node (identified by `_node_order`) can be visited during a flow execution. Raises `RuntimeError` if the limit is exceeded.
- **Result:** Returns a nested dictionary structure where keys are actions and values are lists of results from the branches corresponding to those actions. Example: `{'default': [{'action1': [...]}, {'action2': [...]}]}`.

### 5. ParallelFlow (`brainyflow.ParallelFlow`)

A subclass of `Flow` that enables parallel execution of branches.

- **Concurrency:** Overrides `run_tasks(tasks)` to use `asyncio.gather`, allowing multiple branches triggered from a single node (or multiple nodes run via `run_nodes`) to execute concurrently rather than sequentially.

## Usage Pattern

1.  **Define Nodes:** Create classes inheriting from `Node` (or `BaseNode`) and implement `prep`, `exec`, and `post` methods.
2.  **Connect Nodes:** Instantiate nodes and connect them using `>>` (default action) or `- "action" >>` (specific action).
3.  **Create Flow:** Instantiate `Flow` or `ParallelFlow` with the starting node.
4.  **Execute:** Call the `run(initial_memory)` method on the flow instance with an initial global memory dictionary. Use `await` as `run` is asynchronous.

## Error Handling

- Nodes can implement retry logic using the `Node` class.
- `exec_fallback` provides a hook for custom behavior after retries are exhausted.
- `NodeError` is raised by `Node`'s default fallback, containing `retry_count` information.
- Flows detect and raise `RuntimeError` for excessive cycles.
- Standard Python exceptions raised during `prep`, `exec`, or `post` will propagate unless caught by retry logic or custom error handling.
