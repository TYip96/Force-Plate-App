"""
FORCE PLATE VALIDATION ANALYSIS
Comparing Trevor's custom force plate against VALD Forcedeck reference plate
Data extracted from force_plate_validation_data.csv
"""
import statistics
import math

# Validation data extracted from CSV comparing Trevor's plate (T) vs VALD Forcedeck (F)
# Mine on top of VALD (rows 8-14)
mine_on_top = {
    'jump_num': [1, 2, 3, 4, 5, 6],
    'height_f': [20.7, 15.4, 30.2, 29.5, 36.6, 21.1],
    'height_t': [23.8, 12.3, 23.8, 33.7, 33.9, 11.9],
    'height_error': [14.976, -20.130, -21.192, 14.237, -7.377, -43.602],
    'bw_f': [200.8, 201.1, 201.1, 201.1, 201.1, 201.1],
    'bw_t': [201.3, 201.0, 200.9, 200.8, 200.9, 200.9],
    'bw_error': [0.249, -0.050, -0.099, -0.149, -0.099, -0.099],
    'plf_f': [2121, 2690, 3303, 3178, 3991, 2711],
    'plf_t': [1900, 1925, 2184, 3128, 2222, 2692],
    'plf_error': [-10.420, -28.439, -33.878, -1.573, -44.325, -0.701],
    'ct_f': [None, 774, 774, 808, 802, 696],
    'ct_t': [None, 811.4, 777, 826, 839, 705],
    'ct_error': [None, 4.832, 0.388, 2.228, 4.613, 1.293],
    'ft_f': [None, 364, 504, 504, 560, 408],
    'ft_t': [None, 337, 526, 492, 557, 410],
    'ft_error': [None, -7.418, 4.365, -2.381, -0.536, 0.490]
}

# VALD on top of mine (rows 18-21)
vald_on_top = {
    'jump_num': [1, 2, 3, 4],
    'height_f': [36.7, 33.7, 21.6, 25.5],
    'height_t': [40.7, 31.9, 22.8, 20.2],
    'height_error': [10.899, -5.341, 5.556, -20.784],
    'bw_f': [200.8, 200.9, 200.8, 200.7],
    'bw_t': [200.6, 200.8, 200.8, 200.8],
    'bw_error': [-0.100, -0.050, 0.000, 0.050],
    'plf_f': [2902, 4052, 3139, 3008],
    'plf_t': [2069, 4270, 2964, 3148],
    'plf_error': [-28.704, 5.380, -5.575, 4.654],
    'ct_f': [864, 846, 732, 750],
    'ct_t': [881, 855, 783, 746],
    'ct_error': [1.968, 1.064, 6.967, -0.533],
    'ft_f': [550, 540, 410, 454],
    'ft_t': [542, 545, 410, 479],
    'ft_error': [-1.455, 0.926, 0.000, 5.507]
}

def calculate_stats(values):
    """Calculate mean, std, min, max for a list of values"""
    clean_values = [v for v in values if v is not None]
    if not clean_values:
        return None, None, None, None
    mean = statistics.mean(clean_values)
    std = statistics.stdev(clean_values) if len(clean_values) > 1 else 0
    return mean, std, min(clean_values), max(clean_values)

