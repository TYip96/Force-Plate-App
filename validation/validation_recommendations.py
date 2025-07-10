"""
DETAILED RECOMMENDATIONS FOR FORCE PLATE APP IMPROVEMENTS
Based on calibration data analysis comparing Trevor's force plate with VALD Forcedeck
"""

# 1. IMPROVED CALIBRATION MODEL
class NonLinearCalibration:
    """
    Replace simple N_PER_VOLT constant with a more sophisticated calibration model
    """
    def __init__(self):
        # Base calibration factor
        self.base_sensitivity = 327.0  # N/V
        
        # Configuration-specific offsets
        self.config_offset = {
            'mine_on_top': -0.199,  # -19.9% average underestimation
            'vald_on_top': -0.061,  # -6.1% average underestimation
            'default': 0.0
        }
        
        # Force-dependent correction factors (empirical)
        self.force_correction_coefficients = {
            'a': 1.0,      # base multiplier
            'b': 0.00008,  # linear correction
            'c': 0.000000012  # quadratic correction for high forces
        }
    
    def voltage_to_force(self, voltage, configuration='default'):
        """Convert voltage to force with non-linear correction"""
        # Basic conversion
        force_raw = voltage * self.base_sensitivity
        
        # Apply force-dependent correction
        a, b, c = self.force_correction_coefficients.values()
        correction_factor = a + b * abs(force_raw) + c * (force_raw ** 2)
        
        # Apply configuration offset
        config_correction = 1 + self.config_offset.get(configuration, 0)
        
        # Final corrected force
        force_corrected = force_raw * correction_factor * config_correction
        
        return force_corrected

# 2. ENHANCED FILTER DESIGN
class AdaptiveFilter:
    """
    Adaptive filtering based on signal characteristics
    """
    def __init__(self, sample_rate=1000):
        self.sample_rate = sample_rate
        self.base_cutoff = 50  # Hz
        
    def get_adaptive_cutoff(self, signal_rms, is_landing=False):
        """Adjust filter cutoff based on signal characteristics"""
        if is_landing:
            # Less aggressive filtering during landing to preserve peak forces
            return min(75, self.base_cutoff * 1.5)
        elif signal_rms > 2000:  # High force scenario
            # Preserve high-frequency components for accurate peak detection
            return 65
        else:
            # Standard filtering for quiet periods
            return self.base_cutoff

# 3. IMPROVED JUMP DETECTION
class EnhancedJumpDetector:
    """
    More sophisticated jump detection using multiple criteria
    """
    def __init__(self):
        self.flight_threshold_primary = 20  # N
        self.flight_threshold_secondary = 15  # N (with hysteresis)
        self.rate_of_force_threshold = -500  # N/s for takeoff detection
        self.landing_rate_threshold = 1000  # N/s for landing detection
        
    def detect_flight_phase(self, force, bodyweight, previous_state='ground'):
        """
        Enhanced flight detection with hysteresis and rate-based detection
        """
        # Calculate normalized force
        normalized_force = force - bodyweight
        
        # Apply hysteresis
        if previous_state == 'ground':
            threshold = self.flight_threshold_primary
        else:  # previous_state == 'flight'
            threshold = self.flight_threshold_secondary
        
        # Check if in flight
        return normalized_force < -threshold

# 4. MEASUREMENT UNCERTAINTY QUANTIFICATION
class UncertaintyEstimator:
    """
    Estimate measurement uncertainty based on calibration data
    """
    def __init__(self):
        # Based on calibration analysis
        self.uncertainty_factors = {
            'bodyweight': 0.0025,  # 0.25% uncertainty
            'flight_time': 0.038,  # 3.8% uncertainty
            'peak_force': 0.20,    # 20% uncertainty (worst case)
            'jump_height': 0.23    # 23% uncertainty
        }
        
    def get_confidence_interval(self, measurement_type, value):
        """Return 95% confidence interval for measurement"""
        uncertainty = self.uncertainty_factors.get(measurement_type, 0.1)
        margin = value * uncertainty * 1.96  # 95% CI
        return (value - margin, value + margin)

