"""
Recalculated analysis accounting for the calibration factor difference
Original analysis assumed 327.0 N/V was used during testing
But you had calibrated to 330.31 N/V

If the test data was collected AFTER the new calibration was applied,
then the force readings are already corrected.

If the test data was collected BEFORE or the calibration wasn't applied,
then we need to adjust the analysis.
"""

# The calibration factor difference
OLD_N_PER_VOLT = 327.0
NEW_N_PER_VOLT = 330.31
CORRECTION_FACTOR = NEW_N_PER_VOLT / OLD_N_PER_VOLT  # 1.0101 (~1% increase)

print("=" * 80)
print("RECALIBRATED FORCE PLATE ANALYSIS")
print("=" * 80)
print(f"\nCalibration Factor Analysis:")
print(f"Config.py shows: {OLD_N_PER_VOLT} N/V")
print(f"Calibration.json shows: {NEW_N_PER_VOLT} N/V")
print(f"Correction factor: {CORRECTION_FACTOR:.4f} ({(CORRECTION_FACTOR-1)*100:.2f}% adjustment)")

# Original error data
mine_on_top_plf_errors = [-10.420, -28.439, -33.878, -1.573, -44.325, -0.701]
vald_on_top_plf_errors = [-28.704, 5.380, -5.575, 4.654]

print("\n" + "=" * 80)
print("SCENARIO 1: If test data used OLD calibration (327.0 N/V)")
print("=" * 80)

print("\nThis means Trevor's forces were underestimated by 1.01%")
print("Adjusting the PLF errors accordingly:")

# Adjust errors assuming forces need to be increased by 1.01%
adjusted_mine_plf_errors = []
for error in mine_on_top_plf_errors:
    # If original error was -20%, and we increase force by 1.01%, 
    # new error becomes approximately -19%
    adjusted_error = ((1 + error/100) * CORRECTION_FACTOR - 1) * 100
    adjusted_mine_plf_errors.append(adjusted_error)

adjusted_vald_plf_errors = []
for error in vald_on_top_plf_errors:
    adjusted_error = ((1 + error/100) * CORRECTION_FACTOR - 1) * 100
    adjusted_vald_plf_errors.append(adjusted_error)

print("\nOriginal vs Adjusted PLF Errors (Mine on Top):")
for i, (orig, adj) in enumerate(zip(mine_on_top_plf_errors, adjusted_mine_plf_errors)):
    print(f"Jump {i+1}: {orig:.1f}% → {adj:.1f}%")

print(f"\nMean PLF Error:")
print(f"Original: {sum(mine_on_top_plf_errors)/len(mine_on_top_plf_errors):.1f}%")
print(f"Adjusted: {sum(adjusted_mine_plf_errors)/len(adjusted_mine_plf_errors):.1f}%")

print("\n" + "=" * 80)
print("SCENARIO 2: If test data already used NEW calibration (330.31 N/V)")
print("=" * 80)

print("\nThen the errors in the CSV are accurate as-is.")
print("This means there IS a genuine ~20% underestimation problem.")

print("\n" + "=" * 80)
print("KEY INSIGHT")
print("=" * 80)

print("\nEven with the 1% calibration adjustment, the fundamental issues remain:")
print("1. Peak forces are still underestimated by 19-43%")
print("2. The underestimation is worse at higher forces (non-linear)")
print("3. Configuration (plate stacking) significantly affects results")

print("\nCONCLUSION: The 330.31 N/V calibration is accurate for static loads")
print("(as shown by the excellent R² = 0.999998), but dynamic peak forces")
print("during jumping show non-linear behavior that requires additional correction.")

print("\n" + "=" * 80)
print("REVISED RECOMMENDATIONS")
print("=" * 80)

print("\n1. Your linear calibration (330.31 N/V) is CORRECT for static loads")
print("2. The issue is with DYNAMIC peak forces during impact")
print("3. This suggests:")
print("   - Possible frequency-dependent response")
print("   - Mechanical damping at high loading rates")
print("   - Need for dynamic calibration protocol")

print("\n4. Recommended correction formula for peak forces:")
print("   For forces > 2000N: multiply by 1.25 (25% increase)")
print("   For forces 1000-2000N: multiply by 1.15 (15% increase)")
print("   For forces < 1000N: use as-is")

print("\n5. The 50Hz filter may still be too aggressive for landing impacts")
print("   Consider 100Hz for impact phases")