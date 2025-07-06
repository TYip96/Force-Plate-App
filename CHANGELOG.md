# Changelog

All notable changes to the Force Plate App will be documented in this file.

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