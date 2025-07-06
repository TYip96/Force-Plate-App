# Force Plate Application

A sophisticated Python-based application for real-time force plate data acquisition, processing, and jump analysis. This application provides high-frequency data collection (1000 Hz), advanced signal processing, and comprehensive jump biomechanics analysis with live visualization.

## Features

### Real-time Data Acquisition
- High-speed data acquisition at 1000 Hz per channel
- 4-channel analog input with ±10V range
- Thread-safe DAQ operations using PyQt6 QThread
- Automatic voltage-to-force conversion (327.0 N/V calibration)

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
- Compatible DAQ hardware (tested with MCC USB devices)

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
- **Force Calibration**: 327.0 N/V conversion factor
- **Detection Threshold**: 20N for flight phase detection

## Project Architecture

The application follows a modular, thread-safe architecture:

- **`main_app.py`**: Main application window and GUI controller
- **`daq_handler.py`**: Hardware interface for DAQ operations (threaded)
- **`data_processor.py`**: Real-time data processing, filtering, and jump analysis
- **`plot_handler.py`**: Live plotting and visualization using PyQtGraph
- **`config.py`**: Centralized configuration constants

### Data Flow
1. DAQ Hardware → DAQHandler (QThread) → DataProcessor
2. DataProcessor → Real-time Analysis → PlotHandler
3. Results → GUI Display via PyQt6 signals/slots

## Technical Details

### Jump Analysis Algorithm
- **Phase Detection**: Monitors force threshold crossings to identify jump phases
- **Flight Time Method**: Calculates height from time of flight (h = 0.5 * g * t²)
- **Impulse Method**: Uses impulse-momentum theorem for independent height verification
- **Peak Force Analysis**: Identifies maximum force during propulsion phase

### Signal Processing Pipeline
1. Raw voltage acquisition from DAQ
2. Real-time voltage-to-force conversion
3. Low-pass filtering for noise reduction
4. Baseline correction and drift compensation
5. Jump detection and metrics calculation

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