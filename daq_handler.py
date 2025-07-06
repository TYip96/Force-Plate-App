"""
Handles communication with the Measurement Computing DAQ device.
Uses a separate thread (QThread) for continuous background scanning to prevent
GUI freezing.

*** IMPORTANT NOTE ***
This implementation currently SIMULATES DAQ behavior.
Replace the sections marked with '# TODO: Replace with actual MCC library calls'
with the appropriate functions from your installed `mcculw` or `uldaq` library.
"""
import time
import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QMutex, QMutexLocker

# Import the actual library and specific components
from mcculw import ul
from mcculw.enums import ScanOptions, ULRange, AnalogInputMode, FunctionType
from mcculw.ul import ULError
from mcculw.device_info import DaqDeviceInfo

import config # Import config to use constants
from ctypes import c_double

def generate_cmj_waveform(time_points, sample_rate, base_voltage,
                          cycle_duration_s=5.0, jump_duration_s=1.5, flight_duration_s=0.3, # Added cycle/jump duration
                          bw_factor=0.9, unweight_factor=0.3, peak_factor=2.5, landing_peak_factor=3.0):
    """Generates a CMJ voltage waveform occurring once per cycle_duration_s."""
    n_points = len(time_points)
    waveform = np.ones(n_points) * base_voltage * bw_factor # Default to bodyweight
    dt = 1.0 / sample_rate

    # Ensure jump duration isn't longer than cycle duration
    jump_duration_s = min(jump_duration_s, cycle_duration_s - 0.1)
    jump_start_time_s = cycle_duration_s - jump_duration_s # Start jump towards end of cycle

    # Define jump phase timings *relative* to the start of the jump within the cycle
    active_jump_time = jump_duration_s - flight_duration_s # Time excluding flight
    if active_jump_time <= 0.1: active_jump_time = jump_duration_s * 0.7 # Prevent zero/negative

    t_unweight_end_rel = active_jump_time * 0.15
    t_brake_peak_rel = active_jump_time * 0.40
    t_propulsion_end_rel = active_jump_time * 0.75 # Takeoff point relative to jump start
    t_flight_end_rel = t_propulsion_end_rel + flight_duration_s
    t_land_peak_rel = t_flight_end_rel + active_jump_time * 0.05
    t_settle_end_rel = t_flight_end_rel + active_jump_time * 0.25

    # Voltages
    unweight_v = base_voltage * unweight_factor
    peak_brake_v = base_voltage * peak_factor
    landing_peak_v = base_voltage * landing_peak_factor
    body_weight_v = base_voltage * bw_factor

    for i, t in enumerate(time_points):
        t_in_cycle = t % cycle_duration_s # Time within the overall cycle

        # Check if we are within the jump phase of the cycle
        if t_in_cycle >= jump_start_time_s:
            t_rel = t_in_cycle - jump_start_time_s # Time relative to jump start

            if t_rel < t_unweight_end_rel:
                progress = t_rel / t_unweight_end_rel
                waveform[i] = body_weight_v + (unweight_v - body_weight_v) * np.sin(progress * np.pi / 2)
            elif t_rel < t_brake_peak_rel:
                progress = (t_rel - t_unweight_end_rel) / (t_brake_peak_rel - t_unweight_end_rel)
                waveform[i] = unweight_v + (peak_brake_v - unweight_v) * np.sin(progress * np.pi / 2)
            elif t_rel < t_propulsion_end_rel:
                progress = (t_rel - t_brake_peak_rel) / (t_propulsion_end_rel - t_brake_peak_rel)
                waveform[i] = peak_brake_v + (0 - peak_brake_v) * progress # Drop to zero V for takeoff
            elif t_rel < t_flight_end_rel:
                waveform[i] = 0.0 # Flight
            elif t_rel < t_land_peak_rel:
                progress = (t_rel - t_flight_end_rel) / (t_land_peak_rel - t_flight_end_rel)
                waveform[i] = 0 + (landing_peak_v - 0) * np.sin(progress * np.pi/2)
            elif t_rel < t_settle_end_rel:
                 progress = (t_rel - t_land_peak_rel) / (t_settle_end_rel - t_land_peak_rel)
                 waveform[i] = landing_peak_v + (body_weight_v - landing_peak_v) * np.sin(progress * np.pi/2)
            else:
                # Remainder of jump duration, settle back to BW
                waveform[i] = body_weight_v
        # else: Keep the default body_weight_v assigned at the start

    return waveform

