import pytest
from brainyflow import Memory

class TestMemory:
    """Tests for the Memory class."""
    class TestInitialization:
        """Tests for Memory initialization."""

        def test_initialize_with_global_store_only(self):
            """Should initialize with global store only."""
            global_store = {"g1": "global1"}
            memory = Memory.create(global_store)
            assert memory.g1 == "global1", "Should access global property"
            assert memory.local == memory._local == {}, "Local store should be empty"

        def test_initialize_with_global_and_local_stores(self):
            """Should initialize with global and local stores."""
            global_store = {"g1": "global1", "common": "global_common"}
            local_store = {"l1": "local1", "common": "local_common"}
            memory = Memory.create(global_store, local_store)
            assert memory.g1 == "global1", "Should access global property"
            assert memory.l1 == "local1", "Should access local property"
            assert memory.common == "local_common", "Local should shadow global"
            assert memory.local == memory._local == {"l1": "local1", "common": "local_common"}, "Local store should contain initial local data"

    class TestProxyBehaviorReading:
        """Tests for Memory proxy reading behavior."""

        @pytest.fixture
        def memory(self):
            """Create a memory instance with both global and local stores."""
            global_store = {"g1": "global1", "common": "global_common"}
            local_store = {"l1": "local1", "common": "local_common"}
            return Memory.create(global_store, local_store)

        def test_read_from_local_store_first(self, memory):
            """Should read from local store first."""
            assert memory.l1 == "local1"
            assert memory.common == "local_common"

        def test_fall_back_to_global_store_if_not_in_local(self, memory):
            """Should fall back to global store if property not in local."""
            assert memory.g1 == "global1"

        def test_return_appropriate_error_if_property_exists_in_neither_store(self, memory):
            """Should raise AttributeError for attribute access and KeyError for item access if property exists in neither store."""
            with pytest.raises(AttributeError, match="Key 'non_existent' not found in stores"):
                _ = memory.non_existent
            with pytest.raises(KeyError, match="Key 'non_existent_item' not found in stores"):
                _ = memory["non_existent_item"]


        def test_correctly_access_the_local_property(self, memory):
            """Should correctly access the local property."""
            assert memory.local == memory._local  == {"l1": "local1", "common": "local_common"}

    class TestProxyBehaviorWriting:
        """Tests for Memory proxy writing behavior."""

        @pytest.fixture
        def memory(self):
            """Create a memory instance with both global and local stores."""
            self.global_store = {"g1": "global1", "common": "global_common"}
            self.local_store = {"l1": "local1", "common": "local_common"}
            return Memory.create(self.global_store, self.local_store)

        def test_write_property_to_global_store_by_default(self, memory):
            """Should write property to global store by default."""
            memory.new_prop = "new_value"
            assert memory.new_prop == "new_value", "Should read the new property"
            assert self.global_store["new_prop"] == "new_value", "Global store should be updated"
            assert "new_prop" not in self.local_store, "Local store should not be updated"

        def test_overwrite_existing_global_property(self, memory):
            """Should overwrite existing global property."""
            memory.g1 = "updated_global1"
            assert memory.g1 == "updated_global1", "Should read the updated property"
            assert self.global_store["g1"] == "updated_global1", "Global store should be updated"

        def test_remove_property_from_local_store_when_writing_globally(self, memory):
            """Should remove property from local store if it exists when writing globally."""
            assert memory.common == "local_common", "Should initially read from local"
            memory.common = "updated_common_globally"
            assert memory.common == "updated_common_globally", "Should read the new global value"
            assert self.global_store["common"] == "updated_common_globally", "Global store should be updated"
            assert "common" not in self.local_store, "Property should be removed from local store"
            assert "common" not in memory.local, "Accessing via memory.local should also show removal"
            assert "common" not in memory._local, "Accessing via memory._local should also show removal"

        def test_throw_error_when_attempting_to_set_reserved_properties(self, memory):
            """Should throw error when attempting to set reserved properties."""
            with pytest.raises(Exception, match="Reserved property 'global' cannot be set"):
                setattr(memory, 'global', {})
            with pytest.raises(Exception, match="Reserved property 'local' cannot be set"):
                setattr(memory, 'local', {})
            with pytest.raises(Exception, match="Reserved property '_global' cannot be set"):
                memory._global = {}
            with pytest.raises(Exception, match="Reserved property '_local' cannot be set"):
                memory._local = {}

    class TestCloning:
        """Tests for Memory clone method."""

        @pytest.fixture
        def memory_setup(self):
            """Create a memory instance and data for cloning tests."""
            self.global_store = {
                "g1": "global1",
                "common": "global_common",
                "nested_g": {"val": 1}
            }
            self.local_store = {
                "l1": "local1",
                "common": "local_common",
                "nested_l": {"val": 2}
            }
            self.memory = Memory.create(self.global_store, self.local_store)
            return self.memory

        def test_create_new_memory_instance_with_shared_global_store(self, memory_setup):
            """Should create a new Memory instance with shared global store reference."""
            cloned_memory = memory_setup.clone()
            assert cloned_memory is not memory_setup, "Cloned memory should be a new instance"
            
            # Verify global store reference is shared by modifying through one and checking the other
            # Modify global via original, check clone
            memory_setup.g1 = "modified_global"
            assert cloned_memory.g1 == "modified_global", "Clone should see global changes"
            
            # Modify global via clone, check original
            cloned_memory.g2 = "added_via_clone"
            assert memory_setup.g2 == "added_via_clone", "Original should see global changes from clone"

        def test_create_deep_clone_of_local_store(self, memory_setup):
            """Should create a deep clone of the local store."""
            cloned_memory = memory_setup.clone()
            
            # Verify local store is not shared by reference
            assert (cloned_memory.local is not memory_setup.local) and (cloned_memory._local is not memory_setup._local), "Local store reference should NOT be shared"
            assert cloned_memory.local == cloned_memory._local == self.local_store, "Cloned local store should have same values initially"
            
            memory_setup.local["l1"] = "modified_local_original"
            assert cloned_memory.l1 == "local1", "Clone local property should be unaffected by original local changes"
            assert cloned_memory.local["l1"] == cloned_memory._local["l1"] == "local1", "Clone local store internal value should be unchanged"
            
            # Modify local via clone, check original
            cloned_memory.local["l2"] = "added_via_clone_local"
            # Accessing l2 on the original should raise AttributeError as it wasn't set globally or locally there
            with pytest.raises(AttributeError, match="Key 'l2' not found in stores"):
                _ = memory_setup.l2
            assert "l2" not in memory_setup.local, "Original local store internal value should be unchanged"
            
            assert cloned_memory.nested_l == {"val": 2}
            memory_setup.local["nested_l"]["val"] = 99
            assert cloned_memory.nested_l == {"val": 2}, "Nested local object in clone should be unaffected"

        def test_correctly_merge_forking_data_into_new_local_store(self, memory_setup):
            """Should correctly merge forkingData into the new local store."""
            forking_data = {"f1": "forked1", "common": "forked_common", "nested_f": {"val": 3}}
            cloned_memory = memory_setup.clone(forking_data)
            
            assert cloned_memory.f1 == "forked1", "Should access forked property"
            assert cloned_memory.common == "forked_common", "Forked data should shadow original local and global"
            assert cloned_memory.l1 == "local1", "Should still access original local property"
            assert cloned_memory.g1 == "global1", "Should still access global property"
            assert cloned_memory.nested_f == {"val": 3}
            
            assert cloned_memory.local == {
                "l1": "local1",
                "common": "forked_common",
                "nested_l": {"val": 2},
                "f1": "forked1",
                "nested_f": {"val": 3},
            }
            
            forking_data["nested_f"]["val"] = 99
            assert cloned_memory.nested_f == {"val": 3}, "Nested object in forked data should have been deep cloned"

        def test_handle_empty_forking_data(self, memory_setup):
            """Should handle empty forkingData."""
            cloned_memory = memory_setup.clone({})
            assert cloned_memory.local == cloned_memory._local == self.local_store

        def test_handle_cloning_without_forking_data(self, memory_setup):
            """Should handle cloning without forkingData."""
            cloned_memory = memory_setup.clone()
            assert cloned_memory.local == cloned_memory._local == self.local_store

