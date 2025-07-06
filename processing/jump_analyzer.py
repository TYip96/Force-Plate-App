"""
Post-jump analysis of force plate data.
Performs detailed analysis including filtering, event detection, and metrics calculation.
"""
import numpy as np
from scipy.signal import butter, filtfilt
from PyQt6.QtCore import QObject, pyqtSignal
import config


class JumpAnalyzer(QObject):
    """
    Performs detailed analysis of jump segments after detection.
    Calculates metrics like flight time, jump height, peak forces, etc.
    """
    
    # Signals
    analysis_complete_signal = pyqtSignal(dict)  # Dictionary of calculated metrics
    jump_event_markers_signal = pyqtSignal(dict)  # Dictionary with event times and forces
    status_signal = pyqtSignal(str)
    
    def __init__(self, sample_rate):
        """
        Initialize jump analyzer.
        
        Args:
            sample_rate: Sampling rate in Hz
        """
        super().__init__()
        
        self.sample_rate = sample_rate
        
        # Butterworth filter parameters
        nyquist = self.sample_rate / 2.0
        fc = min(config.FILTER_CUTOFF, nyquist * 0.99)
        self._filter_b, self._filter_a = butter(
            config.FILTER_ORDER,
            fc,
            btype='low',
            analog=False,
            fs=self.sample_rate
        )
        
        # Interpolation results for precise timing
        self._takeoff_idx_precise = None
        self._landing_idx_precise = None
        self._flight_time_precise = None
        
    def analyze_jump_segment(self, time_data_absolute, fz_data, jump_number, 
                           body_weight_n, calibration_std, calibration_complete_time):
        """
        Performs analysis on a specific segment of SUMMED Fz data representing one jump.
        
        Args:
            time_data_absolute: 1D array of timestamps
            fz_data: 1D array of summed force data
            jump_number: Jump number for labeling
            body_weight_n: Calibrated bodyweight in N
            calibration_std: Standard deviation from calibration
            calibration_complete_time: Time when calibration was completed
            
        Returns:
            dict: Analysis results with metrics
        """
        results = {
            f'Jump #{jump_number} Body Weight (N)': 'N/A',
            f'Jump #{jump_number} Peak Propulsive Force (N)': 0,
            f'Jump #{jump_number} Peak Braking Force (N)': 0,
            f'Jump #{jump_number} Flight Time (s)': 0,
            f'Jump #{jump_number} Jump Height (Flight Time) (m)': 0,
            f'Jump #{jump_number} Jump Height (Impulse) (m)': 0,
            f'Jump #{jump_number} Analysis Note': ''
        }
        
        # Initialize critical variables
        movement_start_idx_abs = 0
        first_takeoff_idx = None
        first_landing_idx = 0
        
        if (time_data_absolute is None or fz_data is None or 
            len(time_data_absolute) < config.MIN_CONTACT_SAMPLES + config.MIN_FLIGHT_SAMPLES):
            note = "Not enough data for analysis."
            results[f'Jump #{jump_number} Analysis Note'] = note
            
            # Clean up keys for failed analysis
            keys_to_remove = [k for k in results if k != f'Jump #{jump_number} Analysis Note']
            for k in keys_to_remove:
                del results[k]
            return results
            
        try:
            # 1. Filter the Force Data
            fz_filtered = filtfilt(self._filter_b, self._filter_a, fz_data)
            
            # 2. Use provided bodyweight
            results[f'Jump #{jump_number} Body Weight (N)'] = round(body_weight_n, 2)
            
            # 3. Detect Flight Events
            flight_threshold = max(config.BODYWEIGHT_THRESHOLD_N, body_weight_n * 0.2)
            takeoff_indices, landing_indices = self._find_flight_phases(fz_data, fz_filtered, flight_threshold)
            
            flight_detected = takeoff_indices.size > 0 and landing_indices.size > 0
            
            if not flight_detected:
                # Try manual detection
                results[f'Jump #{jump_number} Analysis Note'] += " Incomplete/No flight phase. Searching manually..."
                takeoff_indices, landing_indices = self._manual_flight_detection(fz_filtered, flight_threshold)
                flight_detected = takeoff_indices.size > 0 and landing_indices.size > 0
                
            if flight_detected:
                # Analyze the first valid jump
                first_takeoff_idx = takeoff_indices[0]
                valid_landing_indices = landing_indices[landing_indices > first_takeoff_idx]
                
                if valid_landing_indices.size == 0:
                    results[f'Jump #{jump_number} Analysis Note'] += " Takeoff no landing."
                else:
                    first_landing_idx = valid_landing_indices[0]
                    
                    # Calculate peak forces
                    propulsive_peak = np.max(fz_data[:first_takeoff_idx]) if first_takeoff_idx > 0 else 0.0
                    
                    # Braking window calculation
                    braking_window_samples = self._find_time_window_samples(time_data_absolute, 0.5)
                    braking_end_idx = min(first_landing_idx + braking_window_samples, len(fz_data))
                    braking_peak = np.max(fz_data[first_landing_idx:braking_end_idx]) if first_landing_idx < braking_end_idx else 0.0
                    
                    results[f'Jump #{jump_number} Peak Propulsive Force (N)'] = round(propulsive_peak, 2)
                    results[f'Jump #{jump_number} Peak Braking Force (N)'] = round(braking_peak, 2)
                    
                    # Calculate flight time using precise interpolation
                    flight_time = self._calculate_flight_time(time_data_absolute, first_takeoff_idx, first_landing_idx)
                    
                    if flight_time < config.MIN_FLIGHT_TIME or flight_time > config.MAX_FLIGHT_TIME:
                        self.status_signal.emit(f"NOTICE: Flight time {flight_time:.3f}s outside expected range")
                        results[f'Jump #{jump_number} Analysis Note'] += " Flight time outside typical range."
                        
                    results[f'Jump #{jump_number} Flight Time (s)'] = round(flight_time, 3)
                    jump_height_m = (config.GRAVITY * flight_time**2) / 8.0
                    results[f'Jump #{jump_number} Jump Height (Flight Time) (m)'] = round(jump_height_m, 3)
                    
                    # Calculate impulse-based jump height
                    impulse_results = self._calculate_impulse_height(
                        time_data_absolute, fz_filtered, first_takeoff_idx,
                        body_weight_n, calibration_std, calibration_complete_time, jump_number
                    )
                    
                    if impulse_results:
                        results.update(impulse_results)
                        
                    # Find movement start for event markers
                    movement_start_idx_abs = self._find_movement_start(
                        fz_filtered, first_takeoff_idx, body_weight_n, 
                        calibration_std, calibration_complete_time, time_data_absolute
                    )
                    
                    # Emit event markers
                    self._emit_event_markers(
                        time_data_absolute, fz_filtered, jump_number,
                        movement_start_idx_abs, first_takeoff_idx, first_landing_idx
                    )
                    
            # Clean up note
            final_note = results[f'Jump #{jump_number} Analysis Note'].strip()
            if not final_note:
                del results[f'Jump #{jump_number} Analysis Note']
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
        """
        Identifies start (takeoff) and end (landing) indices of flight phases.
        Uses unfiltered data for 20N threshold crossings and filtered data for 50N anchor points.
        """
        flight_threshold = config.BODYWEIGHT_THRESHOLD_N  # 20N for precise flight detection
        transition_threshold = 50.0  # 50N for reliable transition detection
        
        # Find takeoff: first point where unfiltered force crosses below 20N
        takeoff_idx = -1
        for i in range(1, len(fz_data)):
            if fz_data[i-1] >= flight_threshold and fz_data[i] < flight_threshold:
                takeoff_idx = i
                break
                
        if takeoff_idx == -1:
            return np.array([]), np.array([])
            
        # Find landing: filtered 50N crossing then backward search for unfiltered 20N
        landing_50N_crossings = []
        for i in range(takeoff_idx + 1, len(fz_filtered)):
            if fz_filtered[i-1] < transition_threshold and fz_filtered[i] >= transition_threshold:
                landing_50N_crossings.append(i)
                break
                
        if not landing_50N_crossings:
            self._interpolate_takeoff(fz_data, takeoff_idx, flight_threshold)
            return np.array([takeoff_idx]), np.array([])
            
        idx_50N_up = landing_50N_crossings[0]
        
        # Search backward for 20N crossing
        search_window_samples = min(int(0.2 * self.sample_rate), idx_50N_up - takeoff_idx)
        min_gap_samples = int(0.05 * self.sample_rate)
        search_start = max(takeoff_idx + min_gap_samples, idx_50N_up - search_window_samples)
        
        landing_idx = idx_50N_up
        found_5N_landing_crossing = False
        
        for i in range(idx_50N_up, search_start, -1):
            if i > 0 and i < len(fz_data):
                if fz_data[i-1] < flight_threshold and fz_data[i] >= flight_threshold:
                    landing_idx = i
                    found_5N_landing_crossing = True
                    break
                    
        # Perform interpolation for precise timing
        self._interpolate_takeoff(fz_data, takeoff_idx, flight_threshold)
        self._interpolate_landing(fz_data, landing_idx, flight_threshold, found_5N_landing_crossing)
        
        return np.array([takeoff_idx]), np.array([landing_idx])
        
    def _manual_flight_detection(self, fz_filtered, flight_threshold):
        """Manual detection when automatic detection fails."""
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
            self.status_signal.emit(f"Manual flight detection successful")
            return takeoff_indices, landing_indices
            
        return np.array([]), np.array([])
        
    def _interpolate_takeoff(self, fz_data, takeoff_idx, flight_threshold):
        """Interpolates the precise takeoff index using unfiltered data."""
        if takeoff_idx > 0 and takeoff_idx < len(fz_data):
            force_before = fz_data[takeoff_idx-1]
            force_after = fz_data[takeoff_idx]
            
            if force_before != force_after:
                interp_fraction = (force_before - flight_threshold) / (force_before - force_after)
                self._takeoff_idx_precise = (takeoff_idx - 1) + interp_fraction
            else:
                self._takeoff_idx_precise = float(takeoff_idx)
        else:
            self._takeoff_idx_precise = float(takeoff_idx)
            
    def _interpolate_landing(self, fz_data, landing_idx, flight_threshold, found_5N_crossing):
        """Interpolates the precise landing index using unfiltered data."""
        if found_5N_crossing and landing_idx > 0 and landing_idx < len(fz_data):
            force_before = fz_data[landing_idx-1]
            force_after = fz_data[landing_idx]
            
            if force_after != force_before:
                interp_fraction = (flight_threshold - force_before) / (force_after - force_before)
                self._landing_idx_precise = (landing_idx - 1) + interp_fraction
            else:
                self._landing_idx_precise = float(landing_idx)
        else:
            self._landing_idx_precise = float(landing_idx)
            
    def _calculate_flight_time(self, time_data_absolute, takeoff_idx, landing_idx):
        """Calculate precise flight time using interpolated indices and wall-clock timing."""
        if hasattr(self, '_takeoff_idx_precise') and self._takeoff_idx_precise >= 0:
            takeoff_time = self._interpolated_index_to_wallclock_time(
                self._takeoff_idx_precise, time_data_absolute
            )
        else:
            takeoff_time = time_data_absolute[takeoff_idx]
            
        if hasattr(self, '_landing_idx_precise') and self._landing_idx_precise >= 0:
            landing_time = self._interpolated_index_to_wallclock_time(
                self._landing_idx_precise, time_data_absolute
            )
        else:
            landing_time = time_data_absolute[landing_idx]
            
        return landing_time - takeoff_time
        
    def _interpolated_index_to_wallclock_time(self, interpolated_index, time_data):
        """Convert an interpolated index to wall-clock time using actual timestamps."""
        if time_data is None or len(time_data) == 0:
            return None
            
        if interpolated_index < 0 or interpolated_index >= len(time_data):
            return None
            
        index_floor = int(interpolated_index)
        index_frac = interpolated_index - index_floor
        
        if index_floor >= len(time_data) - 1:
            return time_data[-1]
        if index_floor < 0:
            return time_data[0]
            
        time_before = time_data[index_floor]
        time_after = time_data[index_floor + 1]
        interpolated_time = time_before + index_frac * (time_after - time_before)
        
        return interpolated_time
        
    def _find_time_window_samples(self, time_array, duration_seconds):
        """Find the number of samples that corresponds to a given time duration."""
        if len(time_array) < 2:
            return int(duration_seconds * self.sample_rate)
            
        total_time_span = time_array[-1] - time_array[0]
        total_samples = len(time_array)
        
        effective_rate = total_samples / total_time_span if total_time_span > 0 else self.sample_rate
        
        return int(duration_seconds * effective_rate)
        
    def _find_movement_start(self, fz_filtered, first_takeoff_idx, body_weight_n, 
                           calibration_std, calibration_complete_time, time_data_absolute):
        """Find the start of countermovement for impulse calculation."""
        if first_takeoff_idx is None or first_takeoff_idx < 10:
            return 0
            
        search_range_onset = fz_filtered[:first_takeoff_idx]
        
        if len(search_range_onset) < 10:
            return 0
            
        # Default to 10% if we don't have calibration time
        search_start_idx = int(len(search_range_onset) * 0.1)
        
        # Use calibration completion time if available
        if calibration_complete_time is not None and len(time_data_absolute) > 0:
            segment_start_time = time_data_absolute[0]
            rel_calib_time = calibration_complete_time - segment_start_time
            
            if rel_calib_time > 0:
                calib_idx = np.abs(time_data_absolute - (segment_start_time + rel_calib_time)).argmin()
                buffer_samples = self._find_time_window_samples(time_data_absolute, 0.1)
                search_start_idx = min(calib_idx + buffer_samples, len(search_range_onset) - 1)
            else:
                search_start_idx = 0
                
        # Use 5 SD threshold
        SD_MULTIPLIER = 5
        if calibration_std is None:
            calibration_std = 5.0  # Fallback
            
        movement_threshold = body_weight_n - (SD_MULTIPLIER * calibration_std)
        
        # Find first point where force drops below threshold
        movement_start_idx = search_start_idx
        movement_found = False
        
        for i in range(search_start_idx, len(search_range_onset)):
            if search_range_onset[i] < movement_threshold:
                movement_start_idx = i
                movement_found = True
                break
                
        if movement_found:
            # Search backward to find BW crossing
            for i in range(movement_start_idx, search_start_idx, -1):
                if i > 0:
                    if ((search_range_onset[i] <= body_weight_n and search_range_onset[i-1] > body_weight_n) or 
                        (search_range_onset[i] >= body_weight_n and search_range_onset[i-1] < body_weight_n)):
                        movement_start_idx = i
                        break
                        
        return movement_start_idx
        
    def _calculate_impulse_height(self, time_data_absolute, fz_filtered, first_takeoff_idx,
                                body_weight_n, calibration_std, calibration_complete_time, jump_number):
        """Calculate jump height using impulse method."""
        results = {}
        
        movement_start_idx = self._find_movement_start(
            fz_filtered, first_takeoff_idx, body_weight_n,
            calibration_std, calibration_complete_time, time_data_absolute
        )
        
        if first_takeoff_idx is None or first_takeoff_idx < 10:
            return results
            
        # Get movement force and time
        full_movement_force = fz_filtered[movement_start_idx:first_takeoff_idx]
        full_movement_time = time_data_absolute[movement_start_idx:first_takeoff_idx]
        
        if len(full_movement_time) > 10 and body_weight_n > 0:
            mass = body_weight_n / config.GRAVITY
            net_force_full = full_movement_force - body_weight_n
            
            # Calculate total net impulse
            net_impulse = np.trapz(net_force_full, full_movement_time)
            
            # Calculate takeoff velocity
            takeoff_velocity = net_impulse / mass
            
            # Calculate jump height
            jump_height_impulse_m = (takeoff_velocity**2) / (2 * config.GRAVITY)
            
            # Add appropriate keys based on the jump number
            results[f'Jump #{jump_number} Jump Height (Impulse) (m)'] = round(jump_height_impulse_m, 3)
            results[f'Jump #{jump_number} Net Impulse (Ns)'] = round(net_impulse, 2)
            
        return results
        
    def _emit_event_markers(self, time_data_absolute, fz_filtered, jump_number,
                          movement_start_idx_abs, first_takeoff_idx, first_landing_idx):
        """Emit event markers for visualization."""
        if (time_data_absolute is None or len(time_data_absolute) == 0 or 
            movement_start_idx_abs >= len(time_data_absolute) or 
            first_takeoff_idx is None or first_takeoff_idx >= len(time_data_absolute) or
            first_landing_idx >= len(time_data_absolute)):
            return
            
        # Get exact event times
        jump_start_time = time_data_absolute[movement_start_idx_abs]
        jump_start_force = fz_filtered[movement_start_idx_abs]
        
        # Use precise interpolated values if available
        if hasattr(self, '_takeoff_idx_precise') and self._takeoff_idx_precise >= 0:
            takeoff_time = self._interpolated_index_to_wallclock_time(
                self._takeoff_idx_precise, time_data_absolute
            )
            takeoff_force = config.BODYWEIGHT_THRESHOLD_N
        else:
            takeoff_time = time_data_absolute[first_takeoff_idx]
            takeoff_force = fz_filtered[first_takeoff_idx]
            
        if hasattr(self, '_landing_idx_precise') and self._landing_idx_precise > 0:
            landing_time = self._interpolated_index_to_wallclock_time(
                self._landing_idx_precise, time_data_absolute
            )
            landing_force = config.BODYWEIGHT_THRESHOLD_N
        else:
            landing_time = time_data_absolute[first_landing_idx]
            landing_force = fz_filtered[first_landing_idx]
            
        # Create event markers dictionary
        event_markers = {
            'jump_number': jump_number,
            'jump_start_time': jump_start_time,
            'jump_start_force': jump_start_force,
            'takeoff_time': takeoff_time,
            'takeoff_force': takeoff_force,
            'landing_time': landing_time,
            'landing_force': landing_force
        }
        
        # Emit the markers
        self.jump_event_markers_signal.emit(event_markers)