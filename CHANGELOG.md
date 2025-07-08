# CHANGELOG

## 2025-01-07 - Fixed Calibration Data Loading and Display Issues

### Fixed
- Fixed issue where calibration data was not loading on startup
- Added debug logging to help diagnose calibration file loading issues  
- Fixed display of calibration results when insufficient data (now properly shows "Need at least 2 different weights")
- Clear calibration plot when data is insufficient

### Added
- Automatic creation of default calibration.json file for first-time users
- Display loaded calibration data information (number of weights, measurements, last saved timestamp)
- Better error handling and user feedback during calibration data loading

### Changed
- **ui/calibration_widget.py**:
  - Enhanced `load_calibration_data()` method with debug logging and default file creation
  - Added `create_default_calibration_file()` method for first-time setup
  - `update_calibration_results()` now properly clears all displays and plot when data is insufficient
  - Progress label now shows information about loaded calibration data after successful load

### Impact
- First-time users will get a default calibration.json file created automatically
- Users can now see what calibration data was loaded (weights, measurements, timestamp)
- The "Need at least 2 different weights" message now displays properly with cleared plot
- Debug logging helps diagnose any future loading issues

## 2025-07-07 14:45 - Fixed Calibration Recording Issue

### Fixed
- Fixed "Not enough samples collected" error when recording calibration points
- The calibration recording now properly checks if DAQ is running before attempting to record
- Added clear user instructions in the calibration widget

### Changed
- **ui/calibration_widget.py**:
  - Added DAQ running status tracking (`is_daq_running` flag)
  - Added instruction label at top of calibration tab showing current status
  - Added validation in `start_recording()` to check if DAQ is running and plate is zeroed
  - Enhanced error messages with step-by-step instructions
  - Visual status indicator changes color based on DAQ state (red when stopped, green when running)
  
- **main_app.py**:
  - Added calls to `calibration_widget.set_daq_status()` when starting/stopping acquisition
  - Ensures calibration widget is aware of DAQ state changes

### Impact
- Users must now start acquisition on the Main tab before recording calibration points
- Clear workflow is now enforced: Zero plate → Start acquisition → Place weight → Record
- Prevents confusing errors and guides users through proper calibration procedure