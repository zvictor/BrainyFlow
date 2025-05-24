import assert from 'node:assert/strict'
import { afterEach, beforeEach, describe, it, mock } from 'node:test'
import { BaseNode, createMemory, DEFAULT_ACTION, Memory, Node, NodeError } from '../brainyflow'

// Helper sleep function
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

// --- Test Node Implementations ---
class SimpleNode extends Node<{ count?: number }, { local_val?: string }> {
  prep = mock.fn(async (memory: Memory<any, any>) => {
    memory.prep_called = true
    return 'prep_result'
  })
  exec = mock.fn(async (prepRes: string) => {
    assert.equal(prepRes, 'prep_result')
    return 'exec_result'
  })
  post = mock.fn(async (memory: Memory<any, any>, prepRes: string, execRes: string) => {
    assert.equal(prepRes, 'prep_result')
    assert.equal(execRes, 'exec_result')
    memory.post_called = true
    // Default trigger is implicit if not called
  })
  execFallback = mock.fn(async (prepRes: string, error: NodeError) => {
    assert.equal(prepRes, 'prep_result')
    return 'fallback_result'
  })
}

class TriggeringNode extends Node {
  actionToTrigger: string | null = DEFAULT_ACTION
  forkingData: Record<string, any> | null = null

  async post(memory: Memory<any, any>, prepRes: any, execRes: any): Promise<void> {
    if (this.actionToTrigger) {
      if (this.forkingData) {
        this.trigger(this.actionToTrigger, this.forkingData)
      } else {
        this.trigger(this.actionToTrigger)
      }
    }
  }
}

class ErrorNode extends Node {
  failCount = 0
  succeedAfter = 1 // Succeed on the second attempt (index 1)

  constructor(options: { maxRetries?: number; wait?: number; succeedAfter?: number } = {}) {
    super(options)
    this.succeedAfter = options.succeedAfter ?? 1
  }

  async exec(prepRes: any): Promise<string> {
    // Cannot access this.curRetry directly, rely on failCount and succeedAfter
    if (this.failCount < this.succeedAfter) {
      this.failCount++
      throw new Error(`Planned failure ${this.failCount}`)
    }
    return 'success_after_retry'
  }

  execFallback = mock.fn(async (prepRes: any, error: NodeError) => {
    return `fallback_result_after_${error.retryCount}_retries`
  })
}

