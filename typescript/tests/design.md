# BrainyFlow TypeScript Test Plan

This document outlines the testing strategy for the `brainyflow.ts` library using Node.js's native test runner (`node:test`).

## 1. Goals

- Ensure the core abstractions (`Memory`, `BaseNode`, `Node`, `Flow`, `ParallelFlow`) function according to the design specifications.
- Verify correct state management (global vs. local memory, cloning).
- Validate flow control mechanisms (sequential, parallel, conditional branching, triggers).
- Test error handling and resilience features (retries, fallbacks, cycle detection).
- Ensure composability (nesting flows).

## 2. Testing Framework

- **Runner:** Node.js native test runner (`node:test`).
- **Assertions:** Node.js native `assert` module.
- **Mocks/Spies:** Node.js native mocking capabilities or a minimal library if necessary (e.g., `sinon` or potentially leverage `vi` from `vitest` if already available, though sticking to native is preferred).

## 3. Test Categories and Cases

### 3.1. `Memory` Class

- **Proxy Behavior (Reading):**
  - Reads property from local store if present.
  - Falls back to global store if property not in local store.
  - Returns `undefined` if property exists in neither store.
  - Correctly accesses the `local` property (`__local` store).
- **Proxy Behavior (Writing):**
  - Writes property to global store by default (`memory.prop = value`).
  - Removes property from local store if it exists when writing to global.
  - Throws error when attempting to set reserved properties (`global`, `local`, `__global`, `__local`).
- **Cloning (`clone()`):**
  - Creates a new `Memory` instance.
  - Shares the same `__global` store reference.
  - Creates a deep clone (`structuredClone`) of the `__local` store.
  - Correctly merges `forkingData` (deep cloned) into the new local store, overwriting existing local keys if necessary.

### 3.2. `BaseNode` & `Node` (RetryNode)

- **Lifecycle Methods:**
  - `prep`, `exec`, `post` are called in the correct order during `run()`.
  - `prep` receives the correct `Memory` instance.
  - `exec` receives the result from `prep`.
  - `post` receives `Memory`, `prep` result, and `exec` result.
  - Default implementations of lifecycle methods do nothing and don't throw errors.
- **Graph Connections:**
  - `on(action, node)` adds the node to the correct action's successors list.
  - `next(node, action?)` adds the node correctly (defaults to `DEFAULT_ACTION`).
  - `getNextNodes(action)` returns the correct array of successor nodes for the given action.
  - `getNextNodes(action)` returns an empty array if no successors exist for the action.
  - `getNextNodes(action)` warns if a non-default action is requested but only other actions exist.
- **Triggering:**
  - `trigger(action, forkingData?)` correctly stores triggers internally.
  - Calling `trigger()` outside of `post` throws an error.
  - `listTriggers()` correctly processes stored triggers, creating cloned memory with `forkingData` applied locally.
  - `listTriggers()` returns `[[DEFAULT_ACTION, clonedMemory]]` if no triggers were called.
- **Execution (`run()`):**
  - `run(memory)` executes the full lifecycle (`prep` -> `execRunner` -> `post`).
  - `run(memory, false)` returns the result of `execRunner`.
  - `run(memory, true)` returns the result of `listTriggers` (array of `[action, memory]` tuples).
  - Warns if `run()` is called on a node with successors (indicating `Flow` should be used).
- **Cloning (`clone()`):**
  - Creates a deep copy of the node instance.
  - Maintains the correct prototype chain.
  - Recursively clones successors.
  - Handles cyclic graph structures correctly using the `seen` map.
- **`Node` (Retry Logic):**
  - `exec` is retried `maxRetries - 1` times upon throwing an error.
  - `wait` option introduces the correct delay between retries.
  - `execFallback` is called with the final error (including `retryCount`) if all retries fail.
  - `execFallback`'s return value becomes the `execRes` passed to `post`.
  - If `execFallback` throws, the error propagates.
  - `curRetry` property reflects the current attempt number within `exec` and `execFallback`.

### 3.3. `Flow` Class

- **Initialization:**
  - Stores the `start` node correctly.
  - Sets default `maxVisits` if not provided.
- **Execution (`run()`):**
  - Starts execution from the `start` node.
  - Executes nodes sequentially based on `DEFAULT_ACTION` triggers.
  - Executes nodes based on specific named action triggers.
  - Correctly clones node instances before running them.
  - Correctly clones memory for each triggered path, applying `forkingData`.
  - Propagates state changes in the global store correctly.
  - Isolates state changes in the local store to specific branches.
  - Aggregates results into the correct `NestedActions` structure.
  - Handles terminal nodes (nodes with no further triggers or successors) correctly.
- **Cycle Detection:**
  - Throws an error if a node is visited more than `maxVisits` times during a single `run()`.
  - `visitCounts` are reset for each `run()`.
- **Flow as Node (Nesting):**
  - A `Flow` instance can be used as a node within another `Flow`.
  - The parent flow correctly executes the nested flow's `prep`, `execRunner` (which runs the sub-flow), and `post`.
  - The nested flow's final state updates the shared memory correctly.
  - The nested flow's `post` method can trigger successors in the parent flow.
- **`runTasks` (Sequential):**
  - Executes tasks provided to it one after another, awaiting each completion.

### 3.4. `ParallelFlow` Class

- **`runTasks` (Parallel):**
  - Overrides `runTasks` to execute provided tasks concurrently using `Promise.all`.
  - Verify that branches triggered by a single node run in parallel (e.g., using mock async functions with different delays and checking execution order/timing).
  - Ensure results from parallel branches are correctly aggregated (order might not be guaranteed, depending on completion time).
  - Test state updates from parallel branches (potential race conditions are hard to test deterministically but ensure basic functionality works).

## 4. Test Structure

- Create separate test files for each major component (`memory.test.ts`, `node.test.ts`, `flow.test.ts`, `parallelFlow.test.ts`).
- Use descriptive `describe` and `it` blocks.
- Employ helper functions to create simple mock nodes and flows for testing specific behaviors.

## 5. Execution

- Run tests using the command specified in `.clinerules`: `node --import=tsx --experimental-test-snapshots --test-concurrency=1 --test typescript/tests/*.test.ts` (or specific files).