class DAQWorker(QObject):
    """
    Worker object to perform DAQ scanning in a separate thread.
    Emits raw data chunks.
    """
    # Signal payload: numpy array shape [chunk_size, num_channels]
    data_chunk_signal = pyqtSignal(np.ndarray)
    status_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, board_num, num_channels, sample_rate, chunk_size, input_mode, scan_range, parent=None):
        super().__init__(parent)
        self.board_num = board_num
        self.num_channels = num_channels
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.input_mode = input_mode
        self.range = scan_range

        self._is_running = False
        self._mutex = QMutex()

    @pyqtSlot()
    def run(self):
        # Use blocking finite scans with driver-allocated buffer handles
        with QMutexLocker(self._mutex):
            self._is_running = True

        self.status_signal.emit(f"DAQ Worker thread started (Board {self.board_num}) with blocking scans.")
        total_points = self.chunk_size * self.num_channels
        ct_buf = (c_double * total_points)()

        try:
            while True:
                with QMutexLocker(self._mutex):
                    if not self._is_running:
                        break

                # Allocate DAQ buffer for this chunk
                memhandle = ul.scaled_win_buf_alloc(total_points)
                if not memhandle:
                    self.error_signal.emit("Failed to allocate DAQ buffer for blocking scan")
                    break

                try:
                    # Conduct the finite blocking scan into the buffer handle
                    ul.a_in_scan(
                        self.board_num,
                        0,
                        self.num_channels - 1,
                        total_points,
                        self.sample_rate,
                        self.range,
                        memhandle,
                        ScanOptions.SCALEDATA
                    )
                    # Copy data out into our ctypes array
                    ul.scaled_win_buf_to_array(memhandle, ct_buf, 0, total_points)
                except ULError as e:
                    self.error_signal.emit(f"DAQ blocking scan error: {e}")
                    break
                finally:
                    # Always free the driver buffer
                    ul.win_buf_free(memhandle)

                # Convert to numpy and reshape
                data_flat = np.ctypeslib.as_array(ct_buf)
                data_chunk = data_flat.reshape((self.chunk_size, self.num_channels))
                self.data_chunk_signal.emit(data_chunk)
        except Exception as e:
            self.error_signal.emit(f"Unexpected error in blocking scan: {e}")
        finally:
            self.status_signal.emit("DAQ Worker thread stopping.")
            self.finished.emit()

    @pyqtSlot()
    def stop(self):
        """Signals the worker thread to stop."""
        with QMutexLocker(self._mutex):
            if self._is_running:
                self._is_running = False
                self.status_signal.emit("Stop signal sent.")
            else:
                self.status_signal.emit("Stop signal sent, but worker wasn't running.")


