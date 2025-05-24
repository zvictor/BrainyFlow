import assert from 'node:assert/strict'
import { beforeEach, describe, it } from 'node:test' // Import beforeEach
import { createMemory, Memory } from '../brainyflow'

describe('Memory Class', () => {
  describe('Initialization', () => {
    it('should initialize with global store only', () => {
      const global = { g1: 'global1' }
      const memory = createMemory(global)
      assert.equal(memory.g1, 'global1', 'Should access global property')
      assert.deepStrictEqual(memory.local, {}, 'Local store should be empty')
    })

    it('should initialize with global and local stores', () => {
      const global = { g1: 'global1', common: 'global_common' }
      const local = { l1: 'local1', common: 'local_common' }
      const memory = createMemory(global, local)

      assert.equal(memory.g1, 'global1', 'Should access global property')
      assert.equal(memory.l1, 'local1', 'Should access local property')
      assert.equal(memory.common, 'local_common', 'Local should shadow global')
      assert.deepStrictEqual(memory.local, { l1: 'local1', common: 'local_common' }, 'Local store should contain initial local data')
    })
  })

  describe('Proxy Behavior (Reading)', () => {
    const global = { g1: 'global1', common: 'global_common' }
    const local = { l1: 'local1', common: 'local_common' }
    const memory = createMemory(global, local)

    it('should read from local store first', () => {
      assert.equal(memory.l1, 'local1')
      assert.equal(memory.common, 'local_common')
    })

    it('should fall back to global store if not in local', () => {
      assert.equal(memory.g1, 'global1')
    })

    it('should return undefined if property exists in neither store', () => {
      assert.strictEqual(memory.nonExistent, undefined)
    })

    it('should correctly access the local property', () => {
      assert.deepStrictEqual(memory.local, {
        l1: 'local1',
        common: 'local_common',
      })
    })
  })

  describe('Proxy Behavior (Writing)', () => {
    let global: Record<string, any>
    let local: Record<string, any>
    let memory: Memory<Record<string, any>, Record<string, any>>

    beforeEach(() => {
      global = { g1: 'global1', common: 'global_common' }
      local = { l1: 'local1', common: 'local_common' }
      memory = createMemory(global, local)
    })

    it('should write property to global store by default', () => {
      memory.newProp = 'newValue'
      assert.equal(memory.newProp, 'newValue', 'Should read the new property')
      assert.equal(global.newProp, 'newValue', 'Global store should be updated')
      assert.strictEqual(local.newProp, undefined, 'Local store should not be updated')
    })

    it('should overwrite existing global property', () => {
      memory.g1 = 'updated_global1'
      assert.equal(memory.g1, 'updated_global1', 'Should read the updated property')
      assert.equal(global.g1, 'updated_global1', 'Global store should be updated')
    })

    it('should remove property from local store if it exists when writing globally', () => {
      assert.equal(memory.common, 'local_common', 'Should initially read from local')
      memory.common = 'updated_common_globally'
      assert.equal(memory.common, 'updated_common_globally', 'Should read the new global value')
      assert.equal(global.common, 'updated_common_globally', 'Global store should be updated')
      assert.strictEqual(local.common, undefined, 'Property should be removed from local store')
      assert.strictEqual(memory.local.common, undefined, 'Accessing via memory.local should also show removal')
    })

    it('should throw error when attempting to set reserved properties', () => {
      assert.throws(() => (memory._isMemoryObject = {}), /Reserved property '_isMemoryObject' cannot be set/)
      assert.throws(() => (memory.local = {}), /Reserved property 'local' cannot be set/)
      assert.throws(() => (memory.clone = {}), /Reserved property 'clone' cannot be set/)
    })
  })

  describe('Cloning (`clone()`)', () => {
    let global: Record<string, any>
    let local: Record<string, any>
    let memory: Memory<Record<string, any>, Record<string, any>>
    let clonedMemory: Memory<Record<string, any>, Record<string, any>>

    beforeEach(() => {
      global = { g1: 'global1', common: 'global_common', nestedG: { val: 1 } }
      local = { l1: 'local1', common: 'local_common', nestedL: { val: 2 } }
      memory = createMemory(global, local)
    })

    it('should create a createMemory instance with shared global store reference', () => {
      clonedMemory = memory.clone()
      assert.notStrictEqual(clonedMemory, memory, 'Cloned memory should be a new instance')

      // Verify global store reference is shared by modifying through one and checking the other
      // Modify global via original, check clone
      memory.g1 = 'modified_global'
      assert.equal(clonedMemory.g1, 'modified_global', 'Clone should see global changes')

      // Modify global via clone, check original
      clonedMemory.g2 = 'added_via_clone'
      assert.equal(memory.g2, 'added_via_clone', 'Original should see global changes from clone')
    })

    it('should create a deep clone of the local store', () => {
      clonedMemory = memory.clone()
      // Verify local store is not shared by reference
      assert.notStrictEqual(clonedMemory.local, memory.local, 'Local store reference should NOT be shared')
      assert.deepStrictEqual(
        clonedMemory.local,
        local, // Check initial values are the same
        'Cloned local store should have same values initially',
      )

      // Modify local via original, check clone
      memory.local.l1 = 'modified_local_original' // Modify original's internal local store
      // Read from the clone. Since its local store is independent, it should still find 'l1' locally.
      assert.equal(
        clonedMemory.l1,
        'local1', // Should still be the original cloned local value
        'Clone local property should be unaffected by original local changes',
      )
      assert.equal(
        clonedMemory.local.l1, // Accessing the clone's internal local store directly
        'local1',
        'Clone local store internal value should be unchanged',
      )

      // Modify local via clone, check original
      clonedMemory.local.l2 = 'added_via_clone_local'
      assert.strictEqual(memory.l2, undefined, 'Original should not see local changes from clone (reads undefined)')
      assert.strictEqual(memory.local.l2, undefined, 'Original local store internal value should be unchanged')

      // Test nested objects
      assert.deepStrictEqual(clonedMemory.nestedL, { val: 2 })
      memory.local.nestedL.val = 99
      assert.deepStrictEqual(clonedMemory.nestedL, { val: 2 }, 'Nested local object in clone should be unaffected')
    })

    it('should correctly merge forkingData into the new local store', () => {
      const forkingData = {
        f1: 'forked1',
        common: 'forked_common',
        nestedF: { val: 3 },
      }
      clonedMemory = memory.clone(forkingData)

      assert.equal(clonedMemory.f1, 'forked1', 'Should access forked property')
      assert.equal(clonedMemory.common, 'forked_common', 'Forked data should shadow original local and global')
      assert.equal(clonedMemory.l1, 'local1', 'Should still access original local property')
      assert.equal(clonedMemory.g1, 'global1', 'Should still access global property')
      assert.deepStrictEqual(clonedMemory.nestedF, { val: 3 })

      // Check internal local store state
      assert.deepStrictEqual(clonedMemory.local, {
        l1: 'local1',
        common: 'forked_common', // Overwritten
        nestedL: { val: 2 },
        f1: 'forked1', // Added
        nestedF: { val: 3 }, // Added
      })

      // Ensure forkingData was deep cloned
      forkingData.nestedF.val = 99
      assert.deepStrictEqual(clonedMemory.nestedF, { val: 3 }, 'Nested object in forked data should have been deep cloned')
    })

    it('should handle empty forkingData', () => {
      clonedMemory = memory.clone({})
      assert.deepStrictEqual(clonedMemory.local, local)
    })

    it('should handle cloning without forkingData', () => {
      clonedMemory = memory.clone()
      assert.deepStrictEqual(clonedMemory.local, local)
    })
  })
})
