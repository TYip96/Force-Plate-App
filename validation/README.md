# Force Plate Validation Analysis

This folder contains the validation analysis comparing Trevor's custom force plate against a VALD Forcedeck reference plate.

## Important Distinction

- **Calibration** (in main directory): Weight-based calibration to determine the 330.31 N/V conversion factor
- **Validation** (this folder): Performance comparison against a reference force plate during actual jumps

## Files in this folder:

### Data
- `force_plate_validation_data.csv` - Raw comparison data from jump tests

### Analysis Scripts
- `validation_analysis.py` - Main statistical analysis script
- `validation_analysis_corrected.py` - Analysis accounting for calibration factor differences

### Results & Recommendations
- `VALIDATION_SUMMARY.md` - Executive summary of findings
- `validation_recommendations.py` - Detailed technical recommendations
- `validation_improvements.py` - Specific code improvements for the app

## Key Findings

1. **Static calibration (330.31 N/V) is excellent** - R² = 0.999998 for known weights
2. **Dynamic peak forces are underestimated** - Up to 44% error during jump landings
3. **This suggests frequency-dependent response** - Different behavior for static vs impact loads

## Main Recommendation

Keep the existing weight-based calibration but add dynamic correction factors for high-rate loading during jumps.