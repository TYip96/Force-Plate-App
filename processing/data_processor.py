"""
Handles processing of raw DAQ data, including:
- Applying zero offset
- Scaling voltage to force (Newtons)
- Summing channels for total vertical force (Fz)
- Buffering data during acquisition
- Performing post-acquisition analysis (filtering, event detection, metrics).

This refactored version delegates specific responsibilities to specialized modules
while maintaining the exact same external interface.
"""
import numpy as np
import time
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer
import config

# Import the new modules
from .buffer_manager import BufferManager
from .calibration_manager import CalibrationManager
from .jump_detector import JumpDetector
from .jump_analyzer import JumpAnalyzer


class DataProcessor(QObject):
    """
    Processes raw data chunks, stores data, and performs analysis.
    Operates in the main application thread (receives signals from DAQ thread).
    
    This is a facade that maintains the original interface while delegating
    to specialized modules for specific functionality.
    """
    # All original signals preserved exactly
    processed_data_signal = pyqtSignal(np.ndarray, np.ndarray)
    analysis_complete_signal = pyqtSignal(dict)
    peak_braking_signal = pyqtSignal(int, float)
    status_signal = pyqtSignal(str)
    calibration_status_signal = pyqtSignal(str, int)
    calibration_complete_signal = pyqtSignal(float)
    jump_event_markers_signal = pyqtSignal(dict)

    def __init__(self, sample_rate, num_channels, n_per_volt, parent=None):
        super().__init__(parent)
        self.sample_rate = sample_rate
        self.num_channels = num_channels
        self.n_per_volt = n_per_volt

        # Initialize zero offset
        self.zero_offset_v = np.zeros(self.num_channels)

        # Initialize specialized modules
        self._buffer_manager = BufferManager(sample_rate, num_channels)
        self._calibration_manager = CalibrationManager()
        self._jump_detector = JumpDetector(sample_rate)
        self._jump_analyzer = JumpAnalyzer(sample_rate)
        
        # Connect signals from modules to forward them
        self._connect_module_signals()
        
        # Add real-time tracking
        self._last_real_time = None
        self._last_chunk_time = None

    def _connect_module_signals(self):
        """Connect signals from internal modules to forward them through this class."""
        # Forward calibration signals
        self._calibration_manager.calibration_status_signal.connect(
            lambda msg, count: self.calibration_status_signal.emit(msg, count)
        )
        self._calibration_manager.calibration_complete_signal.connect(
            lambda weight: self.calibration_complete_signal.emit(weight)
        )
        self._calibration_manager.status_signal.connect(
            lambda msg: self.status_signal.emit(msg)
        )
        
        # Forward jump detector signals
        self._jump_detector.status_signal.connect(
            lambda msg: self.status_signal.emit(msg)
        )
        self._jump_detector.jump_detected_signal.connect(
            self._on_jump_detected
        )
        
        # Forward jump analyzer signals
        self._jump_analyzer.analysis_complete_signal.connect(
            lambda results: self.analysis_complete_signal.emit(results)
        )
        self._jump_analyzer.jump_event_markers_signal.connect(
            lambda markers: self.jump_event_markers_signal.emit(markers)
        )
        self._jump_analyzer.status_signal.connect(
            lambda msg: self.status_signal.emit(msg)
        )

    @pyqtSlot(np.ndarray)
    def set_zero_offset(self, offset_voltages):
        """Stores the measured zero offset voltages."""
        if offset_voltages is not None and offset_voltages.shape == (self.num_channels,):
            self.zero_offset_v = offset_voltages
            self.status_signal.emit(f"Zero offset updated: {np.round(offset_voltages, 3)} V")
        else:
            self.status_signal.emit(f"Invalid offset voltages received. Shape: {offset_voltages.shape if offset_voltages is not None else 'None'}")

    @pyqtSlot()
    def reset_data(self):
        """Clears internal buffers and resets state before starting a new acquisition."""
        self._buffer_manager.reset()
        self._calibration_manager.reset()
        self._jump_detector.reset()
        
        # Reset real-time tracking
        self._last_real_time = None
        self._last_chunk_time = None
        
        self.status_signal.emit("Data buffers and jump state cleared.")

    @pyqtSlot(np.ndarray)
    def process_chunk(self, raw_data_chunk):
        """
        Processes raw data, appends to buffers, and performs real-time jump detection.
        Emits multi-channel processed data.
        """
        # Early guard against invalid input
        if raw_data_chunk is None or raw_data_chunk.ndim != 2 or raw_data_chunk.shape[1] != self.num_channels:
            self.status_signal.emit(f"Invalid raw data chunk received. Shape: {raw_data_chunk.shape if raw_data_chunk is not None else 'None'}")
            return
            
        # REAL-DAQ TIMING: measure actual callback interval
        now = time.time()
        self._last_real_time = now
        
        # Generate time stamps based on real wall-clock time
        num_samples = raw_data_chunk.shape[0]
        if self._last_chunk_time is None:
            start_time = now - num_samples / self.sample_rate
        else:
            start_time = self._last_chunk_time
            
        time_chunk = np.linspace(start_time, now, num_samples, endpoint=True)
        self._last_chunk_time = now
        num_samples_in_chunk = num_samples

        # 1. Apply Zero Offset
        offset_corrected_data = raw_data_chunk - self.zero_offset_v

        # 2. Scale to Force (Newtons per channel)
        force_data_channels = offset_corrected_data * self.n_per_volt

        # 3. Calculate Total Vertical Force (Fz) for detection
        fz_chunk_summed = np.sum(force_data_channels, axis=1)

        # 4. Emit MULTI-CHANNEL data for Plotting
        self.processed_data_signal.emit(time_chunk, force_data_channels)

        # 5. Append to buffers
        self._buffer_manager.append_chunk(time_chunk, force_data_channels)
        current_buffer_length = self._buffer_manager.get_buffer_size()
        
        # 6. Process calibration state machine
        self._calibration_manager.process_chunk(
            time_chunk, fz_chunk_summed, current_buffer_length
        )
        
        # 7. Perform jump detection if calibration is ready
        if self._calibration_manager.is_ready_for_jump():
            # Get buffer data for jump detection
            time_chunks, force_chunks = self._buffer_manager.get_chunks_for_analysis()
            if time_chunks and force_chunks:
                jump_detected, jump_info = self._jump_detector.process_chunk(
                    time_chunks, force_chunks, num_samples_in_chunk
                )
                
                if jump_detected:
                    # Mark calibration phase as completed
                    self._calibration_manager.set_completed()

    def _on_jump_detected(self, jump_number, takeoff_index, landing_index):
        """Handle jump detection by triggering analysis."""
        # Compute and emit basic metrics immediately
        self._compute_basic_metrics(jump_number, takeoff_index, landing_index)
        
        # Schedule braking peak computation after 300ms
        delay_ms = int(0.3 * 1000)
        self.status_signal.emit(f"Scheduling braking-peak calc in {delay_ms} ms")
        QTimer.singleShot(
            delay_ms,
            lambda jn=jump_number, li=landing_index: self._compute_braking_peak(jn, li)
        )

    def get_full_data(self):
        """Returns the complete collected data as NumPy arrays.
        Returns: (full_time [1D], full_force_multi_channel [2D: samples, channels])
        """
        return self._buffer_manager.get_full_data()

    def _compute_basic_metrics(self, jump_number, takeoff_index, landing_index):
        """Compute all jump metrics except braking, then emit full-results dict."""
        full_time, full_multi = self.get_full_data()
        if full_time is None or full_multi is None:
            return
            
        # Sum to get Fz
        fz_full = np.sum(full_multi, axis=1)
        
        # Define segment window: 1s before takeoff to landing
        if full_time is not None and len(full_time) > takeoff_index:
            takeoff_time = full_time[takeoff_index]
            window_start_time = takeoff_time - 1.0
            start_idx = max(0, np.abs(full_time - window_start_time).argmin())
        else:
            start_idx = max(0, takeoff_index - int(1.0 * self.sample_rate))
            
        end_idx = landing_index + 1
        time_seg = full_time[start_idx:end_idx]
        fz_seg = fz_full[start_idx:end_idx]
        
        # Get calibration data
        body_weight = self._calibration_manager.get_bodyweight()
        calibration_std = self._calibration_manager.get_calibration_std()
        calibration_complete_time = self._calibration_manager.get_calibration_complete_time()
        
        # Perform full analysis on this segment
        results = self._jump_analyzer.analyze_jump_segment(
            time_seg, fz_seg, jump_number,
            body_weight, calibration_std, calibration_complete_time
        )
        
        # Zero braking peak until later update
        results[f'Jump #{jump_number} Peak Braking Force (N)'] = 0.0
        
        # Emit immediate results
        self.analysis_complete_signal.emit(results)

    def _compute_braking_peak(self, jump_number, landing_index):
        """Compute and emit only the braking peak after landing."""
        full_time, full_multi = self.get_full_data()
        if full_time is None or full_multi is None:
            return
            
        fz_full = np.sum(full_multi, axis=1)
        
        # Use wall-clock timing to find the braking window (300ms after landing)
        if len(full_time) > landing_index:
            landing_time = full_time[landing_index]
            window_end_time = landing_time + 0.3
            end_idx = min(np.abs(full_time - window_end_time).argmin(), len(fz_full))
        else:
            window_samples = int(0.3 * self.sample_rate)
            end_idx = min(landing_index + window_samples, len(fz_full))
            
        # Slice the braking window
        start_idx = landing_index
        braking_peak = float(np.max(fz_full[start_idx:end_idx])) if start_idx < end_idx else 0.0
        self.status_signal.emit(
            f"Computed braking peak for Jump #{jump_number}: {braking_peak:.2f} N"
        )
        
        # Notify UI with only the braking peak
        self.peak_braking_signal.emit(jump_number, braking_peak)
        
    # Expose phase constants for backward compatibility
    PHASE_WAITING = CalibrationManager.PHASE_WAITING
    PHASE_CALIBRATING = CalibrationManager.PHASE_CALIBRATING
    PHASE_READY = CalibrationManager.PHASE_READY
    PHASE_COMPLETED = CalibrationManager.PHASE_COMPLETED
    
    @property
    def test_phase(self):
        """Get current test phase from calibration manager."""
        return self._calibration_manager.test_phase