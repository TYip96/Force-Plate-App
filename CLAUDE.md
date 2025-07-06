# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based force plate application for real-time data acquisition, processing, and jump analysis. The application uses PyQt6 for the GUI and integrates with Data Acquisition (DAQ) hardware via the mcculw library for force plate measurements.

## Application Architecture

The application follows a modular architecture with clear separation of concerns:

- **main_app.py**: Main application window and GUI controller that orchestrates all components
- **daq_handler.py**: Hardware interface for DAQ operations using threaded data acquisition
- **data_processor.py**: Real-time data processing, filtering, and jump analysis algorithms
- **plot_handler.py**: Live plotting and visualization using PyQtGraph
- **config.py**: Centralized configuration constants for hardware and analysis settings

### Key Data Flow
1. DAQ hardware → DAQHandler (threaded) → DataProcessor → PlotHandler
2. DataProcessor performs real-time analysis and emits results to GUI
3. All components communicate via PyQt6 signals/slots for thread safety

## Common Development Commands

### Running the Application
```bash
python main_app.py
```

### Installing Dependencies
```bash
pip install -r requirements.txt
```

### Dependencies
- PyQt6: GUI framework
- NumPy: Numerical computations
- SciPy: Scientific computing (filtering, analysis)
- pyqtgraph: Real-time plotting
- mcculw: DAQ hardware interface

## Configuration Management

All hardware and analysis parameters are centralized in `config.py`:
- **DAQ Settings**: Sample rate (1000 Hz), channels (4), voltage range (±10V)
- **Analysis Parameters**: Filter cutoff (50 Hz), flight detection thresholds
- **Plotting Settings**: Display window duration, Y-axis scaling

Key configuration constants:
- `SAMPLE_RATE`: 1000 Hz per channel
- `NUM_CHANNELS`: 4 analog input channels
- `N_PER_VOLT`: 327.0 N/V calibration factor
- `FILTER_CUTOFF`: 50 Hz low-pass filter
- `BODYWEIGHT_THRESHOLD_N`: 20N for flight detection

## Real-time Analysis Features

The application performs sophisticated real-time jump analysis:
- **Bodyweight Calibration**: 3-second standing period to establish baseline
- **Jump Detection**: Automated flight phase detection using force thresholds
- **Metrics Calculation**: Flight time, jump height (flight time and impulse methods), peak forces
- **Event Markers**: Visual markers for jump start, takeoff, and landing on plots

## Hardware Interface

The DAQ system uses blocking finite scans with the mcculw library:
- Supports differential input mode with ±10V range
- Thread-safe data acquisition using QThread
- Automatic buffer management and error handling
- Real-time voltage-to-force conversion

## Development Notes

- The application uses PyQt6 signals/slots for thread-safe communication
- All data processing happens in real-time during acquisition
- The plotting system throttles updates to ~30 FPS for smooth visualization
- Configuration validation occurs at startup to prevent runtime errors
- Comprehensive error handling and logging throughout all components

## Claude Code Workflow

When working on this project, follow these specific rules:

1. **Planning Phase**: First think through the problem, read the codebase for relevant files, and write a plan to `tasks/todo.md`.

2. **Task Management**: The plan should have a list of todo items that you can check off as you complete them.

3. **Communication**: Please every step of the way just give me a high level explanation of what changes you made.

4. **Simplicity First**: Make every task and code change you do as simple as possible. We want to avoid making any massive or complex changes. Every change should impact as little code as possible. Everything is about simplicity.

5. **Review Documentation**: Finally, add a review section to the `tasks/todo.md` file with a summary of the changes you made and any other relevant information.

6. **Changelog Maintenance**: After completing any changes to the codebase, update the CHANGELOG.md file with a detailed summary of all modifications, including date/time stamps, files affected, and the impact of changes. This ensures a clear history of all code modifications.