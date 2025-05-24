---
machine-display: false
---

# Migrating from PocketFlow to BrainyFlow (Python)

{% hint style="info" %}
This guide specifically addresses migrating from the older synchronous Python library `PocketFlow` to the asynchronous Python version of `BrainyFlow`. While the core concepts of apply broadly, the specific approaches mentioned here may slightly differ from the TypeScript implementation.
{% endhint %}

BrainyFlow is an asynchronous successor to PocketFlow, designed for enhanced performance and concurrency. Migrating your Python codebase is straightforward:

## Key Changes

1. **All core methods are now async**

   - `prep()`, `exec()`, `post()`, `_exec()`, `_run()`, and `run()` methods now use `async/await` syntax
   - All method calls to these functions must now be awaited

2. **Simplified class hierarchy**

   - Removed separate async classes (`AsyncNode`, `AsyncFlow`, etc.)
   - All classes now use async methods by default

3. **Batch Processing Patterns**:
   - The way batch processing is handled has evolved. Instead of specific `BatchNode`/`BatchFlow` classes, BrainyFlow encourages using standard `Node`s with fan-out patterns (i.e. `trigger`/`forkingData` within a `Flow`).
   - Use `Flow` for sequential batch steps or `ParallelFlow` for concurrent batch steps. See the [MapReduce design pattern](../design_pattern/mapreduce.md) for examples.

## Why Async?

The move to async brings several benefits:

- **Improved performance**: Asynchronous code can handle I/O-bound operations more efficiently
- **Better concurrency**: Easier to implement parallel processing patterns
- **Simplified codebase**: No need for separate sync and async implementations
- **Modern Python**: Aligns with Python's direction for handling concurrent operations

## Migration Steps

### Step 1: Update Imports

Replace `pocketflow` imports with `brainyflow` and add `import asyncio`.

```python
# Before
from pocketflow import Node, Flow, BatchNode # ... etc

# After
import asyncio
from brainyflow import Node, Flow, SequentialBatchNode # ... etc
```

### Step 2: Add `async` / `await`:

- Add `async` before `def` for your `prep`, `exec`, `post`, and `exec_fallback` methods in Nodes and Flows.
- Remove any `_async` suffix from the method names.
- Add `await` before any calls to these methods, `run()` methods, `asyncio.sleep()`, or other async library functions.

#### Node Example (Before):

```python
class MyNode(Node):
    def prep(self, shared):
        # Preparation logic
        return some_data

    def exec(self, prep_res):
        # Execution logic
        return result

    def post(self, shared, prep_res, exec_res):
        # Post-processing logic
        return action

    def exec_fallback(self, prep_res, exc):
        # Handle exception
        return fallback_result
```

#### Node Example (After):

```python
class MyNode(Node):
    # Prefer using 'memory' parameter name for consistency
    async def prep(self, memory):
        # Preparation logic
        # If you call other async functions here, use await
        return some_data

    async def exec(self, prep_res):
        # Execution logic
        # If you call other async functions here, use await
        result = await some_async_task(prep_res)
        return result

    async def post(self, memory, prep_res, exec_res):
        # Post-processing logic
        # If you call other async functions here, use await
        memory.result = exec_res # Write to memory (global store)
        self.trigger(action) # Use trigger instead of returning action string

    async def exec_fallback(self, prep_res, exc):
        # Handle exception
        # If you call other async functions here, use await
        return fallback_result
```

_(Flow methods follow the same pattern)_

### Step 3: Use `.trigger()` for next actions

Check all `.post()` methods and replace any `return action` with a call to `self.trigger(action)`. _`return "default"` can be either replaced or removed._

### Step 4: Replace memory access methods:

Replace `shared.get(` by `getattr(shared, ` if `shared` is a `Memory` instance.

### Step 5: Update Batch Processing Implementation (`*BatchNode` / `*BatchFlow` Removal)

PocketFlow had dedicated classes like `BatchNode`, `ParallelBatchNode`, `BatchFlow`, and `ParallelBatchFlow`. BrainyFlow v0.3+ **removes these specialized classes**.

The batch functionality is now achieved using standard `Node`s and `Flow`s combined with a specific pattern:

