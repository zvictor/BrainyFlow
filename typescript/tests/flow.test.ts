import assert from 'node:assert/strict'
import { beforeEach, describe, it, mock } from 'node:test'
import { createMemory, DEFAULT_ACTION, Flow, Memory, Node } from '../brainyflow'

// --- Helper Nodes ---
class TestNode extends Node<any, any> {
  id: string
  prepMock = mock.fn(async (memory: Memory<any, any>) => {})
  execMock = mock.fn(async (prepRes: any) => `exec_${this.id}`)
  postMock = mock.fn(async (memory: Memory<any, any>, prepRes: any, execRes: any) => {})

  constructor(id: string) {
    super()
    this.id = id
  }

  async prep(memory: Memory<any, any>) {
    memory[`prep_${this.id}`] = true
    await this.prepMock(memory)
    return `prep_${this.id}`
  }
  async exec(prepRes: any) {
    assert.equal(prepRes, `prep_${this.id}`)
    return await this.execMock(prepRes)
  }
  async post(memory: Memory<any, any>, prepRes: any, execRes: any) {
    assert.equal(prepRes, `prep_${this.id}`)
    assert.equal(execRes, `exec_${this.id}`)
    memory[`post_${this.id}`] = true
    await this.postMock(memory, prepRes, execRes)
    // Default trigger is implicit
  }
}

class BranchingNode extends TestNode {
  action: string = DEFAULT_ACTION
  forkData: Record<string, any> | null = null

  setTrigger(action: string, forkData: Record<string, any> | null = null) {
    this.action = action
    this.forkData = forkData
  }

  async post(memory: Memory<any, any>, prepRes: any, execRes: any) {
    await super.post(memory, prepRes, execRes) // Call base post
    this.trigger(this.action, this.forkData ?? {})
  }
}

