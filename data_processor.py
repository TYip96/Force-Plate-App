"""
Handles processing of raw DAQ data, including:
- Applying zero offset
- Scaling voltage to force (Newtons)
- Summing channels for total vertical force (Fz)
- Buffering data during acquisition
- Performing post-acquisition analysis (filtering, event detection, metrics).
"""
import numpy as np
import time
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer
from scipy.signal import butter, filtfilt
import config


class DataProcessor(QObject):
    """
    Processes raw data chunks, stores data, and performs analysis.
    Operates in the main application thread (receives signals from DAQ thread).
    """
    # Signal payload: time_array (1D), force_array_multi_channel (2D: [chunk_size, num_channels])
    processed_data_signal = pyqtSignal(np.ndarray, np.ndarray)
    # Signal payload: dictionary of calculated metrics
    analysis_complete_signal = pyqtSignal(dict)
    # Signal payload: jump number and braking peak value
    peak_braking_signal = pyqtSignal(int, float)
    status_signal = pyqtSignal(str)
    
    # New signals for bodyweight calibration phase
    calibration_status_signal = pyqtSignal(str, int)  # Message, countdown seconds
    calibration_complete_signal = pyqtSignal(float)   # Bodyweight in N

    # New signal for jump event markers (start, takeoff, landing)
    jump_event_markers_signal = pyqtSignal(dict)     # Dictionary with event times and forces

    # Define test phases as constants for clarity
    PHASE_WAITING = 0    # Waiting for person to step on plate
    PHASE_CALIBRATING = 1  # Countdown for bodyweight measurement
    PHASE_READY = 2      # Bodyweight measured, ready for jump
    PHASE_COMPLETED = 4  # Jump completed, analyzing

    def __init__(self, sample_rate, num_channels, n_per_volt, parent=None):
        super().__init__(parent)
        self.sample_rate = sample_rate  # Configured/target sample rate
        self.num_channels = num_channels
        self.n_per_volt = n_per_volt # Calibration factor N/V per channel

        # Initialize zero offset (1D array for 4 channels)
        self.zero_offset_v = np.zeros(self.num_channels)

        # Internal buffers for storing data during acquisition
        self._time_buffer = []
        # Store forces per channel: list of arrays, each [chunk_size, num_channels]
        self._force_buffer = []
        
        # Add real-time tracking
        self._last_real_time = None
        
        # Wall-clock timestamp for creating real-time-based sample stamps
        self._last_chunk_time = None

        # --- State for Real-time Jump Detection (using SUMMED force) ---
        self._in_flight = False
        self._last_contact_index = 0 # Index in full buffer where last contact phase began
        self._last_takeoff_index = None # Index in full buffer of the last takeoff
        self._jump_counter = 0
        
        # Body weight tracking for impulse calculation
        self._estimated_body_weight = None
        self._bw_calibration_std = None  # Store standard deviation of body weight calibration data
        
        # Track calibration completion time and data index
        self._calibration_complete_time = None
        self._calibration_complete_index = None
        
        # New state variables for test phases
        self.test_phase = self.PHASE_WAITING
        self._calibration_start_time = None
        self._calibration_duration = 3  # Changed from 5 to 3 seconds of standing still (per research recommendation)
        self._calibration_force_buffer = []
        self._significant_force_threshold = 200  # N - person stepped on plate

        # Butterworth filter parameters (clamp cutoff to just under Nyquist)
        nyquist = self.sample_rate / 2.0
        fc = min(config.FILTER_CUTOFF, nyquist * 0.99)
        # If user requested cutoff above Nyquist, we use fc<Nyquist to avoid ValueError
        self._filter_b, self._filter_a = butter(
            config.FILTER_ORDER,
            fc,
            btype='low',
            analog=False,
            fs=self.sample_rate
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
        self._time_buffer = []
        self._force_buffer = [] # Clear multi-channel force buffer
        
        # Reset real-time tracking
        self._last_real_time = None
        
        # Reset real-time detection state
        self._in_flight = False
        self._last_contact_index = 0
        self._last_takeoff_index = None
        self._jump_counter = 0
        self._estimated_body_weight = None
        self._bw_calibration_std = None  # Reset calibration standard deviation
        
        # Reset test phase
        self.test_phase = self.PHASE_WAITING
        self._calibration_start_time = None
        self._calibration_force_buffer = []
        
        # Reset wall-clock chunk timestamp
        self._last_chunk_time = None
        
        self.status_signal.emit("Data buffers and jump state cleared.")
        self.calibration_status_signal.emit("Stand off the force plate", 0)

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
        # 4. Generate time stamps based on real wall-clock time (spread chunk over actual interval)
        num_samples = raw_data_chunk.shape[0]
        if self._last_chunk_time is None:
            # First chunk: approximate start time by backing off nominal dt
            start_time = now - num_samples / self.sample_rate
        else:
            start_time = self._last_chunk_time
        # Create timestamps evenly spaced from start_time to now
        time_chunk = np.linspace(start_time, now, num_samples, endpoint=True)
        # Remember for next chunk
        self._last_chunk_time = now
        num_samples_in_chunk = num_samples

        # 1. Apply Zero Offset
        offset_corrected_data = raw_data_chunk - self.zero_offset_v

        # 2. Scale to Force (Newtons per channel)
        # Output shape: [chunk_size, num_channels]
        force_data_channels = offset_corrected_data * self.n_per_volt

        # 3. Calculate Total Vertical Force (Fz) - FOR JUMP DETECTION ONLY
        fz_chunk_summed = np.sum(force_data_channels, axis=1)

        # 5. Emit MULTI-CHANNEL data for Plotting
        self.processed_data_signal.emit(time_chunk, force_data_channels)

        # 6. Append MULTI-CHANNEL data to Internal Buffers
        self._time_buffer.append(time_chunk)
        self._force_buffer.append(force_data_channels)
        
        # --- TEST PHASE STATE MACHINE ---
        # Mean force in this chunk
        mean_force = np.mean(fz_chunk_summed)
        
        # STATE: Waiting for person to step on the plate
        if self.test_phase == self.PHASE_WAITING:
            if mean_force > self._significant_force_threshold:
                # Person stepped on the plate - start calibration
                self.test_phase = self.PHASE_CALIBRATING
                self._calibration_start_time = time_chunk[-1]
                self._calibration_force_buffer = []
                self.status_signal.emit("Person detected on force plate. Starting bodyweight calibration.")
                self.calibration_status_signal.emit("Stand still for calibration", self._calibration_duration)
        
        # STATE: Calibrating bodyweight - countdown
        elif self.test_phase == self.PHASE_CALIBRATING:
            # Add the current chunk to calibration buffer
            self._calibration_force_buffer.append(fz_chunk_summed)
            
            # Calculate elapsed time in calibration
            elapsed = time_chunk[-1] - self._calibration_start_time
            remaining = max(0, self._calibration_duration - elapsed)
            countdown = int(remaining) + 1
            
            # Check if force is stable
            if len(self._calibration_force_buffer) > 1:
                recent_data = np.concatenate(self._calibration_force_buffer[-10:]) if len(self._calibration_force_buffer) > 10 else np.concatenate(self._calibration_force_buffer)
                std_dev = np.std(recent_data)
                if std_dev > 10:  # Too much movement
                    # Reset calibration
                    self._calibration_start_time = time_chunk[-1]
                    self._calibration_force_buffer = [fz_chunk_summed]
                    self.status_signal.emit("Please stand still for accurate bodyweight measurement")
                    self.calibration_status_signal.emit("Stand still! Restarting calibration", self._calibration_duration)
                    return
            
            # Update countdown display
            if countdown <= self._calibration_duration:
                self.calibration_status_signal.emit(f"Stand still for calibration", countdown)
            
            # Check if calibration is complete
            if elapsed >= self._calibration_duration:
                # Calculate body weight from the collected data
                all_calibration_data = np.concatenate(self._calibration_force_buffer)
                self._estimated_body_weight = np.mean(all_calibration_data)
                self._bw_calibration_std = np.std(all_calibration_data)  # Store std deviation for jump start detection
                
                # Sanity check on bodyweight
                if self._estimated_body_weight < 200:
                    self.status_signal.emit(f"Warning: Low bodyweight estimate ({self._estimated_body_weight:.1f}N)")
                    
                # Store calibration completion time and current buffer index
                self._calibration_complete_time = time_chunk[-1]
                full_buffer_len = sum(chunk.shape[0] for chunk in self._force_buffer)
                self._calibration_complete_index = full_buffer_len - 1  # Index of the last sample in buffer
                
                self.status_signal.emit(f"Bodyweight calibration complete: {self._estimated_body_weight:.1f}N")
                self.calibration_status_signal.emit(f"Calibration complete: {self._estimated_body_weight:.1f}N", 0)
                self.calibration_complete_signal.emit(self._estimated_body_weight)
                
                # Move to ready state
                self.test_phase = self.PHASE_READY
                self.status_signal.emit("Ready for jump. Perform your jump now!")
        
        # STATE: Ready for jump
        elif self.test_phase == self.PHASE_READY:
            # Only run jump detection if we have a valid bodyweight
            if self._estimated_body_weight is not None and self._estimated_body_weight > 100:
                # --- Regular Jump Detection Logic (using SUMMED force) ---
                # Get a relevant window of the most recent Fz data for state checking
                # Calculate number of samples needed based on wall-clock timing
                # Use configured sample count as minimum, but verify with actual data if available
                min_flight_samples = config.MIN_FLIGHT_SAMPLES
                min_contact_samples = config.MIN_CONTACT_SAMPLES
                
                # If we have recent timing data, calculate actual sample requirements
                if len(self._time_buffer) > 0:
                    recent_time_chunk = self._time_buffer[-1]
                    if len(recent_time_chunk) > 1:
                        # Calculate effective sample rate from recent data
                        recent_dt = np.mean(np.diff(recent_time_chunk))
                        effective_rate = 1.0 / recent_dt if recent_dt > 0 else self.sample_rate
                        
                        # Calculate time-based sample requirements
                        time_based_flight_samples = int(config.MIN_FLIGHT_TIME * effective_rate)
                        time_based_contact_samples = int(0.02 * effective_rate)  # 20ms of contact
                        
                        # Use the greater of configured or time-based counts
                        min_flight_samples = max(config.MIN_FLIGHT_SAMPLES, time_based_flight_samples)
                        min_contact_samples = max(config.MIN_CONTACT_SAMPLES, time_based_contact_samples)
                
                # Need enough data to check for MIN_FLIGHT/CONTACT samples
                history_needed = max(min_flight_samples, min_contact_samples) * 3  # Increase look-back
                
                # Optimization: A deque buffer could make this faster.
                # We need the summed force history here
                if sum(chunk.shape[0] for chunk in self._force_buffer) + num_samples_in_chunk > history_needed:
                     # Reconstruct summed Fz history as needed for detection logic
                     # This could be optimized by storing the summed buffer separately if needed frequently
                    full_fz_temp = np.concatenate([np.sum(chunk, axis=1) for chunk in self._force_buffer])
                    recent_fz = full_fz_temp[-history_needed:] # Look at the last part
                    current_index = len(full_fz_temp) - 1

                    # Get the state of the *last* sample in the current chunk
                    # Always use the consistent threshold from config
                    flight_threshold = config.BODYWEIGHT_THRESHOLD_N
                    
                    # Check if current force is below threshold
                    is_below_threshold = len(recent_fz) > 0 and recent_fz[-1] < flight_threshold

                    # Track force values to detect potential takeoffs and landings
                    if len(recent_fz) > 0:
                        # Force drops below threshold - potential takeoff
                        if not self._in_flight and is_below_threshold:
                            self.status_signal.emit(f"Potential takeoff detected - Force: {recent_fz[-1]:.2f}N, Threshold: {flight_threshold:.2f}N")

                        # Force rises above threshold - potential landing
                        if self._in_flight and not is_below_threshold:
                            self.status_signal.emit(f"Potential landing detected - Force: {recent_fz[-1]:.2f}N, Threshold: {flight_threshold:.2f}N")

                    if not self._in_flight:
                        # We need several consecutive samples below threshold for reliable takeoff detection
                        # Check if we have enough consecutive samples below threshold
                        if is_below_threshold and len(recent_fz) >= min_flight_samples:
                            # Get the most recent samples
                            recent_samples = recent_fz[-min_flight_samples:]
                            # Check if ALL samples in the window are below threshold
                            if np.all(recent_samples < flight_threshold):
                                self._in_flight = True
                                # Take the first sample below threshold as the takeoff index
                                below_indices = np.where(recent_fz < flight_threshold)[0]
                                # Find the first consecutive sequence of MIN_FLIGHT_SAMPLES
                                for i in range(len(below_indices) - min_flight_samples + 1):
                                    if np.all(np.diff(below_indices[i:i+min_flight_samples]) == 1):
                                        self._last_takeoff_index = current_index - (len(recent_fz) - below_indices[i])
                                        break
                                else:
                                    # Fallback if no consecutive sequence found
                                    self._last_takeoff_index = current_index - min_flight_samples + 1
                                
                                self.status_signal.emit(f"Takeoff detected! Force: {recent_samples[0]:.2f}N")
                    else:  # In flight
                        # For landing, we need several consecutive samples above threshold
                        if not is_below_threshold and len(recent_fz) >= min_contact_samples:
                            # Get most recent samples
                            recent_samples = recent_fz[-min_contact_samples:]
                            # Check if ALL recent samples are above threshold
                            if np.all(recent_samples >= flight_threshold):
                                # Landing confirmed!
                                landing_index = current_index - min_contact_samples + 1
                                self._in_flight = False
                                self._jump_counter += 1  # Increment jump counter
                                
                                self.status_signal.emit(f"Landing detected! Force: {recent_samples[0]:.2f}N. Analyzing jump.")

                                # Only proceed if a takeoff was detected
                                if self._last_takeoff_index is not None:
                                    takeoff_idx = self._last_takeoff_index
                                    jump_num    = self._jump_counter
                                    landing_idx = landing_index

                                    # Compute and emit basic metrics immediately (excluding braking peak)
                                    self._compute_basic_metrics(jump_num, takeoff_idx, landing_idx)

                                    # Schedule only braking peak computation after 300 ms
                                    delay_ms = int(0.3 * 1000)
                                    self.status_signal.emit(
                                        f"Scheduling braking-peak calc in {delay_ms} ms"
                                    )
                                    QTimer.singleShot(
                                        delay_ms,
                                        lambda jn=jump_num, li=landing_idx: self._compute_braking_peak(jn, li)
                                    )
                                    # Prevent re-scheduling for the same takeoff
                                    self._last_takeoff_index = None

        # STATE: Completed - waiting for person to step off
        elif self.test_phase == self.PHASE_COMPLETED:
            # Check if person stepped off the plate to get ready for next test
            if mean_force < self._significant_force_threshold:
                # Reset for the next test
                self.test_phase = self.PHASE_WAITING
                self.status_signal.emit("Ready for next person. Step on the plate to begin.")
                self.calibration_status_signal.emit("Step on force plate to begin test", 0)

    def _find_stable_regions(self, force_data, sample_rate):
        """Identify regions of stable force that likely represent standing/bodyweight."""
        if len(force_data) < 0.1 * sample_rate:  # Need at least 100ms of data
            return []
            
        # Calculate rolling std deviation with a 50ms window
        window_size = int(0.05 * sample_rate)
        if window_size < 2:
            window_size = 2
            
        rolling_std = []
        for i in range(len(force_data) - window_size):
            window = force_data[i:i+window_size]
            rolling_std.append(np.std(window))
            
        # Consider stable regions where std deviation is low
        stable_threshold = 10.0  # N (adjust based on typical noise in your system)
        stable_regions = []
        
        in_stable_region = False
        start_idx = 0
        
        for i, std_val in enumerate(rolling_std):
            if not in_stable_region and std_val < stable_threshold:
                in_stable_region = True
                start_idx = i
            elif in_stable_region and (std_val >= stable_threshold or i == len(rolling_std)-1):
                in_stable_region = False
                end_idx = i
                if end_idx - start_idx > 0.03 * sample_rate:  # At least 30ms
                    stable_regions.append((start_idx, end_idx))
                    
        return stable_regions

    def _find_time_window_samples(self, time_array, duration_seconds):
        """Find the number of samples that corresponds to a given time duration.
        
        Args:
            time_array: Array of wall-clock timestamps
            duration_seconds: Duration in seconds
            
        Returns:
            Number of samples corresponding to the duration
        """
        if len(time_array) < 2:
            # Fallback to configured sample rate if insufficient data
            return int(duration_seconds * self.sample_rate)
        
        # Calculate actual time span and sample count
        total_time_span = time_array[-1] - time_array[0]
        total_samples = len(time_array)
        
        # Calculate effective sample rate from the data
        effective_rate = total_samples / total_time_span if total_time_span > 0 else self.sample_rate
        
        return int(duration_seconds * effective_rate)


    def get_full_data(self):
        """Returns the complete collected data as NumPy arrays.
           Returns: (full_time [1D], full_force_multi_channel [2D: samples, channels])
        """
        if not self._time_buffer or not self._force_buffer:
            return None, None

        full_time = np.concatenate(self._time_buffer)
        # Concatenate along the first axis (samples)
        full_force_multi_channel = np.concatenate(self._force_buffer, axis=0) 
        return full_time, full_force_multi_channel

    def _analyze_jump_segment(self, time_data_absolute, fz_data, jump_number):
        """Performs analysis on a specific segment of SUMMED Fz data representing one jump."""
        results = {
            f'Jump #{jump_number} Body Weight (N)': 'N/A',
            f'Jump #{jump_number} Peak Propulsive Force (N)': 0,
            f'Jump #{jump_number} Peak Braking Force (N)': 0,
            f'Jump #{jump_number} Flight Time (s)': 0,
            f'Jump #{jump_number} Jump Height (Flight Time) (m)': 0,
            f'Jump #{jump_number} Jump Height (Impulse) (m)': 0,
            f'Jump #{jump_number} Analysis Note': ''
        }
        
        # Initialize critical variables with defaults to prevent UnboundLocalError
        movement_start_idx_abs = 0  # Default to start of data
        first_takeoff_idx = None  # Initialize to None instead of 0
        first_landing_idx = 0

        if time_data_absolute is None or fz_data is None or len(time_data_absolute) < config.MIN_CONTACT_SAMPLES + config.MIN_FLIGHT_SAMPLES:
            note = "Not enough data for analysis."
            results[f'Jump #{jump_number} Analysis Note'] = note
            
            # Clean up keys for failed analysis
            keys_to_remove = [k for k in results if k != f'Jump #{jump_number} Analysis Note']
            for k in keys_to_remove:
                del results[k]
            return results

        try:

            # 1. Filter the Force Data for this segment
            # Pad slightly for filtfilt edge effects if possible, or accept minor edge artifact
            fz_filtered = filtfilt(self._filter_b, self._filter_a, fz_data)

            # 2. Estimate Bodyweight (use calibration value since it's always available)
            body_weight_n = self._estimated_body_weight
            
            # Sanity check on body weight
            if body_weight_n < 100:  # Unrealistically low for most humans
                self.status_signal.emit(f"Warning: Low bodyweight estimate ({body_weight_n:.1f}N)")
                results[f'Jump #{jump_number} Analysis Note'] += " Low bodyweight estimate."
            
            results[f'Jump #{jump_number} Body Weight (N)'] = round(body_weight_n, 2)

            # 4. Detect Events within this segment with adaptive threshold
            flight_threshold = max(config.BODYWEIGHT_THRESHOLD_N, body_weight_n * 0.2)
            # Pass both filtered and unfiltered Fz data
            takeoff_indices, landing_indices = self._find_flight_phases(fz_data, fz_filtered, flight_threshold)

            flight_detected = takeoff_indices.size > 0 and landing_indices.size > 0

            if not flight_detected:
                results[f'Jump #{jump_number} Analysis Note'] += " Incomplete/No flight phase. Searching manually..."
                
                # Manual detection - find regions where force is below threshold
                below_threshold = fz_filtered < flight_threshold
                flight_regions = []
                in_flight = False
                flight_start = 0
                
                for i, is_below in enumerate(below_threshold):
                    if not in_flight and is_below:
                        in_flight = True
                        flight_start = i
                    elif in_flight and not is_below:
                        in_flight = False
                        flight_duration = i - flight_start
                        if flight_duration >= config.MIN_FLIGHT_SAMPLES:
                            flight_regions.append((flight_start, i))
                
                # If flight still in progress at the end
                if in_flight and len(below_threshold) - flight_start >= config.MIN_FLIGHT_SAMPLES:
                    flight_regions.append((flight_start, len(below_threshold)))
                
                if flight_regions:
                    # Find the longest flight phase
                    longest_flight = max(flight_regions, key=lambda x: x[1] - x[0])
                    takeoff_indices = np.array([longest_flight[0]])
                    landing_indices = np.array([longest_flight[1]])
                    flight_detected = True
                    self.status_signal.emit(f"Manual flight detection successful for Jump #{jump_number}")

            if flight_detected:
                # --- Analyze the first valid jump within the segment ---
                first_takeoff_idx = takeoff_indices[0]
                    # Find the first landing *after* this takeoff
                valid_landing_indices = landing_indices[landing_indices > first_takeoff_idx]

                if valid_landing_indices.size == 0:
                              results[f'Jump #{jump_number} Analysis Note'] += " Takeoff no landing."
                else:
                    first_landing_idx = valid_landing_indices[0]

                    # Compute peak propulsive and braking forces (only when landing is detected)
                    if first_takeoff_idx is not None and first_takeoff_idx > 0:
                        propulsive_peak = np.max(fz_data[:first_takeoff_idx])
                    else:
                        propulsive_peak = 0.0

                    # Calculate braking window using wall-clock timing
                    braking_window_samples = self._find_time_window_samples(time_data_absolute, 0.5)
                    braking_end_idx = min(first_landing_idx + braking_window_samples, len(fz_data))
                    if first_landing_idx < braking_end_idx:
                        braking_peak = np.max(fz_data[first_landing_idx:braking_end_idx])
                    else:
                        braking_peak = 0.0

                    results[f'Jump #{jump_number} Peak Propulsive Force (N)'] = round(propulsive_peak, 2)
                    results[f'Jump #{jump_number} Peak Braking Force (N)'] = round(braking_peak, 2)

                    # Compute flight time and height using actual timestamps
                    if hasattr(self, '_takeoff_idx_precise') and self._takeoff_idx_precise >= 0:
                        to_floor = int(self._takeoff_idx_precise)
                        to_ceil = min(to_floor + 1, len(time_data_absolute) - 1)
                        to_frac = self._takeoff_idx_precise - to_floor
                        takeoff_time = time_data_absolute[to_floor] + to_frac * (time_data_absolute[to_ceil] - time_data_absolute[to_floor])
                    else:
                        takeoff_time = time_data_absolute[first_takeoff_idx]

                    if hasattr(self, '_landing_idx_precise') and self._landing_idx_precise >= 0:
                        la_floor = int(self._landing_idx_precise)
                        la_ceil = min(la_floor + 1, len(time_data_absolute) - 1)
                        la_frac = self._landing_idx_precise - la_floor
                        landing_time = time_data_absolute[la_floor] + la_frac * (time_data_absolute[la_ceil] - time_data_absolute[la_floor])
                    else:
                        landing_time = time_data_absolute[first_landing_idx]

                    flight_time = landing_time - takeoff_time

                    if flight_time < config.MIN_FLIGHT_TIME or flight_time > config.MAX_FLIGHT_TIME:
                        print(f"NOTICE: Timestamp-based flight time {flight_time:.3f}s outside expected range [{config.MIN_FLIGHT_TIME}, {config.MAX_FLIGHT_TIME}]")
                        results[f'Jump #{jump_number} Analysis Note'] += " Timestamp-based flight time outside typical range."

                    results[f'Jump #{jump_number} Flight Time (s)'] = round(flight_time, 3)
                    jump_height_m = (config.GRAVITY * flight_time**2) / 8.0
                    results[f'Jump #{jump_number} Jump Height (Flight Time) (m)'] = round(jump_height_m, 3)

        
                    # Find the beginning of the countermovement for impulse calculation
                    # Make sure first_takeoff_idx is not None and not 0 (to ensure there is data before takeoff)
                    if first_takeoff_idx is None or first_takeoff_idx < 10:
                        results[f'Jump #{jump_number} Analysis Note'] += " Impulse calculation skipped (invalid takeoff index)."
                        # Set a default movement_start_idx_abs to avoid issues with marker creation
                        movement_start_idx_abs = 0
                    else:
                        # Use the full data up to takeoff for finding the countermovement start
                        search_range_onset = fz_filtered[:first_takeoff_idx]

                        # Check if we have enough data before takeoff for a proper analysis
                        if len(search_range_onset) < 10:  # Need at least 10 samples before takeoff
                            movement_start_idx_abs = 0  # Default to start of data segment
                            
                            # Even with limited data, try a basic impulse calculation
                            if flight_time > 0 and body_weight_n > 0:
                                mass = body_weight_n / config.GRAVITY
                                full_movement_force = fz_filtered[movement_start_idx_abs:first_takeoff_idx]
                                full_movement_time = time_data_absolute[movement_start_idx_abs:first_takeoff_idx]
                                
                                if len(full_movement_time) > 1:  # Need at least 2 samples for trapezoidal rule
                                    net_force_full = full_movement_force - body_weight_n
                                    net_impulse = np.trapz(net_force_full, full_movement_time)
                                    
                                    takeoff_velocity = net_impulse / mass
                                    jump_height_impulse_m = (takeoff_velocity**2) / (2 * config.GRAVITY)
                                    
                                    # Only use this if it's reasonable
                                    if jump_height_impulse_m > 0 and jump_height_impulse_m < 2.0:  # Max reasonable jump height
                                        results[f'Jump #{jump_number} Jump Height (Impulse) (m)'] = round(jump_height_impulse_m, 3)
                                        results[f'Jump #{jump_number} Net Impulse (Ns)'] = round(net_impulse, 2)
                                        self.status_signal.emit(f"Jump #{jump_number} Impulse Height: {jump_height_impulse_m:.3f}m (estimated with limited data)")
                                        results[f'Jump #{jump_number} Analysis Note'] += " Limited impulse calculation using available data."
                                    else:
                                        results[f'Jump #{jump_number} Analysis Note'] += " Impulse calculation skipped (not enough data before takeoff)."
                                else:
                                    results[f'Jump #{jump_number} Analysis Note'] += " Impulse calculation skipped (not enough data before takeoff)."
                            else:
                                results[f'Jump #{jump_number} Analysis Note'] += " Impulse calculation skipped (not enough data before takeoff)."
                        else:
                            # Sufficient data case: Use normal calculation
                            if flight_time > 0:  # Ensure we have a valid flight time
                                # Calculate jump height using flight time method (already done above)
                                
                                # Also calculate jump height using impulse method
                                # Find where force drops below body weight (start of countermovement)
                                cm_start_indices = np.where(search_range_onset < body_weight_n * 0.95)[0]
                                if cm_start_indices.size > 0:
                                    movement_onset_idx = cm_start_indices[0]
                                else:
                                    # Fallback: find min force before takeoff (likely countermovement)
                                    movement_onset_idx = np.argmin(search_range_onset)
                                    
                                # Calculate Impulse and Impulse-based Jump Height
                                if body_weight_n > 0:
                                    mass = body_weight_n / config.GRAVITY
                                    
                                    # *** CALIBRATION-BASED JUMP START DETECTION ***
                                    # Start searching right after the calibration completion point
                                    
                                    # Default to 10% if we don't have calibration time (fallback)
                                    search_start_idx = int(len(search_range_onset) * 0.1)
                                    
                                    # If we have a valid calibration completion time, use it
                                    if self._calibration_complete_time is not None:
                                        # Find the closest time point in our data to the calibration completion time
                                        # First adjust for the segment start time
                                        if len(time_data_absolute) > 0:
                                            segment_start_time = time_data_absolute[0]
                                            rel_calib_time = self._calibration_complete_time - segment_start_time
                                            
                                            # Find the closest index to this time
                                            if rel_calib_time > 0:  # Only if calibration time is within segment
                                                # Find index where time is closest to calibration completion
                                                calib_idx = np.abs(time_data_absolute - (segment_start_time + rel_calib_time)).argmin()
                                                
                                                # Start searching a little bit after calibration (add 100ms buffer)
                                                buffer_samples = self._find_time_window_samples(time_data_absolute, 0.1)
                                                search_start_idx = min(calib_idx + buffer_samples, len(search_range_onset) - 1)
                                                
                                            else:
                                                # Calibration happened before this segment
                                                search_start_idx = 0
                                        else:
                                            # Default case - start from beginning
                                            search_start_idx = 0
                                    
                                    # Get the bodyweight threshold (5 SD below BW)
                                    # Using 5 SD as threshold based on research recommendation
                                    SD_MULTIPLIER = 5
                                    
                                    # Use stored standard deviation from calibration phase
                                    calibration_sd = self._bw_calibration_std
                                    if calibration_sd is None:
                                        # This should not happen if calibration phase ran correctly
                                        print("ERROR: Calibration SD not found during analysis! Using fallback estimate.")
                                        # Provide a minimal fallback if absolutely necessary, but log the error.
                                        calibration_sd = 5.0 # Default arbitrary SD value
                                        results[f'Jump #{jump_number} Analysis Note'] += " Error: Missing Calib SD."
                                    
                                    # Calculate movement threshold (5 SD below BW)
                                    movement_threshold = body_weight_n - (SD_MULTIPLIER * calibration_sd)
                                    
                                    # Find first point where force drops below the threshold (moving forward in time)
                                    movement_start_idx = search_start_idx  # Default to search start if no crossing found
                                    movement_found = False
                                    
                                    for i in range(search_start_idx, len(search_range_onset)):
                                        if search_range_onset[i] < movement_threshold:
                                            movement_start_idx = i
                                            movement_found = True
                                            break
                                    
                                    if movement_found:
                                        # Now search backward from this point to find where force crosses through BW
                                        for i in range(movement_start_idx, search_start_idx, -1):
                                            if i > 0:  # Ensure we can access i-1
                                                # Check if we crossed bodyweight (from above to below or below to above)
                                                if (search_range_onset[i] <= body_weight_n and search_range_onset[i-1] > body_weight_n) or \
                                                   (search_range_onset[i] >= body_weight_n and search_range_onset[i-1] < body_weight_n):
                                                    movement_start_idx = i
                                                    break
                                    else:
                                        # No movement detected, use default
                                        movement_start_idx = 0
                                    
                                    # Convert to absolute index in the full segment
                                    movement_start_idx_abs = movement_start_idx
                                    
                                    # Calculate full range from movement start to takeoff
                                    full_movement_force = fz_filtered[movement_start_idx_abs:first_takeoff_idx]
                                    full_movement_time = time_data_absolute[movement_start_idx_abs:first_takeoff_idx]
                                    
                                    # Use the previously calculated body_weight_n for net force
                                    net_force_full = full_movement_force - body_weight_n

                    # Now that movement_start_idx_abs is set properly, emit event markers for visualization
                    if (time_data_absolute is not None and len(time_data_absolute) > 0 and 
                        movement_start_idx_abs < len(time_data_absolute) and 
                        first_takeoff_idx is not None and first_takeoff_idx < len(time_data_absolute) and 
                        first_landing_idx < len(time_data_absolute) and
                        all(idx >= 0 for idx in [movement_start_idx_abs, first_takeoff_idx, first_landing_idx]) and
                        # Only emit markers if we have actually calculated jump height (either method)
                        (f'Jump #{jump_number} Jump Height (Flight Time) (m)' in results or 
                         f'Jump #{jump_number} Jump Height (Impulse) (m)' in results)):
                    
                        # Get exact event times from the data
                        jump_start_time = time_data_absolute[movement_start_idx_abs]
                        jump_start_force = fz_filtered[movement_start_idx_abs]
                        
                        
                        # Print time values around the movement start index
                        start_idx = max(0, movement_start_idx_abs - 5)
                        end_idx = min(len(time_data_absolute), movement_start_idx_abs + 5)
                        time_slice = time_data_absolute[start_idx:end_idx]
                        
                        
                        # Use precise interpolated values for takeoff and landing if available
                        if hasattr(self, '_takeoff_idx_precise') and self._takeoff_idx_precise >= 0:
                            # Interpolate time and force for takeoff
                            takeoff_idx_floor = int(self._takeoff_idx_precise)
                            takeoff_idx_ceil = min(takeoff_idx_floor + 1, len(time_data_absolute) - 1)
                            frac = self._takeoff_idx_precise - takeoff_idx_floor
                            
                            # Linear interpolation of time and force
                            takeoff_time = time_data_absolute[takeoff_idx_floor] + frac * (time_data_absolute[takeoff_idx_ceil] - time_data_absolute[takeoff_idx_floor])
                            takeoff_force = config.BODYWEIGHT_THRESHOLD_N
                            
                        else:
                            # Fallback to original method
                            takeoff_time = time_data_absolute[first_takeoff_idx]
                            takeoff_force = fz_filtered[first_takeoff_idx]
                        
                        # Similarly for landing
                        if hasattr(self, '_landing_idx_precise') and self._landing_idx_precise > 0:
                            # Interpolate time and force for landing
                            landing_idx_floor = int(self._landing_idx_precise)
                            landing_idx_ceil = min(landing_idx_floor + 1, len(time_data_absolute) - 1)
                            frac = self._landing_idx_precise - landing_idx_floor
                            
                            # Linear interpolation of time and force
                            landing_time = time_data_absolute[landing_idx_floor] + frac * (time_data_absolute[landing_idx_ceil] - time_data_absolute[landing_idx_floor])
                            landing_force = config.BODYWEIGHT_THRESHOLD_N
                            
                        else:
                            # Fallback to original method
                            landing_time = time_data_absolute[first_landing_idx]
                            landing_force = fz_filtered[first_landing_idx]
                        
                        # Create and emit the event markers dictionary
                        event_markers = {
                            'jump_number': jump_number,
                            'jump_start_time': jump_start_time,
                            'jump_start_force': jump_start_force,
                            'takeoff_time': takeoff_time,
                            'takeoff_force': takeoff_force,
                            'landing_time': landing_time,
                            'landing_force': landing_force
                        }
                        
                        # Verify values are as expected
                        if jump_start_time < 0.001:  # Almost zero
                            # Try to get a more reasonable time value as a fallback
                            if movement_start_idx_abs > 0 and len(time_data_absolute) > movement_start_idx_abs:
                                direct_time = float(time_data_absolute[movement_start_idx_abs])
                                jump_start_time = direct_time
                                event_markers['jump_start_time'] = direct_time
                                
                        # Add markers for visualization
                        self.jump_event_markers_signal.emit(event_markers)
                        
                    # --- Continue with impulse calculations after emitting event markers ---
                    # This section starts with checking if we have enough data points for impulse calculation
                    if flight_time > 0 and body_weight_n > 0 and first_takeoff_idx is not None and first_takeoff_idx > 10:
                        if len(full_movement_time) > 10:  # Need enough samples
                            # Calculate total net impulse using trapezoidal rule
                            net_impulse = np.trapz(net_force_full, full_movement_time)
                            
                            # Calculate takeoff velocity from impulse
                            takeoff_velocity = net_impulse / mass
                            
                            # Calculate jump height from takeoff velocity
                            jump_height_impulse_m = (takeoff_velocity**2) / (2 * config.GRAVITY)
                            
                            # Add results to output dictionary
                            results[f'Jump #{jump_number} Jump Height (Impulse) (m)'] = round(jump_height_impulse_m, 3)
                            results[f'Jump #{jump_number} Net Impulse (Ns)'] = round(net_impulse, 2)
                            self.status_signal.emit(f"Jump #{jump_number} Impulse Height: {jump_height_impulse_m:.3f}m")

            # Clean up note
            final_note = results[f'Jump #{jump_number} Analysis Note'].strip()
            if not final_note:
                del results[f'Jump #{jump_number} Analysis Note'] # Remove if empty
            else:
                results[f'Jump #{jump_number} Analysis Note'] = final_note

            return results

        except Exception as e:
            self.status_signal.emit(f"Analysis failed for jump segment: {e}")
            print(f"Analysis Error (Segment): {e}")
            import traceback
            traceback.print_exc()
            results[f'Jump #{jump_number} Error'] = str(e)
            return results

    def _find_flight_phases(self, fz_data, fz_filtered, threshold_n):
        """Identifies start (takeoff) and end (landing) indices of flight phases.
        
        Uses unfiltered data for 20N threshold crossings and filtered data for 50N anchor points.
        
        Args:
            fz_data: Unfiltered summed force data array
            fz_filtered: Filtered summed force data array
            threshold_n: Threshold for flight detection (passed from caller, but we use fixed thresholds)
            
        Returns:
            takeoff_indices: Array of indices where takeoff occurs (based on unfiltered crossing)
            landing_indices: Array of indices where landing occurs (based on unfiltered crossing)
        """
        # Define thresholds
        flight_threshold = config.BODYWEIGHT_THRESHOLD_N  # 20N for precise flight detection
        transition_threshold = 50.0  # 50N for reliable transition detection (using filtered data)

        # Calculate sample-based thresholds using configured sample rate as fallback
        configured_min_flight_samples = int(config.MIN_FLIGHT_TIME * self.sample_rate)
        actual_min_samples = max(config.MIN_FLIGHT_SAMPLES, configured_min_flight_samples)
        
        
        # =====================================================================
        # TAKEOFF DETECTION (Unfiltered Data)
        # =====================================================================
        # Search for the first point where unfiltered force crosses below 20N
        takeoff_idx = -1
        for i in range(1, len(fz_data)): # Start from index 1 to check i-1
            if fz_data[i-1] >= flight_threshold and fz_data[i] < flight_threshold:
                takeoff_idx = i
                break # Found the first crossing
        
        if takeoff_idx == -1:
            return np.array([]), np.array([])
        

        # =====================================================================
        # LANDING DETECTION (Filtered 50N -> Unfiltered 20N)
        # =====================================================================
        # 1. First find where FILTERED force CROSSES ABOVE 50N after takeoff (for reliable landing anchor)
        landing_50N_crossings = []
        for i in range(takeoff_idx + 1, len(fz_filtered)):
            if fz_filtered[i-1] < transition_threshold and fz_filtered[i] >= transition_threshold:
                landing_50N_crossings.append(i)
                break  # We only need the first one
        
        if not landing_50N_crossings:
            # Return the takeoff index found, but no landing index
            # Interpolate takeoff before returning
            self._interpolate_takeoff(fz_data, takeoff_idx, flight_threshold)
            return np.array([takeoff_idx]), np.array([])
        
        # Get the 50N upward crossing index (from filtered data)
        idx_50N_up = landing_50N_crossings[0]
        
        # 2. Search BACKWARD from the 50N crossing to find the FIRST 20N crossing using UNFILTERED data
        landing_idx = idx_50N_up  # Default to the 50N crossing if no 5N crossing is found below
        found_5N_landing_crossing = False
        
        # Define search window (max 200ms before 50N detection, min 50ms after takeoff)
        # Use configured sample rate as fallback for time-based calculations
        search_window_samples = min(int(0.2 * self.sample_rate), idx_50N_up - takeoff_idx)
        min_gap_samples = int(0.05 * self.sample_rate)  # 50ms after takeoff
        search_start = max(takeoff_idx + min_gap_samples, idx_50N_up - search_window_samples)
        
        
        for i in range(idx_50N_up, search_start, -1):
            # Check that we have a valid previous index and array bounds
            if i > 0 and i < len(fz_data):
                # Check for crossing from below 20N to above 20N in UNFILTERED data
                if fz_data[i-1] < flight_threshold and fz_data[i] >= flight_threshold:
                    landing_idx = i
                    found_5N_landing_crossing = True
                    break # Found the first one searching backward
        
        if not found_5N_landing_crossing:
            # Keep landing_idx = idx_50N_up
            pass
        

        # Find precise takeoff and landing points using linear interpolation on UNFILTERED data
        self._interpolate_takeoff(fz_data, takeoff_idx, flight_threshold)
        self._interpolate_landing(fz_data, landing_idx, flight_threshold, found_5N_landing_crossing)
        
        # Calculate precise flight time using wall-clock timing instead of sample rate
        if hasattr(self, '_takeoff_idx_precise') and hasattr(self, '_landing_idx_precise'):
            # Get the full time data to convert interpolated indices to wall-clock timestamps
            full_time, _ = self.get_full_data()
            if full_time is not None:
                # Convert interpolated indices to actual wall-clock timestamps
                takeoff_time_precise = self._interpolated_index_to_wallclock_time(self._takeoff_idx_precise, full_time)
                landing_time_precise = self._interpolated_index_to_wallclock_time(self._landing_idx_precise, full_time)
                
                if takeoff_time_precise is not None and landing_time_precise is not None:
                    flight_time_precise = landing_time_precise - takeoff_time_precise
                    self._flight_time_precise = flight_time_precise
                    
                    # Only print a warning if flight time is outside expected range, but don't override the value
                    if flight_time_precise < config.MIN_FLIGHT_TIME or flight_time_precise > config.MAX_FLIGHT_TIME:
                        print(f"WARNING: Flight time {flight_time_precise:.3f}s outside expected range [{config.MIN_FLIGHT_TIME}, {config.MAX_FLIGHT_TIME}]")
                        print(f"WARNING: Using actual detected flight time regardless of range")
                else:
                    # Fallback to sample-rate method if wall-clock conversion fails
                    flight_time_precise = (self._landing_idx_precise - self._takeoff_idx_precise) / self.sample_rate
                    self._flight_time_precise = flight_time_precise
            else:
                # Fallback to sample-rate method if no time data available
                flight_time_precise = (self._landing_idx_precise - self._takeoff_idx_precise) / self.sample_rate
                self._flight_time_precise = flight_time_precise
        else:
            # Fallback if interpolation failed somehow
            full_time, _ = self.get_full_data()
            if full_time is not None:
                # Use wall-clock time for non-interpolated indices too
                takeoff_time = full_time[takeoff_idx] if takeoff_idx < len(full_time) else None
                landing_time = full_time[landing_idx] if landing_idx < len(full_time) else None
                
                if takeoff_time is not None and landing_time is not None:
                    flight_time = landing_time - takeoff_time
                    self._flight_time_precise = flight_time
                else:
                    # Final fallback to sample-rate method
                    flight_time = (landing_idx - takeoff_idx) / self.sample_rate
                    self._flight_time_precise = flight_time
            else:
                # Final fallback to sample-rate method
                flight_time = (landing_idx - takeoff_idx) / self.sample_rate
                self._flight_time_precise = flight_time
                
        # Return the raw indices found (interpolation happens internally and stores results)
        return np.array([takeoff_idx]), np.array([landing_idx])

    def _interpolate_takeoff(self, fz_data, takeoff_idx, flight_threshold):
        """Interpolates the precise takeoff index using unfiltered data."""
        if takeoff_idx > 0 and takeoff_idx < len(fz_data):
            force_before = fz_data[takeoff_idx-1]  # Force >= threshold
            force_after = fz_data[takeoff_idx]     # Force < threshold
            
            # Compute the fraction where force crosses the threshold
            if force_before != force_after:  # Avoid division by zero
                # Interpolation for downward crossing: fraction of interval AFTER index
                interp_fraction = (force_before - flight_threshold) / (force_before - force_after)
                self._takeoff_idx_precise = (takeoff_idx - 1) + interp_fraction # Index is between i-1 and i
            else:
                 self._takeoff_idx_precise = float(takeoff_idx) # Landed exactly on threshold? Unlikely.
        else:
            self._takeoff_idx_precise = float(takeoff_idx) # Cannot interpolate at edge

    def _interpolate_landing(self, fz_data, landing_idx, flight_threshold, found_5N_crossing):
        """Interpolates the precise landing index using unfiltered data, if 5N crossing was found."""
        # Only interpolate if we actually found the 5N crossing. Otherwise, use the 50N index directly.
        if found_5N_crossing and landing_idx > 0 and landing_idx < len(fz_data):
            force_before = fz_data[landing_idx-1]  # Force < threshold
            force_after = fz_data[landing_idx]     # Force >= threshold
            
            # Compute the fraction where force crosses the threshold
            if force_after != force_before:  # Avoid division by zero
                # Interpolation for upward crossing: fraction of interval AFTER index
                interp_fraction = (flight_threshold - force_before) / (force_after - force_before)
                self._landing_idx_precise = (landing_idx - 1) + interp_fraction # Index is between i-1 and i
            else:
                self._landing_idx_precise = float(landing_idx)
        else:
            # If we didn't find 5N crossing or landed at edge, use the index we have (idx_50N_up) without interpolation
            self._landing_idx_precise = float(landing_idx)

    def _interpolated_index_to_wallclock_time(self, interpolated_index, time_data):
        """Convert an interpolated index to wall-clock time using actual timestamps."""
        if time_data is None or len(time_data) == 0:
            return None
            
        # Ensure index is within bounds
        if interpolated_index < 0 or interpolated_index >= len(time_data):
            return None
            
        # Get integer part and fractional part
        index_floor = int(interpolated_index)
        index_frac = interpolated_index - index_floor
        
        # Handle edge cases
        if index_floor >= len(time_data) - 1:
            return time_data[-1]
        if index_floor < 0:
            return time_data[0]
            
        # Linear interpolation between adjacent timestamps
        time_before = time_data[index_floor]
        time_after = time_data[index_floor + 1]
        interpolated_time = time_before + index_frac * (time_after - time_before)
        
        return interpolated_time

    def _compute_basic_metrics(self, jump_number, takeoff_index, landing_index):
        """Compute all jump metrics except braking, then emit full-results dict."""
        full_time, full_multi = self.get_full_data()
        if full_time is None or full_multi is None:
            return
        # Sum to get Fz
        fz_full = np.sum(full_multi, axis=1)
        # Define segment window: 1s before takeoff to landing
        # Use wall-clock timing to find the right window
        if full_time is not None and len(full_time) > takeoff_index:
            takeoff_time = full_time[takeoff_index]
            window_start_time = takeoff_time - 1.0  # 1 second before takeoff
            start_idx = max(0, np.abs(full_time - window_start_time).argmin())
        else:
            # Fallback to configured sample rate
            start_idx = max(0, takeoff_index - int(1.0 * self.sample_rate))
        end_idx   = landing_index + 1
        time_seg = full_time[start_idx:end_idx]
        fz_seg   = fz_full[start_idx:end_idx]
        # Perform full analysis on this segment
        results = self._analyze_jump_segment(time_seg, fz_seg, jump_number)
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
            window_end_time = landing_time + 0.3  # 300ms after landing
            end_idx = min(np.abs(full_time - window_end_time).argmin(), len(fz_full))
        else:
            # Fallback to configured sample rate
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