1.  **Adopt the Fan-Out Trigger Pattern**:

  All `BatchNode` need to be split into two, a **Trigger Node** and a **Processor Node**.

  The **Trigger Node**:
      - Use the `prep` method to fetch the list of items to process, as usual.
      - Use the `post` method to iterate through these items. For **each item**, calls `self.trigger(action, forkingData={"item": current_item, "index": i, ...})`. The `forkingData` dictionary passes item-specific data into the **local memory** of the triggered successor. (the `action` name can be any of your choice as long as you connect the nodes in the flow; e.g. `process_one`, `default`)

  The **Processor Node**:
      - The `ProcessorNode`'s `prep` method reads the specific item data (e.g., `memory.item`, `memory.index`) from its **local memory**, which was populated by the `forkingData` in the trigger node.
      - The logic previously in the `exec_one` method of the `BatchNode` must be renamed to `exec`.
      - Its `post` method typically writes the result back to the **global memory**, often using the index to place it correctly in a shared list or dictionary.

  Similarly, `BatchFlow` need to be split into a `Node` and a regular `Flow`:
      - Replace the return value of the `prep` method with a  `post` method containing trigger calls.
      - Instead of `self.params["property"]`, use the usual `memory.property`.

2.  **Choose the Right Flow**:
    - Wrap the `TriggerNode` and `ProcessorNode` in a standard `brainyflow.Flow` if you need items processed **sequentially**.
    - Wrap them in a `brainyflow.ParallelFlow` if items can be processed **concurrently**.
    - Connect the nodes: `trigger_node >> processor_node` or `trigger_node - action >> processor_node`

3.  **Rename All Classes**:

    - Replace `AsyncParallelBatchFlow` with `brainyflow.ParallelFlow`.
    - Replace `AsyncParallelBatchNode`, `ParallelBatchNode`, `AsyncBatchNode`, `BatchNode` with the standard `brainyflow.Node`.
    - Replace `AsyncBatchFlow`, `BatchFlow` with `brainyflow.Flow`.
    - Remember to make `prep`, `exec`, `post` methods `async` as per Step 2.


#### Example: Translating Text into Multiple Languages

Let's adapt the `TranslateTextNode` example provided earlier. Before, it might have been a `BatchNode`. Now, we split it into a `TriggerTranslationsNode` and a `TranslateOneLanguageNode`.

{% tabs %}
{% tab title="Python" %}

```python
# Before (PocketFlow) - Conceptual BatchNode
class TranslateTextBatchNode(BatchNode):
    def prep(self, shared):
        text = shared.get("text", "(No text provided)")
        languages = shared.get("languages", ["Chinese", "Spanish", "Japanese"])
        # BatchNode prep would return items for exec
        return [(text, lang) for lang in languages]

    def exec(self, item):
        text, lang = item
        # Assume translate_text exists
        return await translate_text(text, lang)

    def post(self, shared, prep_res, exec_results):
        # BatchNode post might aggregate results
        shared["translations"] = exec_results
        return "default"
```

```python
# After (BrainyFlow) - Using Flow Patterns

from brainyflow import Node, Memory

# 1. Trigger Node (Fans out work)
class TriggerTranslationsNode(Node):
    async def prep(self, memory: Memory):
        text = memory.text if hasattr(memory, 'text') else "(No text provided)"
        languages = memory.languages if hasattr(memory, 'languages') else ["Chinese", "Spanish", "Japanese"]

        return [{"text": text, "language": lang} for lang in languages]

    async def post(self, memory: Memory, prep_res, exec_res):
        for index, input in enumerate(prep_res):
            self.trigger("default", input | {"index": index})

# 2. Processor Node (Handles one language)
class TranslateOneLanguageNode(Node):
    async def prep(self, memory: Memory):
        # Read data passed via forkingData from local memory
        return {
            "text": memory.text,
            "language": memory.language,
            "index": memory.index
        }

    async def exec(self, item):
        # Assume translate_text exists
        return await translate_text(item["text"], item["language"])

    async def post(self, memory: Memory, prep_res, exec_res):
        # Store result in the global list at the correct index
        memory.translations[exec_res["index"]] = exec_res
        this.trigger("default")

# 3. Flow Setup
trigger_node = TriggerTranslationsNode()
processor_node = TranslateOneLanguageNode()

trigger_node >> processor_node
```

{% endtab %}

{% tab title="TypeScript" %}

```typescript
// Before (PocketFlow) - Conceptual BatchNode
class TranslateTextBatchNode extends BatchNode<any, any, any, [string, string], string> {
  async prep(shared: Record<string, any>): Promise<[string, string][]> {
    const text = shared['text'] ?? '(No text provided)'
    const languages = shared['languages'] ?? ['Chinese', 'Spanish', 'Japanese']
    return languages.map((lang: string) => [text, lang])
  }

  async exec(item: [string, string]): Promise<string> {
    const [text, lang] = item
    // Assume translateText exists
    return await translateText(text, lang)
  }

  async post(shared: Record<string, any>, prepRes: any, execResults: string[]): Promise<string> {
    shared['translations'] = execResults
    return 'default'
  }
}
```