class TestMemoryDeletion:
    """Tests for the new Memory deletion functionalities."""

    @pytest.fixture
    def memory_for_deletion(self):
        """Fixture to create a Memory instance with global and local values for deletion tests."""
        global_store = {"g_only": "global_val", "common_gl": "global_common", "g_shadowed": "global_shadow"}
        local_store = {"l_only": "local_val", "common_gl": "local_common", "g_shadowed": "local_shadow_val"}
        return Memory.create(global_store, local_store)

    # Tests for del memory.attr and del memory[key]
    def test_delattr_on_memory_deletes_global_only_key(self, memory_for_deletion):
        """del memory.attr should delete a key present only in the global store."""
        assert "g_only" in memory_for_deletion
        del memory_for_deletion.g_only
        
        assert "g_only" not in memory_for_deletion
        assert "g_only" not in memory_for_deletion._global
        assert "g_only" not in memory_for_deletion._local
        with pytest.raises(AttributeError):
            _ = memory_for_deletion.g_only

    def test_delitem_on_memory_deletes_global_only_key(self, memory_for_deletion):
        """del memory[key] should delete a key present only in the global store."""
        assert "g_only" in memory_for_deletion
        del memory_for_deletion["g_only"]

        assert "g_only" not in memory_for_deletion
        assert "g_only" not in memory_for_deletion._global
        assert "g_only" not in memory_for_deletion._local
        with pytest.raises(KeyError):
            _ = memory_for_deletion["g_only"]

    def test_delattr_on_memory_deletes_local_only_key(self, memory_for_deletion):
        """del memory.attr should delete a key present only in the local store."""
        # Note: current _delete_from_stores(key, self._global, self._local) means
        # it tries global first, then local. So "l_only" is only in local.
        assert "l_only" in memory_for_deletion
        del memory_for_deletion.l_only
        
        assert "l_only" not in memory_for_deletion
        assert "l_only" not in memory_for_deletion._global
        assert "l_only" not in memory_for_deletion._local
        with pytest.raises(AttributeError):
            _ = memory_for_deletion.l_only

    def test_delattr_on_memory_deletes_key_from_both_stores_if_present_in_both(self, memory_for_deletion):
        """del memory.attr should delete a key from both global and local if it exists in both."""
        assert memory_for_deletion.common_gl == "local_common"
        assert "common_gl" in memory_for_deletion._global
        assert "common_gl" in memory_for_deletion._local
        
        del memory_for_deletion.common_gl
        
        assert "common_gl" not in memory_for_deletion
        assert "common_gl" not in memory_for_deletion._global
        assert "common_gl" not in memory_for_deletion._local
        with pytest.raises(AttributeError):
            _ = memory_for_deletion.common_gl

    def test_delattr_on_memory_raises_keyerror_for_non_existent_key(self, memory_for_deletion):
        """del memory.attr should raise KeyError for a non-existent key."""
        # __delattr__ uses _delete_from_stores which raises KeyError
        with pytest.raises(KeyError, match="'non_existent_attr'"):
            del memory_for_deletion.non_existent_attr

    def test_delitem_on_memory_raises_keyerror_for_non_existent_key(self, memory_for_deletion):
        """del memory[key] should raise KeyError for a non-existent key."""
        with pytest.raises(KeyError, match="'non_existent_key'"):
            del memory_for_deletion["non_existent_key"]

    # Tests for del memory.local.attr and del memory.local[key]
    def test_delattr_on_local_proxy_deletes_from_local_store_only(self, memory_for_deletion):
        """del memory.local.attr should delete a key only from the local store."""
        assert memory_for_deletion.local.l_only == "local_val"
        
        del memory_for_deletion.local.l_only
        
        assert "l_only" not in memory_for_deletion.local
        assert "l_only" not in memory_for_deletion._local
        with pytest.raises(AttributeError):
            _ = memory_for_deletion.local.l_only
        
        assert "l_only" not in memory_for_deletion._global

    def test_delitem_on_local_proxy_deletes_from_local_store_only(self, memory_for_deletion):
        """del memory.local[key] should delete a key only from the local store."""
        assert memory_for_deletion.local["l_only"] == "local_val"
        
        del memory_for_deletion.local["l_only"]
        
        assert "l_only" not in memory_for_deletion.local
        assert "l_only" not in memory_for_deletion._local
        with pytest.raises(KeyError):
            _ = memory_for_deletion.local["l_only"]

    def test_delattr_on_local_proxy_does_not_affect_global_store(self, memory_for_deletion):
        """del memory.local.attr should not affect the global store, even if key has same name."""
        # 'g_shadowed' is in both: global_store{"g_shadowed": "global_shadow"}, local_store{"g_shadowed": "local_shadow_val"}
        assert memory_for_deletion.local.g_shadowed == "local_shadow_val"
        assert memory_for_deletion._global["g_shadowed"] == "global_shadow"
        
        del memory_for_deletion.local.g_shadowed
        
        assert "g_shadowed" not in memory_for_deletion.local # Deleted from local
        assert "g_shadowed" not in memory_for_deletion._local
        
        # Global store should be untouched
        assert memory_for_deletion._global["g_shadowed"] == "global_shadow"
        # Main memory object should now see the global value
        assert memory_for_deletion.g_shadowed == "global_shadow"

    def test_delattr_on_local_proxy_unshadows_global_key(self, memory_for_deletion):
        """del memory.local.attr on a shadowing key should make the global key visible via memory.attr."""
        # 'g_shadowed' is in both, local value shadows global
        assert memory_for_deletion.g_shadowed == "local_shadow_val" # Accesses local via memory object
        
        del memory_for_deletion.local.g_shadowed # Delete from local proxy
        
        # Now, memory.g_shadowed should access the global value
        assert "g_shadowed" not in memory_for_deletion.local
        assert memory_for_deletion.g_shadowed == "global_shadow" 
        assert memory_for_deletion._global["g_shadowed"] == "global_shadow"

    def test_delattr_on_local_proxy_raises_keyerror_for_non_existent_key(self, memory_for_deletion):
        """del memory.local.attr should raise KeyError for a non-existent key in local store."""
        # __delattr__ on LocalProxy uses _delete_from_stores which raises KeyError
        with pytest.raises(KeyError, match="'non_existent_local_attr'"):
            del memory_for_deletion.local.non_existent_local_attr

    def test_delitem_on_local_proxy_raises_keyerror_for_non_existent_key(self, memory_for_deletion):
        """del memory.local[key] should raise KeyError for a non-existent key in local store."""
        with pytest.raises(KeyError, match="'non_existent_local_key'"):
            del memory_for_deletion.local["non_existent_local_key"]

    def test_contains_check_after_deletions_on_memory(self, memory_for_deletion):
        """Verify `in` operator behaves correctly after deletions on Memory instance."""
        memory_for_deletion._global["g_delete_in_test"] = 1
        memory_for_deletion._local["l_delete_in_test"] = 2
        
        assert "g_delete_in_test" in memory_for_deletion
        assert "l_delete_in_test" in memory_for_deletion
        
        del memory_for_deletion.g_delete_in_test
        assert "g_delete_in_test" not in memory_for_deletion
        
        del memory_for_deletion.l_delete_in_test
        assert "l_delete_in_test" not in memory_for_deletion

    def test_contains_check_after_deletions_on_local_proxy(self, memory_for_deletion):
        """Verify `in` operator behaves correctly for LocalProxy after deletions."""
        memory_for_deletion.local["proxy_del_test"] = 3
        assert "proxy_del_test" in memory_for_deletion.local
        
        del memory_for_deletion.local.proxy_del_test
        assert "proxy_del_test" not in memory_for_deletion.local
