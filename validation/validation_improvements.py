"""
SPECIFIC CODE IMPROVEMENTS FOR FORCE PLATE APP
Based on calibration data analysis showing:
- 19.9% average force underestimation when Trevor's plate on top
- High variability in jump height calculations (up to 43% error)
- Good timing accuracy (<8% error)
- Excellent bodyweight calibration (<0.25% error)
"""

# ==========================================
# 1. IMPROVED CONFIG.PY
# ==========================================
IMPROVED_CONFIG = """
# Configuration constants for the Force Plate App
from mcculw.enums import AnalogInputMode, ULRange
import numpy as np

# DAQ Settings
SAMPLE_RATE = 1000  # Hz per channel
NUM_CHANNELS = 4     # Number of analog input channels to scan
DAQ_READ_CHUNK_SIZE = 33 # Samples per channel per chunk (~33ms @1kHz → ~30 callbacks/s)
BOARD_NUM = 0        # DAQ board number (e.g., for mcculw)
MCC_INPUT_MODE = AnalogInputMode.DIFFERENTIAL
MCC_VOLTAGE_RANGE = ULRange.BIP10VOLTS

# Basic Calibration - keeping for backward compatibility
N_PER_VOLT = 327.0 # N/V per channel (base sensitivity)

# Non-linear Calibration Parameters
CALIBRATION_PARAMS = {
    'base_sensitivity': 327.0,  # N/V
    'force_correction': {
        'linear': 0.00008,      # Linear correction coefficient
        'quadratic': 1.2e-8,    # Quadratic correction for high forces
        'offset': 0.199         # 19.9% correction factor based on calibration data
    },
    'filter_adaptation': {
        'landing_cutoff': 75,   # Hz - Less aggressive during landing
        'quiet_cutoff': 50,     # Hz - Standard filtering
        'high_force_cutoff': 65 # Hz - For forces > 2000N
    }
}

# Enhanced Jump Detection Parameters
JUMP_DETECTION = {
    'flight_threshold_primary': 20,    # N - Initial flight detection
    'flight_threshold_secondary': 15,  # N - Hysteresis threshold
    'rate_threshold_takeoff': -500,    # N/s - Rate of force change for takeoff
    'rate_threshold_landing': 1000,    # N/s - Rate of force change for landing
    'min_quiet_time': 0.5,            # s - Minimum time before detecting new jump
}

# Data Quality Thresholds
QUALITY_THRESHOLDS = {
    'max_noise_rms': 5.0,     # N - Maximum acceptable noise
    'max_drift_rate': 0.1,    # N/s - Maximum baseline drift
    'spike_threshold': 3.0,    # Standard deviations for spike detection
    'min_quality_score': 70   # Minimum quality score to proceed
}

# Measurement Uncertainty (based on calibration analysis)
UNCERTAINTY_FACTORS = {
    'bodyweight': 0.0025,     # 0.25% - Excellent
    'flight_time': 0.038,     # 3.8% - Good
    'peak_force': 0.20,       # 20% - Needs improvement
    'jump_height': 0.23,      # 23% - Needs improvement
    'contraction_time': 0.025 # 2.5% - Good
}

# Analysis Settings (enhanced)
GRAVITY = 9.81 # m/s^2
FILTER_ORDER = 4
FILTER_CUTOFF = 50 # Hz - Default, but now adaptive
BODYWEIGHT_THRESHOLD_N = 20.0 # Consistent 20N threshold for flight detection
FORCE_ONSET_THRESHOLD_FACTOR = 0.05 # Factor of peak force to determine movement onset
MIN_FLIGHT_SAMPLES = 20 # Minimum number of samples for a valid flight phase (20ms at 1000Hz)
MIN_CONTACT_SAMPLES = 10 # Minimum number of samples for stable contact detection
MIN_FLIGHT_TIME = 0.05 # Minimum flight time (50ms)
MAX_FLIGHT_TIME = 0.8 # Maximum reasonable flight time

# Plotting Settings
PLOT_WINDOW_DURATION_S = 5 # Show the last 5 seconds of data
PLOT_Y_AXIS_INITIAL_MAX = 3000.0 # Initial Y-axis maximum (N)
"""