class DAQHandler(QObject):
    """
    Manages the DAQ hardware interaction and the worker thread.
    Provides methods to start/stop scanning and get status.
    """
    # Signals proxied from the worker or generated directly
    data_chunk_signal = pyqtSignal(object) # Emits numpy array chunks
    daq_status_signal = pyqtSignal(str) # Overall status
    daq_error_signal = pyqtSignal(str)

    def __init__(self, sample_rate, num_channels, chunk_size, board_num=config.BOARD_NUM, parent=None):
        super().__init__(parent)
        self.board_num = board_num
        self.sample_rate = sample_rate
        self.num_channels = num_channels
        self.chunk_size = chunk_size
        self.input_mode = config.MCC_INPUT_MODE
        self.range = config.MCC_VOLTAGE_RANGE

        self._thread = None
        self._worker = None

        # Attempt to set input mode on initialization
        try:
            # Set the input mode for the board (assuming it applies to all channels for this device)
            ul.a_input_mode(self.board_num, self.input_mode)
            self.daq_status_signal.emit(f"Input mode set to {self.input_mode.name}")
        except ULError as e:
            # Log error but continue; maybe mode was already set or device doesn't support it here
            self.daq_error_signal.emit(f"Could not set input mode during init: {e}")
            # Consider if this should be a critical error preventing startup

        self._initialize_device() # Check for device on init

    def _initialize_device(self):
        """Check if the DAQ device can be found."""
        try:
            # Check basic board info
            board_name = ul.get_board_name(self.board_num)
            self.daq_status_signal.emit(f"DAQ Device '{board_name}' found (Board {self.board_num}).")
            # Query AI info to see supported scan options
            daq_info = DaqDeviceInfo(self.board_num)
            ai_info = daq_info.get_ai_info()
            self.daq_status_signal.emit(f"Supported scan options: {ai_info.supported_scan_options}")
            
            # Test if direct reading works
            test_value = ul.v_in(self.board_num, 0, self.range)
            self.daq_status_signal.emit(f"Direct reading test successful: {test_value:.4f}V")
        except ULError as e:
            self.daq_error_signal.emit(f"DAQ Initialization Error ({self.board_num}): {e}")
        except Exception as e:
             self.daq_error_signal.emit(f"Unexpected error during DAQ init: {e}")

    def start_scan(self):
        """Starts the DAQ scanning thread."""
        if self._thread is not None and self._thread.isRunning():
            self.daq_status_signal.emit("Scan already running.")
            return
        
        # Reset the DAQ state before starting
        try:
            # Try to stop any background operations that might still be running
            ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
            self.daq_status_signal.emit("Ensured clean state before starting new scan")
        except ULError:
            # Ignore errors as no operation might be running
            pass
            
        # Add small delay to allow hardware to reset
        time.sleep(0.5)
        
        self.daq_status_signal.emit("Preparing DAQ worker thread...")
        self._thread = QThread(self)
        self._worker = DAQWorker(
            board_num=self.board_num,
            num_channels=self.num_channels,
            sample_rate=self.sample_rate,
            chunk_size=self.chunk_size,
            input_mode=self.input_mode,
            scan_range=self.range
        )
        
        self._worker.moveToThread(self._thread)

        # Connect worker signals to DAQHandler signals/slots
        self._worker.data_chunk_signal.connect(self.data_chunk_signal) # Pass data through
        self._worker.status_signal.connect(self.daq_status_signal) # Pass status through
        self._worker.error_signal.connect(self.daq_error_signal)   # Pass errors through
        self._worker.finished.connect(self._on_worker_finished)    # Handle worker completion

        # Connect thread signals
        self._thread.started.connect(self._worker.run) # Start worker when thread starts
        self._thread.finished.connect(self._thread_cleanup) # Cleanup when thread finishes

        # Start the thread's event loop, which then triggers worker.run via started signal
        self._thread.start()
        self.daq_status_signal.emit("DAQ worker thread requested to start.")

    def stop_scan(self):
        """Signals the DAQ worker thread to stop."""
        if self._worker and self._thread and self._thread.isRunning():
            self.daq_status_signal.emit("Requesting DAQ worker stop...")
            # Signal the worker's run loop to exit. This is thread-safe due to mutex in worker.
            self._worker.stop()
            # Ensure the thread quits and waits for cleanup
            self._thread.quit()
            self._thread.wait(500)
        elif not self._thread or not self._thread.isRunning():
            self.daq_status_signal.emit("Stop requested but DAQ thread not active/running.")
        # No explicit ul.stop_background here; worker handles it.

    # This slot runs in the DAQHandler's thread (likely main thread)
    @pyqtSlot()
    def _on_worker_finished(self):
        """Called when the worker's run() method finishes execution."""
        self.daq_status_signal.emit("DAQ worker run() method finished signal received.")
        if self._thread:
            # Ask the thread's event loop to exit gracefully.
            # It will emit its own 'finished' signal when done.
            self._thread.quit()
            # Optional: Wait briefly for the thread to finish? Usually not needed with proper signal handling.
            # if not self._thread.wait(500): # Wait 500ms
            #    self.daq_error_signal.emit("DAQ thread did not finish quitting cleanly.")

    # This slot runs in the DAQHandler's thread
    @pyqtSlot()
    def _thread_cleanup(self):
        """Called when the QThread itself has finished executing its event loop."""
        self.daq_status_signal.emit("DAQ Thread finished signal received. Cleaning up references.")
        
        # Ensure worker object is deleted or cleaned up if necessary
        # If the worker was moved to the thread without a parent, it might need manual deletion
        # Or, if QThread manages its lifetime, this might be automatic.
        # For safety, explicitly deleteLater if no parent was set for worker
        # if self._worker:
        #    self._worker.deleteLater() 
            
        # If the thread object itself needs deletion (if not parented)
        # if self._thread:
        #     self._thread.deleteLater()

        self._worker = None # Clear references
        self._thread = None 
        self.daq_status_signal.emit("DAQ Thread references cleared.")

    def get_instant_voltage(self) -> np.ndarray | None:
        """Reads a single voltage sample from each channel for zeroing."""
        voltages = np.zeros(self.num_channels, dtype=np.float64)
        try:
            # --- Real MCCULW Logic --- 
            self.daq_status_signal.emit("Reading instant voltages...")
            for i in range(self.num_channels):
                # Use v_in to get scaled voltage directly
                voltages[i] = ul.v_in(self.board_num, i, self.range)
            self.daq_status_signal.emit(f"Read voltages: {np.round(voltages, 4)}")
            return voltages
            # --- End Real MCCULW Logic ---
        except ULError as e:
            self.daq_error_signal.emit(f"DAQ Error reading instant voltage: {e}")
            return None
        except Exception as e:
            self.daq_error_signal.emit(f"Unexpected error reading instant voltage: {e}")
            return None

    def __del__(self):
        """Ensure cleanup on object deletion."""
        print("DAQHandler __del__ called. Attempting cleanup...")
        # Request stop if scan is running, but don't block in __del__
        if self._thread and self._thread.isRunning():
            self.stop_scan() 
            # Consider if a brief wait is appropriate/safe here, but generally avoid blocking.
        
        # Optional: Release the DAQ device if required by UL
        # This might be necessary if create_daq_device was used without ignore_instacal
        # try:
        #     ul.release_daq_device(self.board_num)
        #     print(f"Released DAQ device {self.board_num}")
        # except ULError as e:
        #     print(f"Error releasing DAQ device {self.board_num} during cleanup: {e}")
        # except Exception as e:
        #     print(f"Unexpected error releasing DAQ {self.board_num}: {e}")

