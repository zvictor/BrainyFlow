# Brainyflow TypeScript Library Design

This document describes the design and implementation of the Brainyflow TypeScript library (`brainyflow.ts`).

## 1. High-Level Purpose

The Brainyflow library provides a structured framework for defining, managing, and executing complex processes modeled as computational graphs. Key goals include:

- **Modularity:** Breaking down processes into reusable, independent units of work (Nodes).
- **Flow Control:** Defining clear execution paths, including sequential, conditional (action-based), and parallel flows.
- **State Management:** Providing a flexible memory system with global (shared) and local (forked) state scopes.
- **Resilience:** Incorporating features like automatic retries for transient failures and cycle detection in flows.
- **Composability:** Allowing flows themselves to be treated as nodes within larger flows.

It enables developers to build sophisticated workflows for tasks like data processing pipelines, multi-step API interactions, agent-based systems, and more, while managing complexity and state effectively.

## 2. Core Abstractions

The library is built around several key abstractions:

- **`Memory`:** Manages the state accessible during workflow execution. It separates state into a shared `__global` store and a `__local` store specific to an execution path, facilitating data isolation and controlled propagation via proxy-based access.
- **`BaseNode`:** The abstract base class for all computational units in the graph. It defines the core lifecycle (`prep`, `exec`, `post`), connection mechanisms (`on`, `next`), the concept of triggering subsequent nodes based on `Action`s, and cloning logic. It also includes a unique `__nodeOrder` identifier.
- **`Node` (aliased from `RetryNode`):** The standard node implementation extending `BaseNode`. It adds automatic retry logic with configurable attempts and delays to the `exec` phase via the `execRunner` method, enhancing robustness.
- **`Flow`:** Orchestrates the execution of a graph of connected nodes, starting from a defined entry point. It manages node execution order (sequential by default), memory cloning for branches, aggregates results into a nested execution tree, and includes cycle detection (`maxVisits`).
- **`ParallelFlow`:** A subclass of `Flow` that executes independent branches of the graph concurrently, suitable for performance optimization when tasks can run in parallel.

## 3. Detailed Implementation

### 3.1. `Memory` Class

- **Purpose:** To manage global and local state during flow execution using distinct internal stores (`__global`, `__local`).
- **Mechanism:** Uses a JavaScript `Proxy` to intercept property access.
  - **Get:** Checks the `__local` store first. If the property is not found, it checks the `__global` store. Special properties like `clone` and `local` (accessing `__local`) are handled directly.
  - **Set:** Writes properties directly to the `__global` store by default after ensuring the property is removed from the `__local` store. Protects reserved property names (`global`, `local`, `__global`, `__local`).
- **Cloning (`clone(forkingData?)`):** Creates a _new_ `Memory` instance wrapped in a `Proxy`. The `__global` store reference is shared, but the `__local` store is _deep-cloned_ using `structuredClone`. Optional `forkingData` is merged into the new local store using `structuredClone` as well. This is crucial for state isolation when branching in a `Flow`.

### 3.2. `BaseNode` Abstract Class

- **Purpose:** The fundamental template for a single task or step.
- **Properties:**
  - `successors: Map<Action, BaseNode[]>`: Stores directed connections to subsequent nodes, keyed by an `Action` string (or `DEFAULT_ACTION`).
  - `triggers: Trigger[]`: Temporarily stores actions and forking data specified during the `post` phase.
  - `locked: boolean`: Prevents `trigger` calls outside the `post` method.
  - `__nodeOrder: number`: A unique, auto-incrementing identifier assigned upon instantiation, used for tracking nodes (e.g., in `Flow` cycle detection).
- **Graph Definition Methods:**
  - `on(action, node)`: Adds `node` as a successor for the given `action`. Returns the added `node`.
  - `next(node, action = DEFAULT_ACTION)`: Convenience method, equivalent to `on`. Returns the added `node`.
  - `getNextNodes(action)`: Retrieves the array of successor nodes for a given action, returning an empty array if none are found. Warns if a non-default action has no successors but other successors exist.
- **Lifecycle Methods (intended to be overridden or implemented by subclasses):**
  - `prep(memory)`: Asynchronous setup phase before `exec`. Receives the current `Memory`. Default implementation does nothing.
  - `exec(prepRes)`: Asynchronous core logic of the node. Receives the result from `prep`. Default implementation does nothing. _Note: `execRunner` is the method typically overridden for execution logic, especially with retries._
  - `post(memory, prepRes, execRes)`: Asynchronous finalization phase after `exec`. Receives `Memory` and results from `prep` and `exec`. This is the _only_ place `trigger` should be called. Default implementation does nothing.
