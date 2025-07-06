"""
Main application window for the Force Plate DAQ and Analysis Tool.
Integrates DAQ handling, data processing, plotting, and user interface.
"""
import sys
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStatusBar, QTextEdit, QFileDialog,
    QRadioButton, QButtonGroup, QFrame
)
from PyQt6.QtCore import pyqtSlot, QTimer, Qt
import logging

import config
from daq_handler import DAQHandler
from data_processor import DataProcessor
from plot_handler import PlotHandler

logging.basicConfig(
    filename='force_plate_app.log',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s'
)

class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Force Plate Analysis Tool")
        self.setGeometry(100, 100, 1000, 700) # x, y, width, height

        # --- Configuration Check ---
        if config.NUM_CHANNELS <= 0:
            print("Error: config.NUM_CHANNELS must be greater than 0.")
            # Optionally show an error dialog and exit
            # QMessageBox.critical(self, "Config Error", "NUM_CHANNELS must be > 0 in config.py")
            # sys.exit(1)
            # For now, we'll proceed but DAQ/Processing might fail

        # --- Configuration Validation ---
        errors = []
        # Allow FILTER_CUTOFF above Nyquist if desired (e.g., 580Hz) by skipping validation
        # if not (0 < config.FILTER_CUTOFF < config.SAMPLE_RATE / 2):
        #     errors.append("FILTER_CUTOFF must be between 0 and Nyquist (SAMPLE_RATE/2).")
        if config.MIN_FLIGHT_SAMPLES <= 0:
            errors.append("MIN_FLIGHT_SAMPLES must be positive.")
        if config.MIN_CONTACT_SAMPLES <= 0:
            errors.append("MIN_CONTACT_SAMPLES must be positive.")
        if errors:
            logging.error("Configuration validation failed: " + "; ".join(errors))
            self.show_error("Config validation error. See log.")
            sys.exit(1)

        # --- Central Widget and Layout ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget) # Main horizontal layout

        # --- Control Panel (Left Side) ---
        self.control_panel_layout = QVBoxLayout()
        self.main_layout.addLayout(self.control_panel_layout, 1) # Takes 1 part of stretch

        # Add calibration status display
        self.calibration_frame = QWidget()
        self.calibration_layout = QVBoxLayout(self.calibration_frame)
        
        # Calibration label with large font
        self.calibration_label = QLabel("Ready to begin")
        self.calibration_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #0066cc;")
        self.calibration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Countdown display with very large font
        self.countdown_label = QLabel("")
        self.countdown_label.setStyleSheet("font-size: 36px; font-weight: bold; color: #cc3300;")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setFixedHeight(50)
        
        # Bodyweight display
        self.bodyweight_label = QLabel("Bodyweight: Not calibrated")
        self.bodyweight_label.setStyleSheet("font-size: 14px;")
        self.bodyweight_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add to layout
        self.calibration_layout.addWidget(self.calibration_label)
        self.calibration_layout.addWidget(self.countdown_label)
        self.calibration_layout.addWidget(self.bodyweight_label)
        
        # Add a separator line
        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.Shape.HLine)
        self.separator.setFrameShadow(QFrame.Shadow.Sunken)
        
        self.control_panel_layout.addWidget(self.calibration_frame)
        self.control_panel_layout.addWidget(self.separator)
        self.control_panel_layout.addSpacing(10)

        # Buttons
        self.btn_zero = QPushButton("Zero Plate")
        self.btn_start = QPushButton("Start Acquisition")
        self.btn_stop = QPushButton("Stop Acquisition")
        self.btn_save = QPushButton("Save Data")

        self.control_panel_layout.addWidget(self.btn_zero)
        self.control_panel_layout.addWidget(self.btn_start)
        self.control_panel_layout.addWidget(self.btn_stop)
        self.control_panel_layout.addWidget(self.btn_save)
        # No btn_reset_view here - it goes below the plot

        # --- View Selection Radio Buttons ---
        self.view_label = QLabel("Plot View:")
        self.radio_individual = QRadioButton("Individual Channels")
        self.radio_summed = QRadioButton("Summed Channels")
        self.view_button_group = QButtonGroup(self) # Group ensures only one is selected
        self.view_button_group.addButton(self.radio_individual, 0) # Assign ID 0
        self.view_button_group.addButton(self.radio_summed, 1)     # Assign ID 1
        self.radio_summed.setChecked(True) # Default to summed view

        view_layout = QVBoxLayout() # Layout for radio buttons
        view_layout.addWidget(self.view_label)
        view_layout.addWidget(self.radio_individual)
        view_layout.addWidget(self.radio_summed)
        self.control_panel_layout.addLayout(view_layout)
        # --- End View Selection ---

        # Results Display
        self.results_label = QLabel("Analysis Results:")
        self.results_display = QTextEdit()
        self.results_display.setReadOnly(True)
        self.results_display.setFixedHeight(200) # Adjust height as needed

        self.control_panel_layout.addWidget(self.results_label)
        self.control_panel_layout.addWidget(self.results_display)
        self.control_panel_layout.addStretch(1) # Pushes controls up


        # --- Plotting Area (Right Side) ---
        self.plot_widget = pg.PlotWidget()
        self.plot_layout = QVBoxLayout()  # New vertical layout for plot and reset button
        self.plot_layout.addWidget(self.plot_widget, 1)  # Plot takes most of the space
        
        # Add Reset View button below the plot
        self.btn_reset_view = QPushButton("Reset View")
        self.btn_reset_view.setFixedHeight(30)  # Make it compact
        self.plot_layout.addWidget(self.btn_reset_view, 0)  # Button takes minimal space
        
        # Add the plot layout to main layout
        self.main_layout.addLayout(self.plot_layout, 3)  # Takes 3 parts of stretch

        # --- Status Bar ---
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Application Started. Ready.")

        # --- Initialize Backend Components ---
        # Initialize DAQ and Processor first
        self.daq_handler = DAQHandler(
            sample_rate=config.SAMPLE_RATE,
            num_channels=config.NUM_CHANNELS,
            chunk_size=config.DAQ_READ_CHUNK_SIZE
        )
        self.data_processor = DataProcessor(
            sample_rate=config.SAMPLE_RATE,
            num_channels=config.NUM_CHANNELS,
            n_per_volt=config.N_PER_VOLT
        )
        # Then initialize PlotHandler, passing the plot widget
        self.plot_handler = PlotHandler(self.plot_widget)

        # --- Setup Plot ---
        # Setup plot *after* PlotHandler is created
        self.plot_handler.setup_plot(num_channels=config.NUM_CHANNELS)

        # --- Connect Signals and Slots ---
        self._connect_signals()

        # --- Initial Button States ---
        self.btn_stop.setEnabled(False)
        self.btn_save.setEnabled(False)

        # Keep last displayed results so we can update braking later
        self._last_results = {}

    def _connect_signals(self):
        # Button Clicks
        self.btn_zero.clicked.connect(self.zero_plate)
        self.btn_start.clicked.connect(self.start_acquisition)
        self.btn_stop.clicked.connect(self.stop_acquisition)
        self.btn_save.clicked.connect(self.save_data)
        self.btn_reset_view.clicked.connect(self.reset_plot_view)  # Connect Reset View button

        # View Mode Radio Buttons
        self.view_button_group.idClicked.connect(self.change_plot_view) # Connect group signal

        # DAQ Handler Signals
        self.daq_handler.daq_status_signal.connect(self.update_status)
        self.daq_handler.daq_error_signal.connect(self.show_error)
        # Connect DAQ worker's raw data output to the processor's input slot
        self.daq_handler.data_chunk_signal.connect(self.data_processor.process_chunk)

        # Data Processor Signals
        self.data_processor.status_signal.connect(self.update_status)
        # Connect processor's processed data output to the plot handler's input slot
        # This connection should now work as both objects exist
        self.data_processor.processed_data_signal.connect(self.plot_handler.update_plot)
        # Connect processor's analysis results to the GUI update slot
        self.data_processor.analysis_complete_signal.connect(self.display_results)
        self.data_processor.peak_braking_signal.connect(self._update_peak_braking)
        
        # New calibration signals
        self.data_processor.calibration_status_signal.connect(self.update_calibration_status)
        self.data_processor.calibration_complete_signal.connect(self.update_bodyweight)
        
        # Connect jump event markers signal to plot handler
        self.data_processor.jump_event_markers_signal.connect(self.plot_handler.add_event_markers)

        # Update button states AFTER connections are made
        # NOTE: Reordered these from the original location
        #       in __init__ to ensure they reflect the state
        #       after connections (though the initial state is simple)
        #       The original code moved some button state changes into _connect_signals,
        #       but that seems incorrect. Button states should be set based on the
        #       application's *current* state, not just after signals are connected.
        self.btn_start.setEnabled(True) # Should be True initially?
        self.btn_zero.setEnabled(True)  # Should be True initially?
        self.btn_stop.setEnabled(False) # Set in __init__ already
        self.btn_save.setEnabled(False) # Set in __init__ already
        
    @pyqtSlot(str, int)
    def update_calibration_status(self, message, countdown):
        """Updates the calibration status display."""
        self.calibration_label.setText(message)
        if countdown > 0:
            self.countdown_label.setText(str(countdown))
        else:
            self.countdown_label.setText("")
            
    @pyqtSlot(float)
    def update_bodyweight(self, bodyweight_n):
        """Updates the bodyweight display with the calibrated value."""
        if bodyweight_n > 0:
            # Convert to kg for more intuitive display
            bodyweight_kg = bodyweight_n / config.GRAVITY
            self.bodyweight_label.setText(f"Bodyweight: {bodyweight_n:.1f}N ({bodyweight_kg:.1f}kg)")
        else:
            self.bodyweight_label.setText("Bodyweight: Not calibrated")

    @pyqtSlot()
    def zero_plate(self):
        """Acquires current voltage levels and sends them as zero offset."""
        self.update_status("Zeroing plate (averaging multiple samples)...")
        # Ensure any running acquisition is stopped so we can read instant voltages
        self.daq_handler.stop_scan()
        QApplication.processEvents()
        N_SAMPLES = 100
        voltages_accum = np.zeros(config.NUM_CHANNELS, dtype=float)
        for i in range(N_SAMPLES):
            v = self.daq_handler.get_instant_voltage()
            if v is None:
                self.show_error(f"Failed to read sample {i+1}/{N_SAMPLES} during zeroing.")
                return
            voltages_accum += v
            QApplication.processEvents()
        avg_offset = voltages_accum / N_SAMPLES
        self.data_processor.set_zero_offset(avg_offset)
        self.update_status(f"Zero offset acquired (averaged {N_SAMPLES} samples).")

    @pyqtSlot()
    def start_acquisition(self):
        """Starts the data acquisition process."""
        self.update_status("Starting acquisition...")
        self.results_display.clear() # Clear old results
        
        # Reset calibration display
        self.calibration_label.setText("Waiting for person to step on plate")
        self.countdown_label.setText("")
        self.bodyweight_label.setText("Bodyweight: Not calibrated")

        self.data_processor.reset_data()
        self.plot_handler.clear_plot()
        self.daq_handler.start_scan()

        # Update button states
        self.btn_start.setEnabled(False)
        self.btn_zero.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_save.setEnabled(False)

    @pyqtSlot()
    def stop_acquisition(self):
        """Stops the data acquisition process."""
        self.update_status("Stopping acquisition...")
        self.daq_handler.stop_scan() # This will trigger status updates via signals

        # Update button states (status update from DAQ handler might refine this)
        self.btn_start.setEnabled(True)
        self.btn_zero.setEnabled(True)
        self.btn_stop.setEnabled(False)

        # Enable analysis/save only if some data was likely collected
        # A short delay might be needed for the last chunks to process
        QTimer.singleShot(200, self._check_enable_analysis_save) # Check after 200ms

    def _check_enable_analysis_save(self):
        """Checks if data exists to enable analysis/save buttons."""
        # get_full_data now returns time, multi-channel force
        time, force_multi = self.data_processor.get_full_data()
        has_data = time is not None and len(time) > 0
        self.btn_save.setEnabled(has_data)
        if not has_data and not self.btn_start.isEnabled(): # If stopped but no data
             self.update_status("Acquisition stopped. No data collected.")

    @pyqtSlot(dict)
    def display_results(self, results_dict):
        """Displays the analysis results in the text area, appending new results."""
        # Store for later braking updates
        self._last_results = results_dict.copy()
        if not results_dict:
            # Append a message if the dictionary is empty (e.g., analysis failed early)
            self.results_display.append("--- Analysis Attempt Failed ---")
            return

        # Try to find a jump number in the keys to format the header
        jump_num_str = ""
        for key in results_dict.keys():
            if key.startswith("Jump #"):
                try:
                    jump_num_str = key.split(" ")[1] # Extract '#N'
                    break
                except IndexError:
                    pass # Malformed key, ignore

        if jump_num_str:
            results_text = f"--- JUMP {jump_num_str} RESULTS ---\n"
        else:
             results_text = "--- JUMP RESULTS ---\n" # Fallback header
        
        # Log all keys and values in results_dict for debugging
        print(f"DEBUG - Results dictionary keys: {list(results_dict.keys())}")
        print(f"DEBUG - Results values: {results_dict}")
        
        # Extract important metrics first to display prominently
        flight_time = None
        flight_height = None
        impulse_height = None
        bodyweight = None
        peak_propulsive = None
        peak_braking = None
        
        # Direct key access for cleaner code
        for key, value in results_dict.items():
            if key.endswith("Flight Time (s)"):
                flight_time = value
            elif key.endswith("Jump Height (Flight Time) (m)"):
                flight_height = value
            elif key.endswith("Jump Height (Impulse) (m)"):
                impulse_height = value
            elif key.endswith("Body Weight (N)"):
                bodyweight = value
            elif key.endswith("Peak Propulsive Force (N)"):
                peak_propulsive = value
            elif key.endswith("Peak Braking Force (N)"):
                peak_braking = value
        
        # Display metrics in a clear, consistent format
        if flight_time is not None:
            results_text += f"FLIGHT TIME: {flight_time} s\n"
            
        if bodyweight is not None:
            results_text += f"BODY WEIGHT: {bodyweight} N\n"
            
        if peak_propulsive is not None:
            results_text += f"PEAK PROPULSIVE FORCE: {peak_propulsive} N\n"
        if peak_braking is not None:
            results_text += f"PEAK BRAKING FORCE: {peak_braking} N\n"
        
        if flight_height is not None:
            # Convert jump height from meters to inches
            flight_height_in = flight_height * 39.3701
            results_text += f"JUMP HEIGHT (Flight Time): {flight_height_in:.2f} in\n"
            self.update_status(f"Jump Height: {flight_height_in:.2f} in (Flight Time)")
            
        if impulse_height is not None:
            # Convert impulse-based jump height from meters to inches
            impulse_height_in = impulse_height * 39.3701
            results_text += f"JUMP HEIGHT (Impulse): {impulse_height_in:.2f} in\n"
            self.update_status(f"Impulse-based Jump Height: {impulse_height_in:.2f} in")
            
        # Add a blank line after key metrics
        if flight_time or flight_height or impulse_height or peak_propulsive or peak_braking or bodyweight:
            results_text += "\n"
        else:
            results_text += "No jump data detected. Check threshold settings.\n\n"
            
        # Check for any error messages or notes
        analysis_note = None
        for key, value in results_dict.items():
            if "Analysis Note" in key:
                analysis_note = value
                break
                
        if analysis_note:
            results_text += f"Analysis Note: {analysis_note}\n\n"

        # Display the rest of the results that weren't already displayed
        for key, value in results_dict.items():
            # Skip the key metrics we already displayed
            if ("Flight Time" in key or 
                "Jump Height" in key or 
                "Body Weight" in key or
                "Peak Propulsive Force" in key or
                "Peak Braking Force" in key or
                "Analysis Note" in key):
                continue

            # Remove the jump number prefix for cleaner display
            display_key = key
            if jump_num_str and key.startswith(f"Jump {jump_num_str}"):
                 display_key = key.replace(f"Jump {jump_num_str} ", "", 1)

            # Format floats nicely
            if isinstance(value, float):
                results_text += f"{display_key}: {value:.3f}\n"
            else:
                results_text += f"{display_key}: {value}\n"

        self.results_display.clear() # Clear previous results
        self.results_display.setText(results_text) # Set new results
        # Save the updated results
        self._last_results = results_dict.copy()
        self.update_status("Analysis results updated.")

    def save_data(self):
        """Saves the collected Time and multi-channel Force data to a CSV file."""
        # Get multi-channel data
        time_data, force_data_multi = self.data_processor.get_full_data()

        if time_data is None or force_data_multi is None or len(time_data) == 0:
            self.show_error("No data available to save.")
            return

        num_channels = force_data_multi.shape[1]

        # Ask user for file location
        options = QFileDialog.Option.DontUseNativeDialog
        filePath, _ = QFileDialog.getSaveFileName(self, "Save Data File", "",
                                                  "CSV Files (*.csv);;Text Files (*.txt)", options=options)

        if filePath:
            try:
                self.update_status(f"Saving data to {filePath}...")
                # Combine time and force into a 2D array
                # Reshape time_data to (N, 1) to stack horizontally
                time_col = time_data.reshape(-1, 1)
                # Stack time column with force columns
                save_data = np.hstack((time_col, force_data_multi))

                # Create header
                channel_headers = ",".join([f'Fz_Ch{i} (N)' for i in range(num_channels)])
                header = f"Time (s),{channel_headers}\nSample Rate (Hz): {config.SAMPLE_RATE}, Filter Cutoff (Hz): {config.FILTER_CUTOFF}"

                np.savetxt(filePath, save_data, delimiter=',', header=header, comments='')
                self.update_status(f"Data saved successfully to {filePath}.")
            except Exception as e:
                self.show_error(f"Error saving file: {e}")
        else:
            self.update_status("Save cancelled.")

    @pyqtSlot(int)
    def change_plot_view(self, view_id):
        """Slot called when a radio button is clicked. view_id is 0 or 1."""
        if view_id == 0: # Individual
            self.plot_handler.set_view_mode('individual')
            self.update_status("Plot view: Individual Channels")
        else: # Summed (view_id == 1)
            self.plot_handler.set_view_mode('summed')
            self.update_status("Plot view: Summed Channels")

    @pyqtSlot()
    def reset_plot_view(self):
        """Resets the plot view to the initial X and Y ranges."""
        self.plot_handler.reset_view()
        self.update_status("Plot view reset to initial ranges.")

    @pyqtSlot(str)
    def update_status(self, message):
        """Updates the status bar message and logs it."""
        logging.info(message)
        self.statusBar().showMessage(message)
        print(f"Status: {message}") # Also print to console for debugging

    @pyqtSlot(str)
    def show_error(self, message):
        """Shows an error message in the status bar and logs it."""
        logging.error(message)
        self.statusBar().showMessage(f"Error: {message}", 5000) # Show for 5 seconds
        print(f"Error: {message}") # Also print to console

    def closeEvent(self, event):
        """Ensures the DAQ thread is stopped cleanly on exit."""
        self.update_status("Closing application...")
        self.daq_handler.stop_scan()
        # Gracefully quit and wait for the DAQ thread to finish
        if hasattr(self.daq_handler, '_thread') and self.daq_handler._thread:
            self.daq_handler._thread.quit()
            self.daq_handler._thread.wait(500)
        event.accept()

    @pyqtSlot(int, float)
    def _update_peak_braking(self, jump_number, braking_force):
        """Update only the peak braking force in the last results and re-render."""
        key = f'Jump #{jump_number} Peak Braking Force (N)'
        if key in self._last_results:
            self._last_results[key] = braking_force
            # Re-display using updated dict
            self.display_results(self._last_results)
        else:
            # If no prior results, ignore
            pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Set application style if desired (optional)
    app.setStyle('Fusion')
    mainWin = MainWindow()
    mainWin.show()
    sys.exit(app.exec()) 