"""
Real-time jump detection during data acquisition.
Detects takeoff and landing events based on force thresholds.
"""
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
import config


class JumpDetector(QObject):
    """
    Performs real-time jump detection using summed force data.
    Tracks flight phases and triggers analysis when jumps are completed.
    """
    
    # Signals
    status_signal = pyqtSignal(str)
    jump_detected_signal = pyqtSignal(int, int, int)  # jump_number, takeoff_idx, landing_idx
    
    def __init__(self, sample_rate):
        """
        Initialize jump detector.
        
        Args:
            sample_rate: Sampling rate in Hz
        """
        super().__init__()
        
        self.sample_rate = sample_rate
        
        # State for real-time jump detection
        self._in_flight = False
        self._last_contact_index = 0  # Index in full buffer where last contact phase began
        self._last_takeoff_index = None  # Index in full buffer of the last takeoff
        self._jump_counter = 0
        
        # Thresholds
        self._flight_threshold = config.BODYWEIGHT_THRESHOLD_N
        
    def reset(self):
        """Reset jump detection state."""
        self._in_flight = False
        self._last_contact_index = 0
        self._last_takeoff_index = None
        self._jump_counter = 0
        
    def process_chunk(self, time_buffer, force_buffer, num_samples_in_chunk):
        """
        Process new data chunk for jump detection.
        
        Args:
            time_buffer: List of time arrays (from buffer manager)
            force_buffer: List of force arrays (from buffer manager)
            num_samples_in_chunk: Number of samples in the current chunk
            
        Returns:
            tuple: (jump_detected, jump_info) where jump_info is dict with jump details
        """
        # Calculate minimum samples needed based on configuration
        min_flight_samples = config.MIN_FLIGHT_SAMPLES
        min_contact_samples = config.MIN_CONTACT_SAMPLES
        
        # If we have recent timing data, calculate actual sample requirements
        if len(time_buffer) > 0:
            recent_time_chunk = time_buffer[-1]
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
        
        # Check if we have enough data
        total_samples = sum(chunk.shape[0] for chunk in force_buffer)
        if total_samples + num_samples_in_chunk <= history_needed:
            return False, None
            
        # Reconstruct summed Fz history for detection
        full_fz_temp = np.concatenate([np.sum(chunk, axis=1) for chunk in force_buffer])
        recent_fz = full_fz_temp[-history_needed:]  # Look at the last part
        current_index = len(full_fz_temp) - 1
        
        # Get the state of the *last* sample in the current chunk
        is_below_threshold = len(recent_fz) > 0 and recent_fz[-1] < self._flight_threshold
        
        # Track force values to detect potential takeoffs and landings
        if len(recent_fz) > 0:
            # Force drops below threshold - potential takeoff
            if not self._in_flight and is_below_threshold:
                self.status_signal.emit(f"Potential takeoff detected - Force: {recent_fz[-1]:.2f}N, Threshold: {self._flight_threshold:.2f}N")
            
            # Force rises above threshold - potential landing
            if self._in_flight and not is_below_threshold:
                self.status_signal.emit(f"Potential landing detected - Force: {recent_fz[-1]:.2f}N, Threshold: {self._flight_threshold:.2f}N")
        
        jump_info = None
        
        if not self._in_flight:
            # Check for takeoff: several consecutive samples below threshold
            if is_below_threshold and len(recent_fz) >= min_flight_samples:
                # Get the most recent samples
                recent_samples = recent_fz[-min_flight_samples:]
                # Check if ALL samples in the window are below threshold
                if np.all(recent_samples < self._flight_threshold):
                    self._in_flight = True
                    # Find the first sample below threshold
                    below_indices = np.where(recent_fz < self._flight_threshold)[0]
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
            # Check for landing: several consecutive samples above threshold
            if not is_below_threshold and len(recent_fz) >= min_contact_samples:
                # Get most recent samples
                recent_samples = recent_fz[-min_contact_samples:]
                # Check if ALL recent samples are above threshold
                if np.all(recent_samples >= self._flight_threshold):
                    # Landing confirmed!
                    landing_index = current_index - min_contact_samples + 1
                    self._in_flight = False
                    self._jump_counter += 1  # Increment jump counter
                    
                    self.status_signal.emit(f"Landing detected! Force: {recent_samples[0]:.2f}N. Analyzing jump.")
                    
                    # Only proceed if a takeoff was detected
                    if self._last_takeoff_index is not None:
                        jump_info = {
                            'jump_number': self._jump_counter,
                            'takeoff_index': self._last_takeoff_index,
                            'landing_index': landing_index
                        }
                        
                        # Emit signal for jump detection
                        self.jump_detected_signal.emit(
                            self._jump_counter,
                            self._last_takeoff_index,
                            landing_index
                        )
                        
                        # Reset takeoff index to prevent re-detection
                        self._last_takeoff_index = None
                        
                        return True, jump_info
                        
        return False, jump_info
        
    def get_jump_count(self):
        """Get the current jump counter value."""
        return self._jump_counter
        
    def is_in_flight(self):
        """Check if currently detecting a flight phase."""
        return self._in_flight