```typescript
// After (BrainyFlow) - Using Flow Patterns with ParallelFlow

import { Memory, Node } from 'brainyflow'

// Define Memory structure (optional but recommended)
interface TranslationGlobalStore {
  text?: string
  languages?: string[]
  translations?: ({ language: string; translation: string } | null)[]
}
interface TranslationLocalStore {
  text?: string
  language?: string
  index?: number
}
type TranslationActions = 'translate_one' | 'aggregate_results'

// 1. Trigger Node (Fans out work)
class TriggerTranslationsNode extends Node<
  TranslationGlobalStore,
  TranslationLocalStore,
  TranslationActions[]
> {
  async prep(
    memory: Memory<TranslationGlobalStore, TranslationLocalStore>,
  ): Promise<{ text: string; languages: string[] }> {
    const text = memory.text ?? '(No text provided)'
    const languages = memory.languages ?? getLanguages()
    return { text, languages }
  }

  // No exec needed for this trigger node

  async post(
    memory: Memory<TranslationGlobalStore, TranslationLocalStore>,
    prepRes: { text: string; languages: string[] },
    execRes: void, // No exec result
  ): Promise<void> {
    const { text, languages } = prepRes
    // Initialize results array in global memory
    memory.translations = new Array(languages.length).fill(null)

    // Trigger processing for each language
    languages.forEach((lang, index) => {
      this.trigger('default', {
        text: text,
        language: lang,
        index: index,
      })
    })
  }
}

// 2. Processor Node (Handles one language)
class TranslateOneLanguageNode extends Node<TranslationGlobalStore, TranslationLocalStore> {
  async prep(
    memory: Memory<TranslationGlobalStore, TranslationLocalStore>,
  ): Promise<{ text: string; lang: string; index: number }> {
    // Read data passed via forkingData from local memory
    const text = memory.text ?? ''
    const lang = memory.language ?? 'unknown'
    const index = memory.index ?? -1
    return { text, lang, index }
  }

  async exec(prepRes: {
    text: string
    lang: string
    index: number
  }): Promise<{ translated: string; index: number; lang: string }> {
    // Assume translateText exists
    return await translateText(prepRes.text, prepRes.lang)
  }

  async post(
    memory: Memory<TranslationGlobalStore, TranslationLocalStore>,
    prepRes: { text: string; lang: string; index: number }, // prepRes is passed through
    execRes: { translated: string; index: number; lang: string },
  ): Promise<void> {
    const { index, lang, translated } = execRes
    // Store result in the global list at the correct index
    // Ensure the global array exists and is long enough (important for parallel)
    if (!memory.translations) memory.translations = []
    while (memory.translations.length <= index) {
      memory.translations.push(null)
    }
    memory.translations[execRes.index] = execRes
    this.trigger('default')
  }
}

// 3. Flow Setup (Using ParallelFlow for concurrency)
const triggerNode = new TriggerTranslationsNode()
const processorNode = new TranslateOneLanguageNode()

triggerNode.next(processorNode)
```

_(See the [MapReduce design pattern](../design_pattern/mapreduce.md) for more detailed examples of fan-out/aggregate patterns)._

### Step 6: Run with `asyncio`:

BrainyFlow code must be run within an async event loop. The standard way is using `asyncio.run()`:

```python
import asyncio

async def main():
    # ... setup your BrainyFlow nodes/flows ...
    memory = {}
    result = await my_flow.run(memory) # Use await and pass memory object
    print(result)
    print(memory)

if __name__ == "__main__":
    asyncio.run(main())
```

## Conclusion

Migrating from PocketFlow to BrainyFlow primarily involves:

1.  Updating imports to `brainyflow` and adding `import asyncio`.
2.  Adding `async` to your Node/Flow method definitions (`prep`, `exec`, `post`, `exec_fallback`) and removing any `_async` suffix from the method names.
3. Replacing any `return action` in `post()` with a call to `self.trigger(action)`.
3.  Using `await` when calling `run()` methods and any other asynchronous operations within your methods.
4.  Replacing `BatchNode`/`BatchFlow` with the appropriate `Sequential*` or `Parallel*` BrainyFlow classes.
5.  Running your main execution logic within an `async def main()` function called by `asyncio.run()`.
6. Replacing all `return action` by `self.trigger(action)` in your Node methods.

This transition enables you to leverage the performance and concurrency benefits of asynchronous programming in your workflows.
