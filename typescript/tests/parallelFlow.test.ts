import assert from 'node:assert/strict'
import { beforeEach, describe, it, mock } from 'node:test'
import { createMemory, DEFAULT_ACTION, Memory, Node, ParallelFlow } from '../brainyflow'

// Helper sleep function
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

// --- Helper Nodes ---
class DelayedNode extends Node<any, { delay?: number; id: string }> {
  id: string
  prepMock = mock.fn(async (memory: Memory<any, any>) => {}) // Add prepMock
  execMock = mock.fn(async (prepRes: any) => {})

  constructor(id: string) {
    super()
    this.id = id
  }

  async prep(memory: Memory<any, { delay?: number; id: string }>): Promise<{ delay: number }> {
    // Read delay from local memory (passed via forkingData)
    const delay = memory.delay ?? 0
    memory[`prep_start_${this.id}_${memory.id ?? 'main'}`] = Date.now()
    return { delay }
  }

  async exec(prepRes: { delay: number }): Promise<string> {
    await sleep(prepRes.delay)
    await this.execMock(prepRes)
    return `exec_${this.id}_slept_${prepRes.delay}`
  }

  async post(memory: Memory<any, any>, prepRes: any, execRes: any): Promise<void> {
    memory[`post_${this.id}_${memory.id ?? 'main'}`] = execRes
    memory[`prep_end_${this.id}_${memory.id ?? 'main'}`] = Date.now()
    // Trigger default successor, passing the intended delay for the *next* node if set
    if (this.nextNodeDelay !== undefined) {
      this.trigger('default', { delay: this.nextNodeDelay, id: memory.id }) // Pass original id too
    } else {
      this.trigger('default', { id: memory.id }) // Pass original id
    }
  }
  // Add a property to hold the delay for the next node in the test
  nextNodeDelay?: number
}

class MultiTriggerNode extends Node {
  triggersToFire: { action: string; forkData: Record<string, any> }[] = []

  addTrigger(action: string, forkData: Record<string, any>) {
    this.triggersToFire.push({ action, forkData })
  }

  async post(memory: Memory<any, any>): Promise<void> {
    memory.trigger_node_post_time = Date.now()
    for (const t of this.triggersToFire) {
      this.trigger(t.action, t.forkData)
    }
  }
}

