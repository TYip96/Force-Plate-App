# Configuration constants for the Force Plate App
from mcculw.enums import AnalogInputMode, ULRange # Add imports

# DAQ Settings
SAMPLE_RATE = 1000  # Hz per channel
NUM_CHANNELS = 4     # Number of analog input channels to scan
DAQ_READ_CHUNK_SIZE = 500 # Samples per channel per chunk (~500ms @1kHz → ~2 callbacks/s, reduced from 33 to minimize timing jitter)
BOARD_NUM = 0        # DAQ board number (e.g., for mcculw)
# Use actual mcculw enums
MCC_INPUT_MODE = AnalogInputMode.DIFFERENTIAL
MCC_VOLTAGE_RANGE = ULRange.BIP10VOLTS

# Calibration
# Range: 0-333.333 kg per channel -> 0 - (333.333 * 9.81) N per channel = 3270 N per channel
# Voltage: 0-10 V per channel
# Sensitivity: 327.0 N/V per channel
N_PER_VOLT = 327.0 # N/V per channel

# Analysis Settings
GRAVITY = 9.81 # m/s^2
FILTER_ORDER = 4
FILTER_CUTOFF = 50 # Hz - Low-pass filter cutoff for force data (at Nyquist, will be clamped in processing)
BODYWEIGHT_THRESHOLD_N = 20.0 # Consistent 20N threshold for flight detection
FORCE_ONSET_THRESHOLD_FACTOR = 0.05 # Factor of peak force to determine movement onset (can be adjusted)
MIN_FLIGHT_SAMPLES = 20 # Minimum number of samples for a valid flight phase (20ms at 1000Hz)
MIN_CONTACT_SAMPLES = 10 # Minimum number of samples for stable contact detection (10ms at 1000Hz)
MIN_FLIGHT_TIME = 0.05 # Reduced minimum flight time (50ms) to include lower jumps and single-leg jumps
MAX_FLIGHT_TIME = 0.8 # Maximum reasonable flight time for typical jumps

# Buffer Settings
CONTINUOUS_BUFFER_SECONDS = 10  # Size of circular buffer for continuous acquisition (seconds)
TIMING_JITTER_THRESHOLD_MS = 5.0  # Threshold for detecting timing jitter (milliseconds)

# Plotting Settings
PLOT_WINDOW_DURATION_S = 5 # Show the last 5 seconds of data on the live plot 

# Initial Y-axis maximum for live plot (N)
PLOT_Y_AXIS_INITIAL_MAX = 3000.0 # Increased for better scaling with higher force values 