# ==========================================
# 2. ENHANCED CALIBRATION FUNCTION
# ==========================================
def voltage_to_force_nonlinear(voltage, n_per_volt=327.0, force_correction=None):
    """
    Convert voltage to force with non-linear correction
    
    Args:
        voltage: Input voltage (V)
        n_per_volt: Base sensitivity (N/V)
        force_correction: Dictionary with correction parameters
        
    Returns:
        Corrected force in Newtons
    """
    if force_correction is None:
        # Use default correction based on calibration analysis
        force_correction = {
            'linear': 0.00008,
            'quadratic': 1.2e-8,
            'offset': 0.199
        }
    
    # Basic linear conversion
    force_raw = voltage * n_per_volt
    
    # Apply non-linear correction
    # Correction factor = 1 + linear*force + quadratic*force^2
    correction_factor = (1.0 + 
                        force_correction['linear'] * abs(force_raw) + 
                        force_correction['quadratic'] * (force_raw ** 2))
    
    # Apply systematic offset correction (19.9% underestimation)
    offset_correction = 1.0 + force_correction['offset']
    
    # Final corrected force
    force_corrected = force_raw * correction_factor * offset_correction
    
    return force_corrected

# ==========================================
# 3. MODIFIED DATA PROCESSOR CHUNK
# ==========================================
MODIFIED_PROCESS_CHUNK = """
# Replace lines 170-171 in data_processor.py process_data_chunk method:

# Original:
# force_data_channels = offset_corrected_data * self.n_per_volt

# New implementation with non-linear calibration:
force_data_channels = np.zeros_like(offset_corrected_data)
for ch in range(self.num_channels):
    for i in range(offset_corrected_data.shape[0]):
        force_data_channels[i, ch] = voltage_to_force_nonlinear(
            offset_corrected_data[i, ch],
            self.n_per_volt,
            config.CALIBRATION_PARAMS.get('force_correction', None)
        )
"""

# ==========================================
# 4. ADAPTIVE FILTER IMPLEMENTATION
# ==========================================
class AdaptiveFilter:
    """Adaptive filtering based on signal characteristics"""
    
    def __init__(self, sample_rate, filter_params):
        self.sample_rate = sample_rate
        self.filter_params = filter_params
        self.filters = {}
        
        # Pre-compute filters for different scenarios
        from scipy.signal import butter
        
        for scenario, cutoff in filter_params.items():
            nyquist = sample_rate / 2.0
            fc = min(cutoff, nyquist * 0.99)
            b, a = butter(4, fc, btype='low', analog=False, fs=sample_rate)
            self.filters[scenario] = (b, a)
    
    def filter_adaptive(self, data, force_rms=None, is_landing=False):
        """Apply adaptive filtering based on signal characteristics"""
        from scipy.signal import filtfilt
        
        if is_landing:
            b, a = self.filters['landing_cutoff']
        elif force_rms and force_rms > 2000:
            b, a = self.filters['high_force_cutoff']
        else:
            b, a = self.filters['quiet_cutoff']
        
        return filtfilt(b, a, data)

# ==========================================
# 5. DATA QUALITY MONITOR
# ==========================================
class DataQualityMonitor:
    """Monitor data quality in real-time"""
    
    def __init__(self, thresholds):
        self.thresholds = thresholds
        self.baseline_buffer = []
        self.quality_history = []
        
    def assess_quality(self, force_data, sample_rate=1000):
        """
        Assess data quality and return score with issues
        
        Returns:
            quality_score (0-100), list of issues
        """
        quality_score = 100.0
        issues = []
        
        # Check noise level
        if len(force_data) > sample_rate:
            noise_rms = np.std(force_data[-sample_rate:])
            if noise_rms > self.thresholds['max_noise_rms']:
                quality_score -= 20
                issues.append(f"High noise: {noise_rms:.1f}N RMS")
        
        # Check for drift
        if len(self.baseline_buffer) > 10 * sample_rate:
            baseline = np.array(self.baseline_buffer[-10*sample_rate:])
            drift_rate = np.polyfit(range(len(baseline)), baseline, 1)[0]
            if abs(drift_rate) > self.thresholds['max_drift_rate']:
                quality_score -= 30
                issues.append(f"Baseline drift: {drift_rate:.2f}N/s")
        
        # Check for spikes
        if len(force_data) > 10:
            mean = np.mean(force_data)
            std = np.std(force_data)
            spikes = np.sum(np.abs(force_data - mean) > self.thresholds['spike_threshold'] * std)
            if spikes > 0:
                quality_score -= min(50, 10 * spikes)
                issues.append(f"Detected {spikes} spikes")
        
        # Update baseline during quiet periods
        if len(force_data) > 0 and np.std(force_data) < self.thresholds['max_noise_rms']:
            self.baseline_buffer.extend(force_data.tolist())
            if len(self.baseline_buffer) > 30 * sample_rate:
                self.baseline_buffer = self.baseline_buffer[-30*sample_rate:]
        
        self.quality_history.append(quality_score)
        return max(0, quality_score), issues

