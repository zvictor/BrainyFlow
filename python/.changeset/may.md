---
"brainyflow": major
---

# Major refactor and enhancement release

## Breaking Changes

* **Memory creation**: If you were creating a new Memory object using the `Memory.create(data)` static class method, you will need to replace it by simply `Memory(data)`.
* **Flow.run()**: If you were traversing the nodes representation given by the `.run()` method, you will need to update your code to use the new `ExecutionTree` class.

### Core Library Changes
- **Memory class**: Considerable refactor with new deletion methods (`__delattr__`, `__delitem__`) and improved proxy behavior for local memory access
- **Flow class**: Default `maxVisits` increased from 5 to 15 for cycle detection
- **NodeError**: Changed from Exception class to Protocol interface
- **ExecutionTree**: Updated structure for better result aggregation and tracking
- **Type annotations**: Improved throughout with better Generic constraints and Protocol usage, fixing all type errors and inconsistencies

### API Changes
- Memory deletion operations now support both attribute and item-style deletion
- Error message format updated for cycle detection: now shows "Maximum cycle count (N) reached for ClassName#nodeId"
- Node execution warnings removed for nodes with successors

## New Features

### Memory Management
- Added comprehensive deletion support for Memory objects
- New local proxy with isolated deletion operations
- Better memory cloning with forking data support
- Enhanced store management with helper functions

### Developer Experience
- Improved migration documentation with detailed examples
- Added "Contributors Wanted" section to encourage community participation
- Better test isolation and predictable node ID management
- Enhanced error messages and debugging information

## Infrastructure Improvements

### CI/CD Pipeline
- Updated changesets action to v1.4.9 (workaround for github.com/changesets/action/issues/501)

### Testing
- Comprehensive test suite updates for new Memory functionality
- Added deletion operation tests
- Improved test reliability with BaseNode ID resets
- Better assertion patterns matching new error formats

### Documentation
- Updated migration guide from PocketFlow with clearer examples
- Enhanced core abstraction documentation
- Improved installation and setup instructions

## Bug Fixes
- Fixed memory proxy behavior edge cases
- Improved error handling in node execution
- Better cycle detection error reporting
- Enhanced type safety throughout the codebase

This release represents a significant improvement in memory management, developer experience, and overall library robustness while maintaining the core workflow orchestration capabilities.
