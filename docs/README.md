# Force Plate Application

A sophisticated Python-based application for real-time force plate data acquisition, processing, and jump analysis. This application provides high-frequency data collection (1000 Hz), advanced signal processing, and comprehensive jump biomechanics analysis with live visualization.

## Features

### Real-time Data Acquisition
- High-speed data acquisition at 1000 Hz per channel
- 4-channel analog input with ±10V range
- Thread-safe DAQ operations using PyQt6 QThread
- Automatic voltage-to-force conversion (330.31 N/V calibration)

### Advanced Jump Analysis
- **Bodyweight Calibration**: 3-second standing period for baseline establishment
- **Automated Jump Detection**: Real-time flight phase detection using force thresholds
- **Dual Height Calculation Methods**: Flight time and impulse-momentum approaches
- **Comprehensive Metrics**: Flight time, jump height, peak forces, and takeoff velocity
- **Event Markers**: Visual indicators for jump start, takeoff, and landing phases

### Real-time Visualization
- Live force data plotting with PyQtGraph
- Smooth 30 FPS display updates
- Configurable time windows and scaling
- Multi-channel force plate visualization

### Signal Processing
- Real-time 4th-order Butterworth low-pass filtering (50 Hz cutoff)
- Noise reduction and signal conditioning
- Baseline drift compensation

## Technical Specifications

### System Requirements
- Python 3.8 or higher
- Windows OS (required for mcculw DAQ library)
- Compatible DAQ hardware (tested with USB-1408FS-Plus)

### Dependencies
- **PyQt6**: GUI framework and threading
- **NumPy**: Numerical computations and array operations
- **SciPy**: Scientific computing and digital signal processing
- **pyqtgraph**: High-performance real-time plotting
- **mcculw**: Measurement Computing DAQ hardware interface

### Hardware Requirements
- Force plate with 4 load cells (differential output)
- Measurement Computing DAQ device with analog inputs
- Minimum 4 differential analog input channels
- ±10V input range capability

## Installation

1. Clone this repository:
```bash
git clone <your-repository-url>
cd force-plate-app
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure your DAQ hardware is properly installed and configured with the MCC DAQ software.

## Usage

Run the main application:
```bash
python main_app.py
```

### Basic Operation
1. **Start Application**: Launch the GUI interface
2. **Calibrate**: Stand on the force plate for 3 seconds to establish bodyweight baseline
3. **Jump Analysis**: Perform jumps - the system automatically detects and analyzes each jump
4. **View Results**: Real-time metrics display with live force plots

## Configuration

Key parameters can be modified in `config.py`:

- **Sample Rate**: 1000 Hz (default)
- **Channels**: 4 analog inputs
- **Filter Cutoff**: 50 Hz low-pass filter
- **Force Calibration**: 330.31 N/V conversion factor (calibrated 2025-07-07)
- **Detection Threshold**: 20N for flight phase detection

## Project Architecture

The application follows a modular architecture with clear separation of concerns:

### Core Components
- **`main_app.py`**: Main application window and GUI controller that orchestrates all components
- **`config.py`**: Centralized configuration constants for hardware and analysis settings

### Hardware Layer
- **`hardware/daq_handler.py`**: Hardware interface for DAQ operations using threaded data acquisition

### Processing Layer
- **`processing/data_processor.py`**: Main data processing coordinator (facade pattern)
- **`processing/buffer_manager.py`**: Memory-efficient circular buffers for data storage
- **`processing/calibration_manager.py`**: Bodyweight calibration state machine
- **`processing/jump_detector.py`**: Real-time jump detection during acquisition
- **`processing/jump_analyzer.py`**: Post-jump analysis and metrics calculation

### UI Layer
- **`ui/plot_handler.py`**: Live plotting and visualization using PyQtGraph
- **`ui/calibration_widget.py`**: Interactive N/V ratio calibration interface for force plate calibration

### Validation Tools
- **`validation/`**: Directory containing validation analysis scripts comparing against reference equipment

### Key Data Flow
1. DAQ hardware → DAQHandler (threaded) → DataProcessor
2. DataProcessor coordinates BufferManager, CalibrationManager, JumpDetector, and JumpAnalyzer
3. All components communicate via PyQt6 signals/slots for thread safety

## Technical Details

### Modular Architecture Benefits
- **Memory Efficiency**: Circular buffers prevent memory leaks during extended sessions
- **Single Responsibility**: Each module handles one specific concern
- **Better Testability**: Smaller, focused components are easier to test
- **Improved Maintainability**: 74% reduction in main processing file complexity

### Critical Timing Information
**The DAQ hardware samples at exactly 1000 Hz using hardware pacing with internal clock.** This is fundamental to all timing calculations:
- The USB-1408FS-Plus has an internal hardware clock that triggers sampling at precise 1ms intervals
- Timestamps are reconstructed based on sample count, which accurately reflects hardware sampling times
- No hardware timestamps are available through the mcculw library (not needed due to hardware pacing)
- Delivery timing variations (when Python retrieves data) do not affect actual sample timing
- The hardware clock ensures precise, consistent timing for jump analysis

### Jump Analysis Algorithm
- **Phase Detection**: Monitors force threshold crossings to identify jump phases
- **Flight Time Method**: Calculates height from time of flight (h = 0.5 * g * t²)
- **Impulse Method**: Uses impulse-momentum theorem for independent height verification
- **Peak Force Analysis**: Identifies maximum force during propulsion phase

### Signal Processing Pipeline
1. Raw voltage acquisition from DAQ
2. Real-time voltage-to-force conversion
3. Circular buffer storage with automatic memory management
4. Low-pass filtering for noise reduction
5. Baseline correction and drift compensation
6. Jump detection and metrics calculation

## Troubleshooting

- **DAQ Connection Issues**: Verify hardware installation and mcculw drivers
- **Calibration Problems**: Ensure stable standing during 3-second calibration period
- **Performance Issues**: Check system resources and reduce plot update frequency if needed

## Contributing

When contributing to this project:
1. Follow the existing code structure and threading patterns
2. Maintain real-time performance requirements
3. Test thoroughly with actual hardware
4. Update documentation for any configuration changes

## License

[Add your license information here] 