- **Execution Control:**
  - `trigger(action, forkingData = {})`: Called within `post` to signal which `action` transition should occur and what `forkingData` (if any) should be added to the _local_ memory for that specific path. Throws an error if called outside `post`.
  - `listTriggers(memory)`: Internal helper to process the `triggers` array after `post`, creating cloned memory instances for each triggered path. Returns `[[DEFAULT_ACTION, memory.clone()]]` if no specific triggers were set.
  - `execRunner(memory, prepRes)`: _Abstract_. Internal method called by `run` to execute the core logic (potentially with retries, as in `RetryNode`). Must be implemented by concrete subclasses like `RetryNode`.
  - `run(memory | globalStore, propagate?)`: Executes the node's full lifecycle (`prep` -> `execRunner` -> `post`).
    - Accepts either a full `Memory` object or just a `globalStore` (creating a default `Memory` internally).
    - If `propagate` is `true`, it returns the result of `listTriggers` (an array of `[action, memory]` tuples for the next steps).
    - If `propagate` is `false` or omitted, it returns the result of `execRunner`.
    - Warns if run directly on a node with successors, as they won't be executed (use `Flow` for graph execution).
- **Cloning (`clone(seen?)`):** Creates a deep copy of the node and its successors recursively, essential for `Flow` execution to run on a copy of the graph definition. Uses `Object.create` to maintain the prototype chain and copies properties. Uses a `seen` map to handle cyclic graphs correctly during successor cloning.

### 3.3. `RetryNode` Class (Exported as `Node`)

- **Purpose:** Provides a concrete `BaseNode` implementation with built-in retry logic for the `exec` phase.
- **Inheritance:** Extends `BaseNode`.
- **Configuration:**
  - `constructor({ maxRetries?, wait? })`: Sets the maximum number of retry attempts (`maxRetries`, default 1) and the waiting period in seconds (`wait`, default 0) between attempts.
- **Error Handling:**
  - `execFallback(prepRes, error)`: An overridable method called if all retry attempts fail. The default implementation re-throws the final error (augmented with `retryCount`).
- **Execution Override:**
  - `execRunner(memory, prepRes)`: Implements the retry loop. It calls the node's `exec` method within a `try...catch` block. On error, it waits (if `wait > 0`) and retries up to `maxRetries`. If all retries fail, it calls `execFallback`.

### 3.4. `Flow` Class

- **Purpose:** Orchestrates the execution of a graph of nodes sequentially, managing state and preventing infinite loops.
- **Inheritance:** Extends `BaseNode`.
- **Initialization:**
  - `constructor(start, options?)`: Requires the starting `BaseNode` of the workflow and accepts optional `options` like `maxVisits` (default 15) for cycle detection.
- **Properties:**
  - `start`: The entry point node of the flow.
  - `visitCounts`: A `Map` to track how many times each node (identified by `__nodeOrder`) has been visited during a single `run` execution to detect cycles.
  - `options`: Stores configuration like `maxVisits`.
- **Execution Logic:**
  - `exec()`: Throws an error – Flows orchestrate; they don't perform work themselves via `exec`.
  - `execRunner(memory)`: Initiates the flow by calling the internal `runNode` on the `start` node with the initial memory. Resets `visitCounts` before starting.
  - `runNode(node, memory)`: The core recursive method:
    1.  Checks `visitCounts` for the current `node` (using `__nodeOrder`). If `maxVisits` is reached, throws an error. Increments the count.
    2.  Clones the current `node` using `node.clone()`.
    3.  Runs the cloned node via `clone.run(memory.clone(), true)` to execute its lifecycle and get the `triggers` (actions and forked memory). Validates that `triggers` is an array.
    4.  For each `[action, nodeMemory]` trigger:
        - Gets the successor nodes (`nextNodes`) for that `action` from the _cloned_ node.
        - If `nextNodes` exist, recursively calls `runNodes` on them with the specific `nodeMemory`.
        - Constructs a result entry: `[action, recursiveResults]` or `[action, []]` if it's a terminal node for that path.
    5.  Uses `runTasks` (sequentially by default) to execute the processing for each trigger.
    6.  Aggregates results from all triggered paths into a nested object (`NestedActions`) representing the execution tree for the current `node`.
  - `runNodes(nodes, memory)`: Helper to run an array of nodes using `runTasks`.
  - `runTasks(tasks)`: Executes an array of async task functions sequentially using an `async/await` loop. Returns an array of results.

### 3.5. `ParallelFlow` Class

- **Purpose:** Orchestrates graph execution, running independent branches concurrently.
- **Inheritance:** Extends `Flow`.
- **Concurrency:**
  - Overrides `runTasks(tasks)` to use `Promise.all(tasks.map(task => task()))`. This executes the asynchronous functions (representing different branches initiated by triggers from a single node) in parallel.

### 3.6. Types and Constants

- `DEFAULT_ACTION`: `'default'` (constant) - Used when no specific action is triggered or required.
- `SharedStore`: `Record<string, any>` - Basic type for memory stores.
- `Action`: `string | typeof DEFAULT_ACTION` - Type for actions triggering transitions.
- `NestedActions<T>`: Recursive type defining the structure of the execution tree returned by `Flow.run`. `Record<T[number], NestedActions<T>[]>`
- `NodeError`: `Error & { retryCount: number }` - Custom error type carrying retry information.
- `Trigger<Action, L>`: Interface for objects stored in the `triggers` array (`{ action, forkingData }`).

### 3.7. Browser Compatibility

- A simple check (`typeof window !== 'undefined'`) detects browser environments.
- If in a browser and `globalThis.brainyflow` is not already defined, the main classes (`BaseNode`, `Node`, `Flow`, `ParallelFlow`) are attached to `globalThis.brainyflow` for easy access without module loaders.
