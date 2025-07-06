# Force Plate Application

A Python-based application for force plate data acquisition, processing, and analysis. This application provides real-time data visualization and jump height calculations using force plate technology.

## Features

- Real-time force plate data acquisition
- Live data visualization using PyQt6 and pyqtgraph
- Jump height calculation algorithms
- Data processing and analysis tools
- User-friendly GUI interface

## Requirements

- Python 3.8 or higher
- PyQt6 for GUI
- NumPy for numerical computations
- SciPy for scientific computing
- pyqtgraph for real-time plotting
- mcculw for DAQ (Data Acquisition) hardware interface

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

## Usage

Run the main application:
```bash
python main_app.py
```

## Project Structure

- `main_app.py` - Main application entry point and GUI
- `daq_handler.py` - Data acquisition hardware interface
- `data_processor.py` - Data processing and analysis algorithms
- `plot_handler.py` - Real-time plotting and visualization
- `display_results.py` - Results display and export functionality
- `config.py` - Configuration settings

## Hardware Requirements

- Force plate hardware compatible with mcculw library
- Appropriate DAQ (Data Acquisition) hardware

## License

[Add your license information here]

## Contributing

[Add contribution guidelines here] 