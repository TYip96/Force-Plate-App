"""
Manages bodyweight calibration state machine and logic.
Handles the countdown, stability detection, and bodyweight calculation.
"""
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal
import config


class CalibrationManager(QObject):
    """
    Manages the bodyweight calibration process with a state machine.
    Emits signals for UI updates during calibration phases.
    """
    
    # Signals for calibration status updates
    calibration_status_signal = pyqtSignal(str, int)  # Message, countdown seconds
    calibration_complete_signal = pyqtSignal(float)   # Bodyweight in N
    status_signal = pyqtSignal(str)
    
    # Define test phases as constants for clarity
    PHASE_WAITING = 0    # Waiting for person to step on plate
    PHASE_WAITING_FOR_STABILITY = 1  # Person on plate, waiting for stability
    PHASE_CALIBRATING = 2  # Countdown for bodyweight measurement
    PHASE_READY = 3      # Bodyweight measured, ready for jump
    PHASE_COMPLETED = 4  # Jump completed, analyzing
    
    def __init__(self, calibration_duration=3):
        """
        Initialize calibration manager.
        
        Args:
            calibration_duration: Duration of calibration period in seconds (default 3)
        """
        super().__init__()
        
        self._calibration_duration = calibration_duration
        self._significant_force_threshold = 200  # N - person stepped on plate
        
        # State variables
        self.test_phase = self.PHASE_WAITING
        self._calibration_start_time = None
        self._calibration_force_buffer = []
        self._stability_buffer = []  # Buffer for stability detection before calibration
        
        # Results
        self._estimated_body_weight = None
        self._bw_calibration_std = None  # Store standard deviation of calibration data
        self._calibration_complete_time = None
        self._calibration_complete_index = None
        
    def reset(self):
        """Reset calibration state to initial values."""
        self.test_phase = self.PHASE_WAITING
        self._calibration_start_time = None
        self._calibration_force_buffer = []
        self._stability_buffer = []
        self._estimated_body_weight = None
        self._bw_calibration_std = None
        self._calibration_complete_time = None
        self._calibration_complete_index = None
        
        self.calibration_status_signal.emit("Step on the force plate", 0)
        
    def process_chunk(self, time_chunk, fz_chunk_summed, current_buffer_length):
        """
        Process a chunk of summed force data for calibration.
        
        Args:
            time_chunk: 1D array of timestamps
            fz_chunk_summed: 1D array of summed force values
            current_buffer_length: Current total length of the data buffer
            
        Returns:
            bool: True if calibration phase changed, False otherwise
        """
        phase_changed = False
        mean_force = np.mean(fz_chunk_summed)
        
        # STATE: Waiting for person to step on the plate
        if self.test_phase == self.PHASE_WAITING:
            if mean_force > self._significant_force_threshold:
                # Person stepped on the plate - wait for stability before starting timer
                self.test_phase = self.PHASE_WAITING_FOR_STABILITY
                self._stability_buffer = [fz_chunk_summed]
                self.status_signal.emit("Person detected on force plate. Please stand still.")
                self.calibration_status_signal.emit("Stand still to begin calibration", 0)
                phase_changed = True
                
        # STATE: Waiting for person to stabilize before starting calibration timer
        elif self.test_phase == self.PHASE_WAITING_FOR_STABILITY:
            # Check if person is still on the plate
            if mean_force < self._significant_force_threshold:
                # Person stepped off - go back to waiting
                self.test_phase = self.PHASE_WAITING
                self._stability_buffer = []
                self.status_signal.emit("Person stepped off. Step on the plate to begin.")
                self.calibration_status_signal.emit("Step on force plate to begin test", 0)
                phase_changed = True
            else:
                # Add to stability buffer
                self._stability_buffer.append(fz_chunk_summed)
                
                # Check for stability once we have enough data
                if len(self._stability_buffer) >= 3:  # Need at least 3 chunks (~100ms) for stability check
                    # Keep only recent data for stability analysis
                    recent_data = np.concatenate(self._stability_buffer[-10:]) if len(self._stability_buffer) > 10 else np.concatenate(self._stability_buffer)
                    std_dev = np.std(recent_data)
                    
                    if std_dev <= 10:  # Person is stable - start calibration timer
                        self.test_phase = self.PHASE_CALIBRATING
                        self._calibration_start_time = time_chunk[-1]
                        self._calibration_force_buffer = []
                        self.status_signal.emit("Stability detected. Starting bodyweight calibration.")
                        self.calibration_status_signal.emit("Stand still for calibration", self._calibration_duration)
                        phase_changed = True
                    else:
                        # Still unstable - keep waiting
                        self.calibration_status_signal.emit("Stand still to begin calibration", 0)
        
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
                    return False
            
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
                self._calibration_complete_index = current_buffer_length - 1  # Index of the last sample in buffer
                
                self.status_signal.emit(f"Bodyweight calibration complete: {self._estimated_body_weight:.1f}N")
                self.calibration_status_signal.emit("Ready to jump!", 0)
                self.calibration_complete_signal.emit(self._estimated_body_weight)
                
                # Move to ready state
                self.test_phase = self.PHASE_READY
                self.status_signal.emit("Ready for jump. Perform your jump now!")
                phase_changed = True
        
        # STATE: Ready for jump (handled by jump detector)
        elif self.test_phase == self.PHASE_READY:
            pass  # Jump detection happens elsewhere
            
        # STATE: Completed - waiting for person to step off
        elif self.test_phase == self.PHASE_COMPLETED:
            # Check if person stepped off the plate to get ready for next test
            if mean_force < self._significant_force_threshold:
                # Reset for the next test
                self.test_phase = self.PHASE_WAITING
                self.status_signal.emit("Ready for next person. Step on the plate to begin.")
                self.calibration_status_signal.emit("Step on force plate to begin test", 0)
                phase_changed = True
                
        return phase_changed
        
    def is_ready_for_jump(self):
        """Check if calibration is complete and ready for jump detection."""
        return (self.test_phase == self.PHASE_READY and 
                self._estimated_body_weight is not None and 
                self._estimated_body_weight > 100)
                
    def set_completed(self):
        """Mark the test as completed after a jump."""
        self.test_phase = self.PHASE_COMPLETED
        
    def get_bodyweight(self):
        """Get the calibrated bodyweight value."""
        return self._estimated_body_weight
        
    def get_calibration_std(self):
        """Get the standard deviation from calibration for threshold calculations."""
        return self._bw_calibration_std
        
    def get_calibration_complete_time(self):
        """Get the timestamp when calibration was completed."""
        return self._calibration_complete_time
        
    def get_calibration_complete_index(self):
        """Get the buffer index when calibration was completed."""
        return self._calibration_complete_index