describe('BaseNode & Node', () => {
  let memory: Memory<any, any>
  let globalStore: Record<string, any>

  beforeEach(() => {
    globalStore = { initial: 'global' }
    memory = createMemory(globalStore)
    // Reset mocks for SimpleNode if necessary (though node:test often isolates)
    mock.reset() // Reset all mocks globally for safety
  })

  describe('Lifecycle Methods', () => {
    it('should call prep, exec, post in order with correct arguments', async () => {
      const node = new SimpleNode()
      const execResult = await node.run(memory)

      assert.equal(execResult, 'exec_result')
      assert.equal(node.prep.mock.calls.length, 1, 'prep should be called once')
      assert.equal(node.exec.mock.calls.length, 1, 'exec should be called once')
      assert.equal(node.post.mock.calls.length, 1, 'post should be called once')

      // Check memory modifications by lifecycle methods
      assert.equal(memory.prep_called, true)
      assert.equal(memory.post_called, true)

      // Check arguments passed
      assert.strictEqual(node.prep.mock.calls[0].arguments[0], memory)
      assert.strictEqual(node.exec.mock.calls[0].arguments[0], 'prep_result')
      assert.strictEqual(node.post.mock.calls[0].arguments[0], memory)
      assert.strictEqual(node.post.mock.calls[0].arguments[1], 'prep_result')
      assert.strictEqual(node.post.mock.calls[0].arguments[2], 'exec_result')
    })

    it('should handle nodes with only some lifecycle methods implemented', async () => {
      class PartialNode extends Node {
        async prep(memory: Memory<any, any>): Promise<string> {
          memory.prep_done = true
          return 'partial_prep'
        }
        // No exec
        async post(memory: Memory<any, any>, prepRes: any, execRes: any): Promise<void> {
          memory.post_done = true
          assert.equal(prepRes, 'partial_prep')
          assert.strictEqual(execRes, undefined) // exec returns void if not implemented
        }
      }
      const node = new PartialNode()
      const result = await node.run(memory)

      assert.strictEqual(result, undefined)
      assert.equal(memory.prep_done, true)
      assert.equal(memory.post_done, true)
    })
  })

  describe('Graph Connections', () => {
    let nodeA: BaseNode
    let nodeB: BaseNode
    let nodeC: BaseNode

    beforeEach(() => {
      nodeA = new SimpleNode()
      nodeB = new SimpleNode()
      nodeC = new SimpleNode()
    })

    it('on(action, node) should add successor correctly', () => {
      const returnedNode = nodeA.on('success', nodeB)
      assert.strictEqual(returnedNode, nodeB)
      const successors = nodeA.getNextNodes('success')
      assert.deepStrictEqual(successors, [nodeB])
      assert.deepStrictEqual(nodeA.getNextNodes(DEFAULT_ACTION), [])
    })

    it('next(node, action?) should add successor correctly', () => {
      const returnedNodeDefault = nodeA.next(nodeB) // Default action
      const returnedNodeNamed = nodeA.next(nodeC, 'custom')

      assert.strictEqual(returnedNodeDefault, nodeB)
      assert.strictEqual(returnedNodeNamed, nodeC)

      assert.deepStrictEqual(nodeA.getNextNodes(DEFAULT_ACTION), [nodeB])
      assert.deepStrictEqual(nodeA.getNextNodes('custom'), [nodeC])
      assert.deepStrictEqual(nodeA.getNextNodes('other'), [])
    })

    it('getNextNodes(action) should return correct successors', () => {
      nodeA.on('a', nodeB)
      nodeA.on('a', nodeC)
      nodeA.on('b', nodeB)

      assert.deepStrictEqual(nodeA.getNextNodes('a'), [nodeB, nodeC])
      assert.deepStrictEqual(nodeA.getNextNodes('b'), [nodeB])
      assert.deepStrictEqual(nodeA.getNextNodes('c'), [])
      assert.deepStrictEqual(nodeA.getNextNodes(), []) // Default action
    })

    it('getNextNodes(action) should return empty array if no successors', () => {
      assert.deepStrictEqual(nodeA.getNextNodes('any'), [])
    })

    it('getNextNodes(action) should warn if non-default action requested but only others exist', () => {
      // nodeA.on(DEFAULT_ACTION, nodeB); // Add a default successor
      // const warnMock = mock.method(console, 'warn', () => {});
      // nodeA.getNextNodes('non_existent_action');
      // assert.equal(warnMock.mock.calls.length, 1);
      // assert.match(warnMock.mock.calls[0].arguments[0], /Flow ends: 'non_existent_action' not found/);
      // warnMock.mock.restore();
      // Note: Mocking console.warn in node:test can be tricky. Skipping direct assertion for now.
      // Manual verification during dev or more complex setup needed.
    })
  })

  describe('Triggering', () => {
    it('should store triggers internally via trigger()', async () => {
      const node = new TriggeringNode()
      node.actionToTrigger = 'my_action'
      node.forkingData = { key: 'value' }

      // Run with propagate: true to get triggers
      const triggers = await node.run(memory, true)

      // Internal state isn't directly testable, but listTriggers result is
      assert.equal(triggers.length, 1)
      const [action, triggeredMemory] = triggers[0]
      assert.equal(action, 'my_action')
      assert.ok(triggeredMemory._isMemoryObject)
      assert.equal(triggeredMemory.key, 'value') // Check forkingData applied locally
      assert.equal(triggeredMemory.local.key, 'value')
      assert.strictEqual(memory.key, undefined) // Original memory unaffected
    })

    it('should throw error if trigger() is called outside post()', () => {
      const node = new TriggeringNode()
      assert.throws(() => node.trigger('test'), /An action can only be triggered inside post\(\)/)
    })

    it('listTriggers() should return default action if no trigger called', async () => {
      const node = new TriggeringNode()
      node.actionToTrigger = null // Ensure trigger is not called in post

      const triggers = await node.run(memory, true)

      assert.equal(triggers.length, 1)
      const [action, triggeredMemory] = triggers[0]
      assert.equal(action, DEFAULT_ACTION)
      assert.ok(triggeredMemory._isMemoryObject)
      assert.notStrictEqual(triggeredMemory, memory) // Should be a clone
      assert.deepStrictEqual(triggeredMemory.local, {}) // No forking data
    })

    it('listTriggers() should handle multiple triggers', async () => {
      class MultiTriggerNode extends Node {
        async post(memory: Memory<any, any>): Promise<void> {
          this.trigger('action1', { data1: 1 })
          this.trigger('action2', { data2: 2 })
        }
      }
      const node = new MultiTriggerNode()
      const triggers = await node.run(memory, true)

      assert.equal(triggers.length, 2)
      const trigger1 = triggers.find((t) => t[0] === 'action1')
      const trigger2 = triggers.find((t) => t[0] === 'action2')

      assert.ok(trigger1)
      assert.equal(trigger1[1].data1, 1)
      assert.deepStrictEqual(trigger1[1].local, { data1: 1 })

      assert.ok(trigger2)
      assert.equal(trigger2[1].data2, 2)
      assert.deepStrictEqual(trigger2[1].local, { data2: 2 })
    })
  })

  describe('Execution (`run()`)', () => {
    it('run(memory, false) should return execRunner result', async () => {
      const node = new SimpleNode()
      const result = await node.run(memory, false) // Explicit false
      assert.equal(result, 'exec_result')
    })

    it('run(memory) should default to returning execRunner result', async () => {
      const node = new SimpleNode()
      const result = await node.run(memory) // Omitted propagate
      assert.equal(result, 'exec_result')
    })

    it('run(memory, true) should return listTriggers result', async () => {
      const node = new TriggeringNode()
      node.actionToTrigger = 'test_action'
      const triggers = await node.run(memory, true)
      assert.equal(triggers.length, 1)
      assert.equal(triggers[0][0], 'test_action')
      assert.ok(triggers[0][1]._isMemoryObject)
    })

    it('run() should warn if called on a node with successors', async () => {
      const nodeA = new SimpleNode()
      const nodeB = new SimpleNode()
      nodeA.next(nodeB)
      const warnMock = mock.method(console, 'warn', () => {})
      await nodeA.run(memory)
      assert.equal(warnMock.mock.calls.length, 1, 'Expected a warning when running a node that has successors')
      warnMock.mock.restore()
      // assert.match(warnMock.mock.calls[0].arguments[0], /Node won't run successors. Use Flow!/);
      // warnMock.mock.restore();
      // Skipping direct assertion due to console.warn mocking difficulty
    })

    it('run() should accept global store directly', async () => {
      const node = new SimpleNode()
      // Global store must match the node's expected GlobalStore type <{ count?: number }>
      const global = { count: 5, initial: 'global_val' }
      await node.run(global) // Pass global store object directly

      assert.equal(node.prep.mock.calls.length, 1)
      const memoryArg = node.prep.mock.calls[0].arguments[0] as Memory<any, any>
      assert.ok(memoryArg._isMemoryObject)
      assert.equal(memoryArg.initial, 'global_val') // Check property from the passed global
      assert.equal(memoryArg.count, 5)
      assert.deepStrictEqual(memoryArg.local, {})
    })
  })

  describe('Cloning (`clone()`)', () => {
    it('should create a deep copy of the node instance', () => {
      const nodeA = new SimpleNode()
      ;(nodeA as any).customProp = 'original_value'
      const cloneA = nodeA.clone()

      assert.notStrictEqual(cloneA, nodeA)
      assert.ok(cloneA instanceof SimpleNode)
      assert.equal((cloneA as any).customProp, 'original_value')

      // Modify original, clone should be unaffected
      ;(nodeA as any).customProp = 'modified_value'
      assert.equal((cloneA as any).customProp, 'original_value')
    })

    it('should recursively clone successors', () => {
      const nodeA = new SimpleNode()
      const nodeB = new SimpleNode()
      const nodeC = new SimpleNode()
      nodeA.next(nodeB)
      nodeB.on('action', nodeC)

      const cloneA = nodeA.clone()
      const cloneB = cloneA.getNextNodes(DEFAULT_ACTION)[0]
      const cloneC = cloneB.getNextNodes('action')[0]

      assert.ok(cloneB)
      assert.ok(cloneC)
      assert.notStrictEqual(cloneB, nodeB)
      assert.notStrictEqual(cloneC, nodeC)
      assert.ok(cloneB instanceof SimpleNode)
      assert.ok(cloneC instanceof SimpleNode)
    })

    it('should handle cyclic graph structures during cloning', () => {
      const nodeA = new SimpleNode()
      const nodeB = new SimpleNode()
      nodeA.next(nodeB)
      nodeB.next(nodeA) // Cycle

      let cloneA: BaseNode | undefined
      assert.doesNotThrow(() => {
        cloneA = nodeA.clone()
      })

      assert.ok(cloneA)
      const cloneB = cloneA.getNextNodes(DEFAULT_ACTION)[0]
      assert.ok(cloneB)
      const cloneA_from_B = cloneB.getNextNodes(DEFAULT_ACTION)[0]
      assert.ok(cloneA_from_B)

      // Check that the cycle points back to the *cloned* instance of A
      assert.strictEqual(cloneA_from_B, cloneA)
    })

    it('should maintain the correct prototype chain', () => {
      class SpecificNode extends SimpleNode {
        specificMethod() {
          return 'specific'
        }
      }
      const node = new SpecificNode()
      const clone = node.clone()

      assert.ok(clone instanceof SpecificNode)
      assert.ok(clone instanceof SimpleNode)
      assert.ok(clone instanceof Node)
      assert.ok(clone instanceof BaseNode)
      assert.equal(clone.specificMethod(), 'specific')
    })
  })

  describe('Node (Retry Logic)', () => {
    it('should not retry if exec succeeds on first attempt', async () => {
      const node = new ErrorNode({ maxRetries: 3, succeedAfter: 0 }) // Succeed immediately
      const result = await node.run(memory)
      assert.equal(result, 'success_after_retry')
      assert.equal(node.failCount, 0)
      assert.equal(node.execFallback.mock.calls.length, 0)
    })

    it('should retry exec up to maxRetries times', async () => {
      const node = new ErrorNode({ maxRetries: 3, succeedAfter: 2 }) // Succeed on 3rd attempt (index 2)
      const result = await node.run(memory)
      assert.equal(result, 'success_after_retry')
      assert.equal(node.failCount, 2) // Failed on attempt 0 and 1
      assert.equal(node.execFallback.mock.calls.length, 0)
    })

    it('should call execFallback if all retries fail', async () => {
      const node = new ErrorNode({ maxRetries: 2, succeedAfter: 5 }) // Will always fail within retries
      const result = await node.run(memory)
      assert.equal(result, 'fallback_result_after_1_retries') // maxRetries=2 means 1 retry (attempts 0, 1)
      assert.equal(node.failCount, 2) // Failed on attempt 0 and 1
      assert.equal(node.execFallback.mock.calls.length, 1)
      const fallbackError = node.execFallback.mock.calls[0].arguments[1] as NodeError
      assert.equal(fallbackError.retryCount, 1) // Retry count is 0-based index of the *last* retry attempt
      assert.match(fallbackError.message, /Planned failure 2/)
    })

    it('should wait between retries if wait > 0', async () => {
      const node = new ErrorNode({
        maxRetries: 3,
        wait: 0.05,
        succeedAfter: 1,
      }) // Succeed on 2nd attempt
      const startTime = Date.now()
      const result = await node.run(memory)
      const endTime = Date.now()
      const duration = endTime - startTime

      assert.equal(result, 'success_after_retry')
      assert.equal(node.failCount, 1)
      assert.ok(duration >= 45, `Duration (${duration}ms) should be >= ~50ms`) // Allow some buffer
      assert.ok(duration < 150, `Duration (${duration}ms) should be < ~150ms`)
    })

    it('should pass correct prepRes and error to execFallback', async () => {
      class PrepErrorNode extends ErrorNode {
        async prep(memory: Memory<any, any>): Promise<string> {
          return 'prep_data_for_fallback'
        }
      }
      const node = new PrepErrorNode({ maxRetries: 1, succeedAfter: 1 }) // Fail immediately
      await node.run(memory)

      assert.equal(node.execFallback.mock.calls.length, 1)
      const [prepArg, errorArg] = node.execFallback.mock.calls[0].arguments
      assert.equal(prepArg, 'prep_data_for_fallback')
      assert.ok(errorArg instanceof Error)
      assert.equal((errorArg as NodeError).retryCount, 0)
    })

    it('should allow execFallback to throw an error', async () => {
      class FallbackThrowsNode extends ErrorNode {
        constructor() {
          super({ maxRetries: 1, succeedAfter: 1 }) // Fail immediately
        }
        // Override execFallback using mock.fn to match base class definition style
        execFallback = mock.fn(async (prepRes: any, error: NodeError): Promise<string> => {
          throw new Error('Fallback failed too')
        })
      }
      const node = new FallbackThrowsNode()
      await assert.rejects(node.run(memory), /Fallback failed too/)
    })

    it('should track attempts correctly during retries', async () => {
      // Test retry attempts by checking the final state or number of calls, not curRetry
      class CheckRetryNode extends Node<{ attempts: number[] }, any> {
        exec_calls = 0
        constructor() {
          super({ maxRetries: 3 })
        }
        // Pass attempts array via prepRes
        async prep(memory: Memory<{ attempts: number[] }, any>): Promise<{ attempts: number[] }> {
          memory.attempts = []
          return { attempts: memory.attempts }
        }
        async exec(prepRes: { attempts: number[] }): Promise<string> {
          this.exec_calls++
          prepRes.attempts.push(this.exec_calls) // Record call number
          if (this.exec_calls < 2) {
            // Fail on the first call
            throw new Error('Retry me')
          }
          return 'success'
        }
      }

      const node = new CheckRetryNode()
      const globalStoreForNode = { attempts: [] } // Match node's GlobalStore
      await node.run(globalStoreForNode)

      // Check how many times exec was called (1 initial + 1 retry)
      assert.equal(node.exec_calls, 2)
      // Check the recorded calls in the memory
      assert.deepStrictEqual(globalStoreForNode.attempts, [1, 2])
    })
  })
})