describe('ParallelFlow Class', () => {
  let memory: Memory<any, any>
  let globalStore: Record<string, any>
  let triggerNode: MultiTriggerNode
  let nodeB: DelayedNode
  let nodeC: DelayedNode
  let nodeD: DelayedNode // Another node for sequential part

  beforeEach(() => {
    globalStore = { initial: 'global' }
    memory = createMemory(globalStore)
    triggerNode = new MultiTriggerNode()
    nodeB = new DelayedNode('B')
    nodeC = new DelayedNode('C')
    nodeD = new DelayedNode('D') // For testing sequential after parallel
    mock.reset() // Reset all mocks
  })

  it('should execute triggered branches concurrently using runTasks override', async () => {
    const delayB = 50
    const delayC = 60

    // Setup: TriggerNode fans out to B and C with different delays using distinct actions
    triggerNode.addTrigger('process_b', { id: 'B', delay: delayB })
    triggerNode.addTrigger('process_c', { id: 'C', delay: delayC })
    triggerNode.on('process_b', nodeB)
    triggerNode.on('process_c', nodeC)

    const parallelFlow = new ParallelFlow(triggerNode)

    const startTime = Date.now()
    const result = await parallelFlow.run(memory)
    const endTime = Date.now()
    const duration = endTime - startTime

    // --- Assertions ---

    // 1. Check total duration: Should be closer to max(delayB, delayC) than sum(delayB, delayC)
    const maxDelay = Math.max(delayB, delayC)
    const sumDelay = delayB + delayC
    console.log(`Execution Time: ${duration}ms (Max Delay: ${maxDelay}ms, Sum Delay: ${sumDelay}ms)`)
    assert.ok(duration < sumDelay - 10, `Duration (${duration}ms) should be significantly less than sum (${sumDelay}ms)`)
    assert.ok(
      duration >= maxDelay - 5 && duration < maxDelay + 50, // Allow buffer for overhead
      `Duration (${duration}ms) should be close to max delay (${maxDelay}ms)`,
    )

    // 2. Check if both nodes executed (via post-execution memory state)
    assert.equal(memory.post_B_B, `exec_B_slept_${delayB}`)
    assert.equal(memory.post_C_C, `exec_C_slept_${delayC}`)

    // 3. Check the aggregated result structure
    assert.ok(result && typeof result === 'object', 'Result should be an object')
    assert.ok('process_b' in result, "Result should contain 'process_b' key")
    assert.ok('process_c' in result, "Result should contain 'process_c' key")
    const processB_Results = result.process_b
    const processC_Results = result.process_c
    assert.ok(Array.isArray(processB_Results) && processB_Results.length === 1, "'process_b' should be an array with 1 result")
    assert.ok(Array.isArray(processC_Results) && processC_Results.length === 1, "'process_c' should be an array with 1 result")

    // Check that both branches completed (results are empty objects as DelayedNode has no successors)
    assert.deepStrictEqual(processB_Results[0], { [DEFAULT_ACTION]: [] })
    assert.deepStrictEqual(processC_Results[0], { [DEFAULT_ACTION]: [] })

    // 4. Check total mock calls
    assert.equal(nodeB.execMock.mock.calls.length + nodeC.execMock.mock.calls.length, 2, 'Total exec calls across parallel nodes should be 2')
  })

  it('should handle mix of parallel and sequential execution', async () => {
    // A (MultiTrigger) -> [B (delay 50), C (delay 60)] -> D (delay 30)
    const delayB = 50
    const delayC = 60
    const delayD = 30

    // Use distinct actions for parallel steps
    triggerNode.addTrigger('parallel_b', { id: 'B', delay: delayB })
    triggerNode.addTrigger('parallel_c', { id: 'C', delay: delayC })

    // Both parallel branches lead to D
    triggerNode.on('parallel_b', nodeB)
    triggerNode.on('parallel_c', nodeC)
    nodeB.next(nodeD, 'default') // B -> D
    nodeC.next(nodeD, 'default') // C -> D

    // Set the delay that nodes B and C should pass to node D
    nodeB.nextNodeDelay = delayD
    nodeC.nextNodeDelay = delayD

    // No need to mock nodeD.prep, its actual implementation should read the delay
    // from the forkingData provided by nodeB/nodeC's trigger call.

    const parallelFlow = new ParallelFlow(triggerNode)
    const startTime = Date.now()
    await parallelFlow.run(memory)
    const endTime = Date.now()
    const duration = endTime - startTime

    const expectedMinDuration = Math.max(delayB, delayC) + delayD
    console.log(`Mixed Execution Time: ${duration}ms (Expected Min: ~${expectedMinDuration}ms)`)

    // Check completion
    assert.equal(memory.post_B_B, `exec_B_slept_${delayB}`)
    assert.equal(memory.post_C_C, `exec_C_slept_${delayC}`)
    assert.equal(memory.post_D_B, `exec_D_slept_${delayD}`) // D executed after B
    assert.equal(memory.post_D_C, `exec_D_slept_${delayD}`) // D executed after C

    // Check timing: D should start only after its respective predecessor (B or C) finishes.
    // The whole flow should take roughly max(delayB, delayC) + delayD
    assert.ok(duration >= expectedMinDuration - 10, `Duration (${duration}ms) should be >= expected min (${expectedMinDuration}ms)`)
    assert.ok(
      duration < expectedMinDuration + 100, // Allow generous buffer for overhead
      `Duration (${duration}ms) should be reasonably close to expected min (${expectedMinDuration}ms)`,
    )

    // Check D was executed twice (once for each incoming path)
    assert.equal(nodeD.execMock.mock.calls.length, 2)
  })
})
