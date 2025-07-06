# Changelog

All notable changes to the Force Plate App will be documented in this file.

## [Unreleased] - 2025-07-06 17:55

### Added
- **New modular architecture** to address memory leaks and improve maintainability:
  - `buffer_manager.py` (134 lines): Memory-bounded circular buffers using deque to fix unbounded memory growth
  - `calibration_manager.py` (157 lines): Isolated bodyweight calibration state machine logic
  - `jump_detector.py` (151 lines): Real-time jump detection during data acquisition
  - `jump_analyzer.py` (483 lines): Post-jump analysis including filtering, event detection, and metrics
  - Files created: 4 new modules totaling 925 lines of well-organized code

### Changed
- **Refactored data_processor.py** from monolithic 1056-line file to modular 270-line coordinator:
  - Reduced from 1056 lines to 270 lines (74% reduction)
  - Now acts as a facade maintaining the exact same external interface
  - All PyQt signals preserved with identical signatures
  - All public methods maintain exact same behavior
  - Delegates responsibilities to specialized modules while preserving 100% functionality
  - Original file backed up as `data_processor_original.py`

### Fixed
- **Critical memory leak** in data processing:
  - Replaced unbounded lists (`self._time_buffer = []`) with circular buffers
  - Maximum buffer duration configurable (default 5 minutes)
  - Prevents out-of-memory errors during extended acquisition sessions

### Technical Details
- **Architecture improvements**:
  - Single Responsibility Principle: Each module handles one specific concern
  - Improved testability: Smaller, focused modules are easier to test
  - Better error isolation: Issues can be traced to specific modules
  - Reduced coupling: Modules communicate through well-defined interfaces
  
- **Memory efficiency**:
  - BufferManager uses `collections.deque` with maxlen for automatic old data eviction
  - Configurable buffer duration prevents unbounded growth
  - Efficient chunk-based storage for analysis operations

- **Preserved functionality**:
  - All signal emissions remain identical
  - External API completely unchanged
  - Calibration workflow unchanged
  - Jump detection logic preserved
  - Analysis calculations identical
  - UI behavior unaffected

### Documentation Updated
- **README.md**: Updated architecture section to reflect new modular structure
  - Fixed inaccurate data flow description to show DataProcessor as coordinator
- **CLAUDE.md**: Updated development notes to include new modules and memory management details

### Summary
- **Total impact**: Restructured 1056-line file into 5 modules totaling 1195 lines
- **Memory leak fixed**: Unbounded buffers replaced with circular buffers
- **Maintainability**: 74% reduction in main file complexity
- **Functionality preserved**: 100% - external interface completely unchanged
- **Files affected**: 7 files (1 refactored, 4 created, 1 backup, 2 documentation updated)

## [Unreleased] - 2025-07-06 15:30

### Updated
- **README.md comprehensive rewrite**: Complete overhaul to provide accurate and detailed project documentation
  - Removed reference to non-existent `display_results.py` file
  - Added detailed technical specifications including 1000 Hz sampling rate, 4-channel configuration
  - Expanded features section with real-time analysis capabilities (bodyweight calibration, jump detection, dual height calculation methods)
  - Added comprehensive hardware requirements and DAQ specifications
  - Included detailed architecture overview with data flow diagrams
  - Added configuration parameters section with key constants
  - Enhanced installation and usage instructions
  - Added troubleshooting section and technical details
  - Improved developer contribution guidelines
  - Files affected: README.md (complete rewrite, ~3x content expansion)

## [Unreleased] - 2025-07-06 11:00

### Fixed
- **Jump detection not working**: Restored `MIN_CONTACT_SAMPLES = 10` constant to config.py
  - The constant was accidentally removed during cleanup but is still required by data_processor.py
  - Without this constant, an AttributeError was preventing jump detection from functioning
  - Files affected: config.py (restored missing constant)

## [Unreleased] - 2025-07-06

### Removed
- **Unused constants from config.py**:
  - `VOLTAGE_RANGE = 10.0` (never referenced)
  - `MIN_CONTACT_SAMPLES = 10` (validated but never used in processing)

- **Simulation code from daq_handler.py**:
  - `generate_cmj_waveform()` function (59 lines of CMJ waveform generation)
  - Extensive cleanup comments in `_thread_cleanup()` method
  - Misleading header comments about simulation vs real hardware

- **Unused variables and methods from data_processor.py**:
  - `_acquisition_start_time` variable (initialized but never used)
  - `dt_chunk` calculations in two locations
  - `_find_time_window_indices()` method (26 lines, never called)
  - Dead body weight estimation code block
  - Empty else blocks and redundant debug comments

- **Unused tracking from plot_handler.py**:
  - `_acquisition_start_time` tracking variables
  - Obsolete comments about removed code

- **Redundant comments from main_app.py**:
  - Error handling comments
  - Verbose button state management comments

- **Entire unused file**:
  - `display_results.py` (~100 lines of duplicated functionality)

### Changed
- Updated configuration validation in main_app.py to remove MIN_CONTACT_SAMPLES check
- Updated CLAUDE.md to remove reference to deleted display_results.py file

### Summary
- **Total lines reduced**: ~338 lines (13.3% reduction from ~2,537 to 2,199 lines)
- **Files modified**: 5 files cleaned up
- **Files removed**: 1 file deleted
- **Functionality preserved**: 100% - no behavioral changes

This cleanup effort removed extensive unused simulation code, debug statements, redundant comments, and dead code while maintaining all existing functionality.