describe('Flow Class', () => {
  let memory: Memory<any, any>
  let globalStore: Record<string, any>
  let nodeA: TestNode, nodeB: TestNode, nodeC: TestNode, nodeD: TestNode

  beforeEach(() => {
    globalStore = { initial: 'global' }
    memory = createMemory(globalStore)
    nodeA = new TestNode('A')
    nodeB = new TestNode('B')
    nodeC = new TestNode('C')
    nodeD = new TestNode('D')
    // Reset all mocks globally before each test
    mock.reset()
  })

  describe('Initialization', () => {
    it('should store the start node and default options', () => {
      const flow = new Flow(nodeA)
      assert.strictEqual(flow.start, nodeA)
      assert.deepStrictEqual((flow as any).options, { maxVisits: 15 })
    })

    it('should accept custom options', () => {
      const flow = new Flow(nodeA, { maxVisits: 10 })
      assert.strictEqual(flow.start, nodeA)
      assert.deepStrictEqual((flow as any).options, { maxVisits: 10 })
    })
  })

  describe('Sequential Execution', () => {
    it('should execute nodes sequentially following default actions', async () => {
      nodeA.next(nodeB)
      nodeB.next(nodeC) // A -> B -> C

      const flow = new Flow(nodeA)
      await flow.run(memory)

      // Verify execution order via mocks
      assert.equal(nodeA.prepMock.mock.calls.length, 1)
      assert.equal(nodeA.execMock.mock.calls.length, 1)
      assert.equal(nodeA.postMock.mock.calls.length, 1)
      assert.equal(nodeB.prepMock.mock.calls.length, 1)
      assert.equal(nodeB.execMock.mock.calls.length, 1)
      assert.equal(nodeB.postMock.mock.calls.length, 1)
      assert.equal(nodeC.prepMock.mock.calls.length, 1)
      assert.equal(nodeC.execMock.mock.calls.length, 1)
      assert.equal(nodeC.postMock.mock.calls.length, 1)

      // Verify memory changes
      assert.equal(memory.prep_A, true)
      assert.equal(memory.post_A, true)
      assert.equal(memory.prep_B, true)
      assert.equal(memory.post_B, true)
      assert.equal(memory.prep_C, true)
      assert.equal(memory.post_C, true)
    })

    it('should stop execution if a node has no successor for the triggered action', async () => {
      nodeA.next(nodeB) // A -> B (B has no successor)

      const flow = new Flow(nodeA)
      await flow.run(memory)

      assert.equal(nodeA.postMock.mock.calls.length, 1)
      assert.equal(nodeB.postMock.mock.calls.length, 1)
      assert.equal(nodeC.prepMock.mock.calls.length, 0) // C should not run
    })
  })

  describe('Conditional Branching', () => {
    it('should follow the correct path based on triggered action', async () => {
      const branchingNode = new BranchingNode('Branch')
      branchingNode.on('path_B', nodeB)
      branchingNode.on('path_C', nodeC)

      // Test path B
      branchingNode.setTrigger('path_B')
      let flowB = new Flow(branchingNode)
      let memoryB = createMemory({})
      await flowB.run(memoryB)
      assert.equal(memoryB.post_Branch, true)
      assert.equal(memoryB.post_B, true)
      assert.strictEqual(memoryB.post_C, undefined)

      // Test path C
      branchingNode.setTrigger('path_C') // Reset trigger
      let flowC = new Flow(branchingNode) // Recreate flow to reset visits
      let memoryC = createMemory({})
      await flowC.run(memoryC)
      assert.equal(memoryC.post_Branch, true)
      assert.strictEqual(memoryC.post_B, undefined)
      assert.equal(memoryC.post_C, true)
    })
  })

  describe('Memory Handling', () => {
    it('should propagate global memory changes', async () => {
      nodeA.postMock.mock.mockImplementation(async (mem) => {
        mem.global_A = 'set_by_A'
      })
      nodeB.prepMock.mock.mockImplementation(async (mem) => {
        assert.equal(mem.global_A, 'set_by_A')
      })
      nodeA.next(nodeB)
      const flow = new Flow(nodeA)
      await flow.run(memory)
      assert.equal(memory.global_A, 'set_by_A')
      assert.equal(nodeB.prepMock.mock.calls.length, 1) // Ensure B ran
    })

    it('should isolate local memory using forkingData', async () => {
      const branchingNode = new BranchingNode('Branch')
      branchingNode.on('path_B', nodeB)
      branchingNode.on('path_C', nodeC)

      // Setup mocks to check local memory
      nodeB.prepMock.mock.mockImplementation(async (mem) => {
        assert.equal(mem.local_data, 'for_B')
        assert.equal(mem.common_local, 'common')
        assert.strictEqual(mem.local.local_data, 'for_B')
      })
      nodeC.prepMock.mock.mockImplementation(async (mem) => {
        assert.equal(mem.local_data, 'for_C')
        assert.equal(mem.common_local, 'common')
        assert.strictEqual(mem.local.local_data, 'for_C')
      })

      // Trigger B with specific local data
      branchingNode.setTrigger('path_B', {
        local_data: 'for_B',
        common_local: 'common',
      })
      let flowB = new Flow(branchingNode)
      let memoryB = createMemory({ global_val: 1 })
      await flowB.run(memoryB)
      assert.equal(nodeB.prepMock.mock.calls.length, 1)
      assert.equal(nodeC.prepMock.mock.calls.length, 0)
      assert.strictEqual(memoryB.local_data, undefined) // Forked data shouldn't leak to global
      assert.strictEqual(memoryB.common_local, undefined)

      // Trigger C with different local data
      branchingNode.setTrigger('path_C', {
        local_data: 'for_C',
        common_local: 'common',
      })
      let flowC = new Flow(branchingNode) // Recreate flow
      let memoryC = createMemory({ global_val: 1 })
      await flowC.run(memoryC)
      assert.equal(nodeB.prepMock.mock.calls.length, 1) // Called once from previous run
      assert.equal(nodeC.prepMock.mock.calls.length, 1) // Called once now
      assert.strictEqual(memoryC.local_data, undefined)
      assert.strictEqual(memoryC.common_local, undefined)
    })
  })

  describe('Cycle Detection', () => {
    it('should execute a loop exactly maxVisits times before rejecting', async () => {
      let loopCount = 0
      nodeA.prepMock.mock.mockImplementation(async (mem) => {
        loopCount++
        mem.count = loopCount // Modify the memory passed to the node
      })
      nodeA.next(nodeA) // A -> A loop

      const maxVisitsAllowed = 3
      const flow = new Flow(nodeA, { maxVisits: maxVisitsAllowed })

      // Use a fresh memory object for this specific test's state
      const loopMemory = createMemory<{ count?: number }>({})
      // Expect rejection when the (maxVisits + 1)th execution is attempted
      await assert.rejects(
        async () => {
          try {
            await flow.run(loopMemory) // Run with the dedicated memory
          } catch (e) {
            // Assert state *inside* the catch block before re-throwing
            assert.equal(loopCount, maxVisitsAllowed, `Node should have executed exactly ${maxVisitsAllowed} times before error`)
            assert.equal(loopMemory.count, maxVisitsAllowed, `Memory count should be ${maxVisitsAllowed} before error`)
            throw e // Re-throw for assert.rejects to catch
          }
          // If it doesn't throw (which it should), fail the test explicitly
          assert.fail('Flow should have rejected due to cycle limit, but did not.')
        },
        new RegExp(`Maximum cycle count \\(${maxVisitsAllowed}\\) reached`),
        'Flow should reject when loop count exceeds maxVisits',
      )

      // Final check on loopCount after rejection is confirmed
      assert.equal(loopCount, maxVisitsAllowed, `Node should have executed exactly ${maxVisitsAllowed} times (final check)`)
    })

    it('should throw error immediately if loop exceeds maxVisits (e.g., maxVisits=2)', async () => {
      nodeA.next(nodeA) // A -> A loop
      const maxVisitsAllowed = 2
      const flow = new Flow(nodeA, { maxVisits: maxVisitsAllowed })
      const loopMemory = createMemory<{ count?: number }>({}) // Fresh memory

      await assert.rejects(
        flow.run(loopMemory),
        new RegExp(`Maximum cycle count \\(${maxVisitsAllowed}\\) reached`), // Check error message
        'Flow should reject when loop count exceeds maxVisits (maxVisits=2)',
      )
    })
  })

  describe('Flow as Node (Nesting)', () => {
    it('should execute a nested flow as a single node step', async () => {
      // Sub-flow: B -> C
      nodeB.next(nodeC)
      const subFlow = new Flow(nodeB)

      // Main flow: A -> subFlow -> D
      nodeA.next(subFlow)
      subFlow.next(nodeD) // Connect subFlow's implicit default exit to D

      const mainFlow = new Flow(nodeA)
      await mainFlow.run(memory)

      // Check execution order
      assert.equal(nodeA.postMock.mock.calls.length, 1)
      assert.equal(nodeB.postMock.mock.calls.length, 1) // B ran inside subFlow
      assert.equal(nodeC.postMock.mock.calls.length, 1) // C ran inside subFlow
      assert.equal(nodeD.postMock.mock.calls.length, 1) // D ran after subFlow

      // Check memory state
      assert.equal(memory.post_A, true)
      assert.equal(memory.post_B, true)
      assert.equal(memory.post_C, true)
      assert.equal(memory.post_D, true)
    })

    it('nested flow prep/post should wrap sub-flow execution', async () => {
      nodeB.next(nodeC)
      const subFlow = new Flow(nodeB)

      // Add prep/post to the subFlow instance itself
      subFlow.prep = mock.fn(async (mem) => {
        mem.subflow_prep = true
      })
      subFlow.post = mock.fn(async (mem) => {
        mem.subflow_post = true
      })

      nodeA.next(subFlow).next(nodeD)
      const mainFlow = new Flow(nodeA)
      await mainFlow.run(memory)

      assert.equal(memory.subflow_prep, true)
      assert.equal(memory.post_B, true) // Inner nodes ran
      assert.equal(memory.post_C, true)
      assert.equal(memory.subflow_post, true)
      assert.equal(memory.post_D, true) // D ran after subflow post
      assert.equal((subFlow.prep as any).mock.calls.length, 1)
      assert.equal((subFlow.post as any).mock.calls.length, 1)
    })
  })

  describe('Result Aggregation', () => {
    it('should return the correct NestedActions structure for a simple flow', async () => {
      nodeA.next(nodeB) // A -> B
      const flow = new Flow(nodeA)
      const result = await flow.run(memory)

      const expected = {
        [DEFAULT_ACTION]: [
          // Results from node A triggering default
          {
            [DEFAULT_ACTION]: [], // Results from node B triggering default (terminal)
          },
        ],
      }
      assert.deepStrictEqual(result, expected)
    })

    it('should return the correct structure for branching flow', async () => {
      const branchingNode = new BranchingNode('Branch')
      branchingNode.on('path_B', nodeB) // Branch -> B
      branchingNode.on('path_C', nodeC) // Branch -> C
      nodeB.next(nodeD) // B -> D

      // Trigger path B
      branchingNode.setTrigger('path_B')
      let flowB = new Flow(branchingNode)
      let resultB = await flowB.run(createMemory({}))

      const expectedB = {
        path_B: [
          // Results from Branch triggering path_B
          {
            [DEFAULT_ACTION]: [
              // Results from B triggering default
              {
                [DEFAULT_ACTION]: [], // Results from D triggering default
              },
            ],
          },
        ],
      }
      assert.deepStrictEqual(resultB, expectedB)

      // Trigger path C
      branchingNode.setTrigger('path_C')
      let flowC = new Flow(branchingNode) // Reset flow/visits
      let resultC = await flowC.run(createMemory({}))

      const expectedC = {
        path_C: [
          // Results from Branch triggering path_C
          {
            [DEFAULT_ACTION]: [], // Results from C triggering default
          },
        ],
      }
      assert.deepStrictEqual(resultC, expectedC)
    })

    it('should return correct structure for multi-trigger (fan-out)', async () => {
      class MultiTrigger extends TestNode {
        async post(memory: Memory<any, any>, prepRes: any, execRes: any) {
          await super.post(memory, prepRes, execRes)
          this.trigger('out1')
          this.trigger('out2')
        }
      }
      const multiNode = new MultiTrigger('Multi')
      multiNode.on('out1', nodeB) // Multi -> B
      multiNode.on('out2', nodeC) // Multi -> C

      const flow = new Flow(multiNode)
      const result = await flow.run(memory)

      // Ensure result is a valid object before proceeding
      assert.ok(result && typeof result === 'object', 'Flow result should be an object')

      const expected = {
        out1: [
          // Results from Multi triggering out1
          { [DEFAULT_ACTION]: [] }, // Result from B
        ],
        out2: [
          // Results from Multi triggering out2
          { [DEFAULT_ACTION]: [] }, // Result from C
        ],
      }
      // Order of keys might vary, check content
      assert.deepStrictEqual(Object.keys(result).sort(), ['out1', 'out2'])
      assert.deepStrictEqual(result.out1, expected.out1)
      assert.deepStrictEqual(result.out2, expected.out2)
    })
  })
})