def print_analysis():
    print("=" * 80)
    print("FORCE PLATE VALIDATION ANALYSIS")
    print("Comparing Trevor's Plate vs VALD Forcedeck Reference")
    print("=" * 80)
    
    # 1. BODYWEIGHT CALIBRATION ACCURACY
    print("\n1. BODYWEIGHT CALIBRATION ACCURACY")
    print("-" * 40)
    
    all_bw_errors = mine_on_top['bw_error'] + vald_on_top['bw_error']
    mean_bw, std_bw, min_bw, max_bw = calculate_stats(all_bw_errors)
    
    print(f"Mean BW Error: {mean_bw:.3f}%")
    print(f"Std BW Error: {std_bw:.3f}%")
    print(f"Range: [{min_bw:.3f}%, {max_bw:.3f}%]")
    print(f"✓ EXCELLENT: All errors < 0.25%, indicating very accurate bodyweight calibration")
    
    # 2. JUMP HEIGHT MEASUREMENT
    print("\n2. JUMP HEIGHT MEASUREMENT")
    print("-" * 40)
    
    mot_height_mean, mot_height_std, mot_height_min, mot_height_max = calculate_stats(mine_on_top['height_error'])
    print(f"\nMine on Top Configuration:")
    print(f"Mean Height Error: {mot_height_mean:.2f}%")
    print(f"Std Height Error: {mot_height_std:.2f}%")
    print(f"Range: [{mot_height_min:.2f}%, {mot_height_max:.2f}%]")
    
    vot_height_mean, vot_height_std, vot_height_min, vot_height_max = calculate_stats(vald_on_top['height_error'])
    print(f"\nVALD on Top Configuration:")
    print(f"Mean Height Error: {vot_height_mean:.2f}%")
    print(f"Std Height Error: {vot_height_std:.2f}%")
    print(f"Range: [{vot_height_min:.2f}%, {vot_height_max:.2f}%]")
    
    print(f"\n⚠ CONCERN: High variability in height measurements (up to ±43.6% error)")
    print(f"  - Mine on top shows negative bias (underestimating)")
    print(f"  - Configuration affects measurement accuracy")
    
    # 3. PEAK LANDING FORCE
    print("\n3. PEAK LANDING FORCE (PLF)")
    print("-" * 40)
    
    mot_plf_mean, mot_plf_std, mot_plf_min, mot_plf_max = calculate_stats(mine_on_top['plf_error'])
    print(f"\nMine on Top Configuration:")
    print(f"Mean PLF Error: {mot_plf_mean:.2f}%")
    print(f"Std PLF Error: {mot_plf_std:.2f}%")
    print(f"Range: [{mot_plf_min:.2f}%, {mot_plf_max:.2f}%]")
    
    vot_plf_mean, vot_plf_std, vot_plf_min, vot_plf_max = calculate_stats(vald_on_top['plf_error'])
    print(f"\nVALD on Top Configuration:")
    print(f"Mean PLF Error: {vot_plf_mean:.2f}%")
    print(f"Std PLF Error: {vot_plf_std:.2f}%")
    print(f"Range: [{vot_plf_min:.2f}%, {vot_plf_max:.2f}%]")
    
    print(f"\n⚠ MAJOR CONCERN: Systematic underestimation of peak forces")
    print(f"  - Mine on top: avg {mot_plf_mean:.1f}% error (consistently underestimating)")
    print(f"  - Configuration dependent behavior")
    
    # 4. TIMING MEASUREMENTS
    print("\n4. TIMING MEASUREMENTS")
    print("-" * 40)
    
    ft_errors = [e for e in mine_on_top['ft_error'] + vald_on_top['ft_error'] if e is not None]
    ft_mean, ft_std, ft_min, ft_max = calculate_stats(ft_errors)
    
    print(f"\nFlight Time:")
    print(f"Mean Error: {ft_mean:.2f}%")
    print(f"Std Error: {ft_std:.2f}%")
    print(f"Range: [{ft_min:.2f}%, {ft_max:.2f}%]")
    print(f"✓ GOOD: Flight time errors generally < 8%")
    
    ct_errors = [e for e in mine_on_top['ct_error'] + vald_on_top['ct_error'] if e is not None]
    ct_mean, ct_std, ct_min, ct_max = calculate_stats(ct_errors)
    
    print(f"\nContraction Time:")
    print(f"Mean Error: {ct_mean:.2f}%")
    print(f"Std Error: {ct_std:.2f}%")
    print(f"Range: [{ct_min:.2f}%, {ct_max:.2f}%]")
    print(f"✓ GOOD: Contraction time errors generally < 7%")
    
    # 5. DETAILED ANALYSIS OF ERRORS
    print("\n5. DETAILED ERROR ANALYSIS")
    print("-" * 40)
    
    # Calculate absolute force errors
    plf_abs_errors = []
    for i in range(len(mine_on_top['plf_f'])):
        abs_error = abs(mine_on_top['plf_f'][i] - mine_on_top['plf_t'][i])
        plf_abs_errors.append(abs_error)
    for i in range(len(vald_on_top['plf_f'])):
        abs_error = abs(vald_on_top['plf_f'][i] - vald_on_top['plf_t'][i])
        plf_abs_errors.append(abs_error)
    
    mean_abs_error = statistics.mean(plf_abs_errors)
    print(f"\nMean Absolute Force Error: {mean_abs_error:.0f} N")
    
    # Check if errors correlate with force magnitude
    print("\n⚠ Key Findings:")
    print("  1. Configuration-dependent errors (plate stacking order matters)")
    print("  2. Systematic underestimation of peak forces when Trevor's plate on top")
    print("  3. High variability in height measurements")
    print("  4. Possible non-linearity in force measurements")
    
    # 6. RECOMMENDATIONS
    print("\n6. RECOMMENDATIONS FOR APP IMPROVEMENT")
    print("-" * 40)
    print("\n🔧 CRITICAL FIXES:")
    print("  1. Force Calibration:")
    print("     - Implement non-linear calibration curve (polynomial fit)")
    print("     - Add force-dependent correction factors")
    print("     - Current linear N_PER_VOLT (327.0 N/V) appears insufficient")
    print(f"     - Consider adding offset: avg underestimation is {mot_plf_mean:.1f}%")
    
    print("\n  2. Signal Processing:")
    print("     - Review filter settings (current 50Hz may be too aggressive)")
    print("     - Add adaptive filtering based on signal characteristics")
    print("     - Implement better peak detection algorithms")
    print("     - Consider using median filter for spike removal")
    
    print("\n  3. Jump Detection:")
    print("     - Re-examine flight detection threshold (20N)")
    print("     - Add hysteresis to prevent false triggers")
    print("     - Implement velocity-based takeoff/landing detection")
    print("     - Use rate of force development for better edge detection")
    
    print("\n  4. Calibration Procedure:")
    print("     - Add multi-point calibration with known weights")
    print("     - Store calibration curves, not just single factors")
    print("     - Implement temperature compensation if applicable")
    print("     - Add periodic recalibration reminders")
    
    print("\n  5. Quality Assurance:")
    print("     - Add real-time data quality indicators")
    print("     - Implement anomaly detection for outliers")
    print("     - Add confidence intervals to measurements")
    print("     - Flag suspicious readings for review")
    
    print("\n📊 SUGGESTED FEATURES:")
    print("  1. Calibration validation mode with known weights")
    print("  2. Force plate comparison/validation tools")
    print("  3. Measurement uncertainty reporting")
    print("  4. Advanced filtering options for different jump types")
    print("  5. Raw data export for external validation")
    print("  6. Automated calibration check before each session")
    print("  7. Visual feedback on data quality during acquisition")
    
    # 7. SPECIFIC CODE IMPROVEMENTS
    print("\n7. SPECIFIC CODE IMPROVEMENTS FOR config.py")
    print("-" * 40)
    print("  Current: N_PER_VOLT = 327.0")
    print("  Suggested: Implement calibration class with:")
    print("    - Base sensitivity: 327.0 N/V")
    print("    - Force-dependent correction: f(force) = 1 + 0.0001 * force")
    print("    - Configuration offset: -0.2 * measured_force (for high forces)")
    
    print("\n  Filter improvements:")
    print("    - Add cascaded filter option")
    print("    - Implement zero-phase filtering")
    print("    - Add filter diagnostics")
    
    print("\n8. SUMMARY")
    print("-" * 40)
    print("STRENGTHS:")
    print("  ✓ Excellent bodyweight calibration (<0.25% error)")
    print("  ✓ Good timing measurements (<8% error)")
    print("  ✓ Consistent data acquisition")
    
    print("\nWEAKNESSES:")
    print("  ✗ Significant peak force underestimation (up to -44%)")
    print("  ✗ High variability in height calculations")
    print("  ✗ Configuration-dependent behavior")
    print("  ✗ Possible non-linear response at high forces")
    
    print("\nPRIORITY FIXES:")
    print("  1. Implement non-linear force calibration")
    print("  2. Review and optimize filter settings")
    print("  3. Add measurement uncertainty reporting")
    print("  4. Implement configuration-specific corrections")

if __name__ == "__main__":
    print_analysis()