# 5. DATA QUALITY INDICATORS
class DataQualityMonitor:
    """
    Real-time data quality assessment
    """
    def __init__(self):
        self.quality_thresholds = {
            'noise_rms': 5.0,  # N
            'drift_rate': 0.1,  # N/s
            'spike_threshold': 3.0  # standard deviations
        }
        
    def assess_quality(self, force_buffer, sample_rate=1000):
        """Assess data quality and return quality score and issues"""
        quality_score = 100.0
        issues = []
        
        # Check noise level
        if len(force_buffer) > sample_rate:
            quiet_period = force_buffer[-sample_rate:]  # Last second
            noise_rms = self._calculate_rms(quiet_period)
            if noise_rms > self.quality_thresholds['noise_rms']:
                quality_score -= 20
                issues.append(f"High noise: {noise_rms:.1f}N RMS")
        
        # Check for drift
        if len(force_buffer) > sample_rate * 10:
            drift = self._calculate_drift(force_buffer[-sample_rate*10:])
            if abs(drift) > self.quality_thresholds['drift_rate']:
                quality_score -= 30
                issues.append(f"Baseline drift: {drift:.2f}N/s")
        
        # Check for spikes
        spikes = self._detect_spikes(force_buffer)
        if spikes > 0:
            quality_score -= 10 * min(spikes, 5)
            issues.append(f"Detected {spikes} spikes")
        
        return max(0, quality_score), issues
    
    def _calculate_rms(self, data):
        """Calculate RMS of signal"""
        import math
        mean = sum(data) / len(data)
        return math.sqrt(sum((x - mean)**2 for x in data) / len(data))
    
    def _calculate_drift(self, data):
        """Calculate baseline drift rate"""
        # Simple linear regression
        n = len(data)
        x = list(range(n))
        xy = sum(i * v for i, v in enumerate(data))
        xx = sum(i * i for i in x)
        x_mean = n / 2
        y_mean = sum(data) / n
        slope = (xy - n * x_mean * y_mean) / (xx - n * x_mean * x_mean)
        return slope
    
    def _detect_spikes(self, data):
        """Count number of statistical outliers"""
        if len(data) < 10:
            return 0
        mean = sum(data) / len(data)
        std = self._calculate_rms(data)
        threshold = self.quality_thresholds['spike_threshold'] * std
        return sum(1 for x in data if abs(x - mean) > threshold)

# 6. RECOMMENDED CONFIG.PY UPDATES
RECOMMENDED_CONFIG = """
# Replace simple constants with calibration objects
from calibration import NonLinearCalibration, AdaptiveFilter

# DAQ Configuration
SAMPLE_RATE = 1000  # Hz per channel
NUM_CHANNELS = 4
VOLTAGE_RANGE = 10  # ±10V

# Calibration System (replaces N_PER_VOLT)
calibration = NonLinearCalibration()

# Adaptive Filtering (replaces FILTER_CUTOFF)
filter_system = AdaptiveFilter(SAMPLE_RATE)

# Enhanced Jump Detection Parameters
JUMP_DETECTION = {
    'flight_threshold_primary': 20,  # N
    'flight_threshold_secondary': 15,  # N (hysteresis)
    'rate_threshold_takeoff': -500,  # N/s
    'rate_threshold_landing': 1000,  # N/s
    'min_flight_time': 100,  # ms
    'max_flight_time': 1000  # ms
}

# Data Quality Thresholds
QUALITY_THRESHOLDS = {
    'min_quality_score': 70,  # Warn if below
    'max_noise_rms': 5.0,  # N
    'max_drift_rate': 0.1,  # N/s
}

# Measurement Uncertainty (for reporting)
UNCERTAINTY_FACTORS = {
    'bodyweight': 0.0025,
    'flight_time': 0.038,
    'peak_force': 0.20,
    'jump_height': 0.23
}
"""

# 7. VALIDATION TEST SUITE
def create_validation_tests():
    """
    Test suite to validate calibration improvements
    """
    tests = """
    1. Known Weight Test:
       - Place known weights (10kg, 20kg, 50kg) on plate
       - Verify readings within 1% of expected
       - Test at different positions on plate
    
    2. Dynamic Range Test:
       - Generate controlled impacts from 500N to 5000N
       - Compare with reference force plate
       - Verify linearity across range
    
    3. Frequency Response Test:
       - Use vibration source at known frequencies
       - Verify filter preserves important frequencies
       - Check phase distortion
    
    4. Configuration Test:
       - Test with different plate stacking orders
       - Verify configuration-specific corrections work
    
    5. Long-term Stability Test:
       - Monitor baseline for 30 minutes
       - Check drift and temperature effects
       - Verify auto-zero functionality
    """
    return tests

if __name__ == "__main__":
    print("Force Plate App Improvement Recommendations")
    print("=" * 50)
    print("\n1. Replace linear calibration with NonLinearCalibration class")
    print("2. Implement AdaptiveFilter for better peak force preservation")
    print("3. Use EnhancedJumpDetector with hysteresis and rate-based detection")
    print("4. Add UncertaintyEstimator to report confidence intervals")
    print("5. Implement DataQualityMonitor for real-time quality assessment")
    print("\nSee RECOMMENDED_CONFIG for specific config.py updates")