# ==========================================
# 6. UNCERTAINTY REPORTING
# ==========================================
def add_uncertainty_to_results(results, uncertainty_factors):
    """
    Add confidence intervals to measurement results
    
    Args:
        results: Dictionary of jump metrics
        uncertainty_factors: Dictionary of uncertainty percentages
        
    Returns:
        Enhanced results dictionary with confidence intervals
    """
    enhanced_results = results.copy()
    
    # Add confidence intervals for key metrics
    if 'bodyweight' in results:
        bw = results['bodyweight']
        uncertainty = uncertainty_factors.get('bodyweight', 0.01)
        enhanced_results['bodyweight_ci'] = (
            bw * (1 - 1.96 * uncertainty),
            bw * (1 + 1.96 * uncertainty)
        )
    
    if 'flight_time' in results:
        ft = results['flight_time']
        uncertainty = uncertainty_factors.get('flight_time', 0.05)
        enhanced_results['flight_time_ci'] = (
            ft * (1 - 1.96 * uncertainty),
            ft * (1 + 1.96 * uncertainty)
        )
    
    if 'jump_height_ft' in results:
        jh = results['jump_height_ft']
        uncertainty = uncertainty_factors.get('jump_height', 0.25)
        enhanced_results['jump_height_ft_ci'] = (
            jh * (1 - 1.96 * uncertainty),
            jh * (1 + 1.96 * uncertainty)
        )
    
    if 'peak_landing_force' in results:
        plf = results['peak_landing_force']
        uncertainty = uncertainty_factors.get('peak_force', 0.20)
        enhanced_results['peak_landing_force_ci'] = (
            plf * (1 - 1.96 * uncertainty),
            plf * (1 + 1.96 * uncertainty)
        )
    
    # Add overall data quality score if available
    if hasattr(results, '_quality_score'):
        enhanced_results['data_quality_score'] = results._quality_score
    
    return enhanced_results

# ==========================================
# 7. IMPLEMENTATION GUIDE
# ==========================================
IMPLEMENTATION_STEPS = """
STEP-BY-STEP IMPLEMENTATION GUIDE:

1. BACKUP CURRENT FILES
   - config.py
   - processing/data_processor.py

2. UPDATE config.py
   - Add CALIBRATION_PARAMS dictionary
   - Add JUMP_DETECTION enhanced parameters
   - Add QUALITY_THRESHOLDS
   - Add UNCERTAINTY_FACTORS

3. MODIFY data_processor.py
   - Import numpy as np at top if not already
   - Replace linear force conversion (line ~171) with:
     ```python
     # Non-linear calibration
     force_data_channels = np.zeros_like(offset_corrected_data)
     force_correction = config.CALIBRATION_PARAMS.get('force_correction', None)
     for ch in range(self.num_channels):
         for i in range(offset_corrected_data.shape[0]):
             force_data_channels[i, ch] = voltage_to_force_nonlinear(
                 offset_corrected_data[i, ch],
                 self.n_per_volt,
                 force_correction
             )
     ```

4. ADD DATA QUALITY MONITORING (optional but recommended)
   - Add DataQualityMonitor instance in __init__
   - Call assess_quality in process_data_chunk
   - Emit quality warnings via status_signal

5. UPDATE RESULTS REPORTING
   - Modify analysis_complete_signal emission to include uncertainty
   - Update UI to show confidence intervals

6. TEST WITH KNOWN WEIGHTS
   - Place 10kg, 20kg, 50kg weights on plate
   - Verify readings are within 1% of expected
   - Check that peak forces are no longer underestimated

7. VALIDATE WITH JUMPS
   - Perform test jumps
   - Compare with previous data
   - Verify improved accuracy
"""

print("Force Plate Calibration Improvements Generated")
print("=" * 50)
print("Key files created:")
print("1. calibration_analysis_simple.py - Analysis results")
print("2. detailed_recommendations.py - Detailed recommendations")
print("3. calibration_improvements.py - This file with code changes")
print("\nRefer to IMPLEMENTATION_STEPS for applying changes")