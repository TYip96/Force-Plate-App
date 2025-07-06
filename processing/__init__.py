"""
Data processing modules for the Force Plate Application.

This package contains the core data processing pipeline:
- data_processor.py: Main coordinator (facade pattern)
- buffer_manager.py: Memory-efficient circular buffers
- calibration_manager.py: Bodyweight calibration state machine
- jump_detector.py: Real-time jump detection
- jump_analyzer.py: Post-jump analysis and metrics calculation
"""