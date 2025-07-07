"""
Calibration widget for force plate N/V ratio calibration.
This is a self-contained module that can be easily removed later.
"""
import numpy as np
import json
import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QDoubleSpinBox, QRadioButton,
    QButtonGroup, QGroupBox, QMessageBox, QHeaderView, QSplitter,
    QFileDialog, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg
from scipy import stats


class CalibrationWidget(QWidget):
    """Widget for calibrating the force plate N/V ratio using known weights."""
    
    # Signal emitted when calibration is applied (new_n_per_volt, calibration_data)
    calibration_applied = pyqtSignal(float, dict)
    # Signal emitted when user wants to zero the plate
    zero_plate_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_voltage = 0.0
        self.current_force = 0.0
        self.calibration_weights = {}  # Dict: weight_kg -> list of (voltage, force) measurements
        self.current_n_per_volt = 327.0  # Default from config
        self.calibration_file = "calibration.json"
        self.is_zeroed = False  # Track if plate has been zeroed
        
        # Multiple measurement tracking
        self.current_weight_measurements = []  # List of (voltage, force) for current weight
        self.current_measurement_number = 0
        self.measurements_per_weight = 3  # Default
        
        self.init_ui()
        self.load_calibration_data()
        
        # Timer for updating readings
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(100)  # Update every 100ms
        
    def init_ui(self):
        """Initialize the user interface."""
        main_layout = QVBoxLayout(self)
        
        # Create splitter for left (controls) and right (plot)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side - Controls
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Current readings group
        readings_group = QGroupBox("Current Readings")
        readings_layout = QVBoxLayout()
        
        self.voltage_label = QLabel("Voltage: 0.000 V (zero-corrected)")
        self.voltage_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.force_label = QLabel("Force: 0.0 N (0.0 kg)")
        self.force_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.current_ratio_label = QLabel(f"Current N/V: {self.current_n_per_volt:.1f}")
        
        readings_layout.addWidget(self.voltage_label)
        readings_layout.addWidget(self.force_label)
        readings_layout.addWidget(self.current_ratio_label)
        
        # Zero plate button and status
        zero_layout = QHBoxLayout()
        self.zero_btn = QPushButton("Zero Plate")
        self.zero_btn.setStyleSheet("font-size: 12px; padding: 5px;")
        self.zero_btn.setToolTip("Zero the force plate with no weight applied")
        self.zero_btn.clicked.connect(self.on_zero_requested)
        zero_layout.addWidget(self.zero_btn)
        
        self.zero_status_label = QLabel("Not zeroed")
        self.zero_status_label.setStyleSheet("color: red;")
        zero_layout.addWidget(self.zero_status_label)
        zero_layout.addStretch()
        
        readings_layout.addLayout(zero_layout)
        
        readings_group.setLayout(readings_layout)
        
        # Weight entry group
        entry_group = QGroupBox("Add Calibration Point")
        entry_layout = QVBoxLayout()
        
        # Weight input
        weight_layout = QHBoxLayout()
        weight_layout.addWidget(QLabel("Known Weight:"))
        
        self.weight_spinbox = QDoubleSpinBox()
        self.weight_spinbox.setRange(0, 2000)
        self.weight_spinbox.setDecimals(2)
        self.weight_spinbox.setSingleStep(0.5)
        self.weight_spinbox.setValue(20.0)
        self.weight_spinbox.valueChanged.connect(self.on_weight_changed)
        weight_layout.addWidget(self.weight_spinbox)
        
        # Unit selection
        self.unit_group = QButtonGroup()
        self.kg_radio = QRadioButton("kg")
        self.lb_radio = QRadioButton("lbs")
        self.kg_radio.setChecked(True)
        self.unit_group.addButton(self.kg_radio)
        self.unit_group.addButton(self.lb_radio)
        self.unit_group.buttonClicked.connect(lambda: self.on_weight_changed())
        
        weight_layout.addWidget(self.kg_radio)
        weight_layout.addWidget(self.lb_radio)
        
        # Measurements per weight setting
        meas_layout = QHBoxLayout()
        meas_layout.addWidget(QLabel("Measurements per weight:"))
        
        self.measurements_spinbox = QSpinBox()
        self.measurements_spinbox.setRange(1, 10)
        self.measurements_spinbox.setValue(3)
        self.measurements_spinbox.valueChanged.connect(self.on_measurements_changed)
        meas_layout.addWidget(self.measurements_spinbox)
        meas_layout.addStretch()
        
        # Record button with countdown
        self.record_btn = QPushButton("Record (3s average) - Measurement 1/3")
        self.record_btn.clicked.connect(self.start_recording)
        self.record_btn.setStyleSheet("font-size: 14px; padding: 8px;")
        
        # Progress label
        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setStyleSheet("font-size: 12px; color: #0066cc;")
        
        entry_layout.addLayout(weight_layout)
        entry_layout.addLayout(meas_layout)
        entry_layout.addWidget(self.record_btn)
        entry_layout.addWidget(self.progress_label)
        entry_group.setLayout(entry_layout)
        
        # Calibration data table
        table_group = QGroupBox("Calibration Points")
        table_layout = QVBoxLayout()
        
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(10)
        self.data_table.setHorizontalHeaderLabels([
            "Weight (kg)", "Weight (lbs)", "Meas#", "Voltage (V)", 
            "Force (N)", "Mean V", "SD V", "CV (%)", "Mean F (N)", "Error (%)"
        ])
        # Set column widths
        header = self.data_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.data_table.setColumnWidth(0, 80)  # Weight kg
        self.data_table.setColumnWidth(1, 80)  # Weight lbs  
        self.data_table.setColumnWidth(2, 50)  # Meas#
        self.data_table.setColumnWidth(3, 80)  # Voltage
        self.data_table.setColumnWidth(4, 80)  # Force
        self.data_table.setColumnWidth(5, 80)  # Mean V
        self.data_table.setColumnWidth(6, 60)  # SD V
        self.data_table.setColumnWidth(7, 60)  # CV
        self.data_table.setColumnWidth(8, 80)  # Mean F
        self.data_table.setColumnWidth(9, 70)  # Error
        
        # Table buttons
        table_btn_layout = QHBoxLayout()
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.clicked.connect(self.clear_all_points)
        
        table_btn_layout.addWidget(self.remove_btn)
        table_btn_layout.addWidget(self.clear_btn)
        
        table_layout.addWidget(self.data_table)
        table_layout.addLayout(table_btn_layout)
        table_group.setLayout(table_layout)
        
        # Calibration results group
        results_group = QGroupBox("Calibration Results")
        results_layout = QVBoxLayout()
        
        self.new_ratio_label = QLabel("New N/V Ratio: ---")
        self.new_ratio_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.r_squared_label = QLabel("R² Value: ---")
        self.rmse_label = QLabel("RMSE: --- N")
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: red; font-weight: bold;")
        
        results_layout.addWidget(self.new_ratio_label)
        results_layout.addWidget(self.r_squared_label)
        results_layout.addWidget(self.rmse_label)
        results_layout.addWidget(self.warning_label)
        results_group.setLayout(results_layout)
        
        # Action buttons
        action_layout = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Calibration")
        self.apply_btn.clicked.connect(self.apply_calibration)
        self.apply_btn.setEnabled(False)
        self.apply_btn.setStyleSheet("font-size: 14px; padding: 10px; font-weight: bold;")
        
        self.save_btn = QPushButton("Save Data")
        self.save_btn.clicked.connect(self.save_calibration_data)
        
        self.load_btn = QPushButton("Load Data")
        self.load_btn.clicked.connect(self.load_calibration_data)
        
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.clicked.connect(self.export_csv)
        
        action_layout.addWidget(self.apply_btn)
        action_layout.addWidget(self.save_btn)
        action_layout.addWidget(self.load_btn)
        action_layout.addWidget(self.export_btn)
        
        # Add all to left layout
        left_layout.addWidget(readings_group)
        left_layout.addWidget(entry_group)
        left_layout.addWidget(table_group)
        left_layout.addWidget(results_group)
        left_layout.addLayout(action_layout)
        left_layout.addStretch()
        
        # Right side - Calibration plot
        self.plot_widget = pg.PlotWidget(title="Force Plate Calibration Curve")
        self.plot_widget.setLabel('left', 'Measured Force', units='N')
        self.plot_widget.setLabel('bottom', 'Actual Force', units='N')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        # Add scatter plot for data points
        self.scatter_plot = self.plot_widget.plot(
            [], [], pen=None, symbol='o', symbolSize=10,
            symbolBrush='b', name='Calibration Points'
        )
        
        # Add line plot for best fit
        self.fit_line = self.plot_widget.plot(
            [], [], pen=pg.mkPen('r', width=2), name='Best Fit'
        )
        
        # Add ideal line (y=x)
        self.ideal_line = self.plot_widget.plot(
            [], [], pen=pg.mkPen('g', width=1, style=Qt.PenStyle.DashLine),
            name='Ideal (1:1)'
        )
        
        # Add to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(self.plot_widget)
        splitter.setSizes([500, 700])  # Initial sizes
        
        main_layout.addWidget(splitter)
        
        # Recording state
        self.is_recording = False
        self.recording_start_time = None
        self.recording_values = []
        self.recording_countdown = 3
        
    def update_record_button_text(self):
        """Update the record button text based on current state."""
        total_needed = self.measurements_spinbox.value()
        current = self.current_measurement_number + 1
        if current > total_needed:
            current = 1
        self.record_btn.setText(f"Record (3s average) - Measurement {current}/{total_needed}")
        
    def on_measurements_changed(self, value):
        """Handle change in measurements per weight setting."""
        self.measurements_per_weight = value
        self.update_record_button_text()
        
    def on_weight_changed(self):
        """Handle change in weight value or units."""
        self.update_weight_status()
        
    def update_weight_status(self):
        """Update the status display when weight changes."""
        weight_value = self.weight_spinbox.value()
        if self.lb_radio.isChecked():
            weight_kg = weight_value * 0.453592
        else:
            weight_kg = weight_value
            
        if weight_kg in self.calibration_weights:
            measurements = self.calibration_weights[weight_kg]
            total_needed = self.measurements_spinbox.value()
            self.current_weight_measurements = measurements.copy()
            self.current_measurement_number = len(measurements)
            
            if self.current_measurement_number >= total_needed:
                self.progress_label.setText(
                    f"Weight {weight_kg:.2f} kg already has {self.current_measurement_number} measurements"
                )
            else:
                self.progress_label.setText(
                    f"Weight {weight_kg:.2f} kg has {self.current_measurement_number}/{total_needed} measurements"
                )
        else:
            self.current_weight_measurements = []
            self.current_measurement_number = 0
            self.progress_label.setText("")
            
        self.update_record_button_text()
        
    def set_current_readings(self, voltage, force):
        """Update current voltage and force readings from main app.
        
        Args:
            voltage: Summed voltage across all channels (after zero offset correction)
            force: Total force in Newtons (sum of all channels)
        """
        self.current_voltage = voltage
        self.current_force = force
        
        # If recording, collect samples
        if self.is_recording:
            self.recording_values.append((voltage, force))
        
    @pyqtSlot()
    def update_display(self):
        """Update the display with current readings."""
        self.voltage_label.setText(f"Voltage: {self.current_voltage:.3f} V (zero-corrected)")
        
        # Show force in both N and kg
        force_kg = self.current_force / 9.81
        self.force_label.setText(f"Force: {self.current_force:.1f} N ({force_kg:.2f} kg)")
        
        # Update recording countdown if recording
        if self.is_recording:
            elapsed = datetime.now().timestamp() - self.recording_start_time
            remaining = 3 - elapsed
            if remaining > 0:
                total_needed = self.measurements_spinbox.value()
                current = self.current_measurement_number + 1
                self.record_btn.setText(f"Recording {current}/{total_needed}... {remaining:.1f}s")
            else:
                self.finish_recording()
                
    def start_recording(self):
        """Start recording a calibration point."""
        if self.is_recording:
            return
            
        # Check if we're continuing measurements for an existing weight
        weight_value = self.weight_spinbox.value()
        if self.lb_radio.isChecked():
            weight_kg = weight_value * 0.453592
        else:
            weight_kg = weight_value
            
        if weight_kg in self.calibration_weights:
            # Continue with existing measurements for this weight
            self.current_weight_measurements = self.calibration_weights[weight_kg].copy()
            self.current_measurement_number = len(self.current_weight_measurements)
            if self.current_measurement_number >= self.measurements_spinbox.value():
                # Already have enough measurements for this weight
                QMessageBox.information(self, "Measurements Complete", 
                    f"Already have {self.current_measurement_number} measurements for {weight_kg:.2f} kg. "
                    "Remove some measurements or change the weight to continue.")
                return
        else:
            # New weight
            self.current_weight_measurements = []
            self.current_measurement_number = 0
            
        self.is_recording = True
        self.recording_start_time = datetime.now().timestamp()
        self.recording_values = []
        self.record_btn.setEnabled(False)
        
    def finish_recording(self):
        """Finish recording and add the calibration point."""
        self.is_recording = False
        self.record_btn.setEnabled(True)
        
        if len(self.recording_values) < 10:  # Need at least some samples
            QMessageBox.warning(self, "Recording Error", 
                              "Not enough samples collected. Please ensure DAQ is running.")
            self.update_record_button_text()
            return
            
        # Calculate averages from recorded values
        avg_voltage = np.mean([v[0] for v in self.recording_values])
        avg_force = np.mean([v[1] for v in self.recording_values])
            
        # Get the known weight
        weight_value = self.weight_spinbox.value()
        if self.lb_radio.isChecked():
            # Convert lbs to kg
            weight_kg = weight_value * 0.453592
        else:
            weight_kg = weight_value
            
        # Add measurement to current weight
        if weight_kg not in self.calibration_weights:
            self.calibration_weights[weight_kg] = []
            self.current_weight_measurements = []
            self.current_measurement_number = 0
            
        self.current_weight_measurements.append((avg_voltage, avg_force))
        self.calibration_weights[weight_kg] = self.current_weight_measurements.copy()
        self.current_measurement_number += 1
        
        # Update progress
        total_needed = self.measurements_spinbox.value()
        self.progress_label.setText(
            f"Completed {self.current_measurement_number}/{total_needed} measurements for {weight_kg:.2f} kg"
        )
        
        # Check if we need more measurements for this weight
        if self.current_measurement_number < total_needed:
            self.update_record_button_text()
        else:
            # All measurements complete for this weight
            self.current_measurement_number = 0
            self.current_weight_measurements = []
            self.progress_label.setText(f"All measurements complete for {weight_kg:.2f} kg")
            self.update_record_button_text()
            
        # Update table
        self.update_table()
        
        # Update calibration results
        self.update_calibration_results()
        
    def update_table(self):
        """Update the calibration data table with individual measurements and statistics."""
        # Count total rows needed
        total_rows = sum(len(measurements) for measurements in self.calibration_weights.values())
        self.data_table.setRowCount(total_rows)
        
        row = 0
        for weight_kg in sorted(self.calibration_weights.keys()):
            measurements = self.calibration_weights[weight_kg]
            if not measurements:
                continue
                
            weight_lbs = weight_kg * 2.20462
            actual_force_n = weight_kg * 9.81
            
            # Calculate statistics for this weight
            voltages = [m[0] for m in measurements]
            forces = [m[1] for m in measurements]
            mean_voltage = np.mean(voltages)
            std_voltage = np.std(voltages) if len(voltages) > 1 else 0
            cv_voltage = (std_voltage / mean_voltage * 100) if mean_voltage > 0 else 0
            mean_force = np.mean(forces)
            error_pct = ((mean_force - actual_force_n) / actual_force_n * 100) if actual_force_n > 0 else 0
            
            # Add each measurement to table
            for i, (voltage, force) in enumerate(measurements):
                # Weight columns (same for all measurements of this weight)
                self.data_table.setItem(row, 0, QTableWidgetItem(f"{weight_kg:.2f}"))
                self.data_table.setItem(row, 1, QTableWidgetItem(f"{weight_lbs:.2f}"))
                
                # Measurement number
                self.data_table.setItem(row, 2, QTableWidgetItem(f"{i+1}"))
                
                # Individual measurement
                self.data_table.setItem(row, 3, QTableWidgetItem(f"{voltage:.3f}"))
                self.data_table.setItem(row, 4, QTableWidgetItem(f"{force:.1f}"))
                
                # Statistics (same for all measurements of this weight)
                self.data_table.setItem(row, 5, QTableWidgetItem(f"{mean_voltage:.3f}"))
                self.data_table.setItem(row, 6, QTableWidgetItem(f"{std_voltage:.3f}"))
                cv_item = QTableWidgetItem(f"{cv_voltage:.1f}")
                self.data_table.setItem(row, 7, cv_item)
                self.data_table.setItem(row, 8, QTableWidgetItem(f"{mean_force:.1f}"))
                error_item = QTableWidgetItem(f"{error_pct:.1f}")
                self.data_table.setItem(row, 9, error_item)
                
                # Color code CV
                if cv_voltage > 5:
                    cv_item.setBackground(Qt.GlobalColor.red)
                elif cv_voltage > 2:
                    cv_item.setBackground(Qt.GlobalColor.yellow)
                    
                # Color code errors
                if abs(error_pct) > 5:
                    error_item.setBackground(Qt.GlobalColor.red)
                elif abs(error_pct) > 2:
                    error_item.setBackground(Qt.GlobalColor.yellow)
                    
                row += 1
                
    def update_calibration_results(self):
        """Calculate and display calibration results using averaged measurements."""
        if len(self.calibration_weights) < 2:
            self.new_ratio_label.setText("New N/V Ratio: Need at least 2 different weights")
            self.apply_btn.setEnabled(False)
            return
            
        # Extract averaged data for each weight
        actual_forces = []
        mean_voltages = []
        
        for weight_kg in sorted(self.calibration_weights.keys()):
            measurements = self.calibration_weights[weight_kg]
            if measurements:
                actual_forces.append(weight_kg * 9.81)
                mean_voltages.append(np.mean([m[0] for m in measurements]))
                
        actual_forces = np.array(actual_forces)
        voltages = np.array(mean_voltages)
        
        # Perform linear regression (Force = slope * Voltage)
        # We force the line through origin (0,0)
        slope = np.sum(actual_forces * voltages) / np.sum(voltages * voltages)
        
        # Calculate R-squared
        predicted_forces = slope * voltages
        ss_res = np.sum((actual_forces - predicted_forces) ** 2)
        ss_tot = np.sum((actual_forces - np.mean(actual_forces)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        # Calculate RMSE
        rmse = np.sqrt(np.mean((actual_forces - predicted_forces) ** 2))
        
        # Update displays
        self.new_ratio_label.setText(f"New N/V Ratio: {slope:.1f}")
        self.r_squared_label.setText(f"R² Value: {r_squared:.4f}")
        self.rmse_label.setText(f"RMSE: {rmse:.1f} N")
        
        # Check for warnings
        percent_diff = abs(slope - self.current_n_per_volt) / self.current_n_per_volt * 100
        if percent_diff > 10:
            self.warning_label.setText(
                f"WARNING: New ratio differs by {percent_diff:.1f}% from current value!"
            )
        else:
            self.warning_label.setText("")
            
        # Update plot
        self.update_plot(slope)
        
        # Enable apply button
        self.apply_btn.setEnabled(True)
        
        # Store the new ratio
        self.new_n_per_volt = slope
        
    def update_plot(self, slope):
        """Update the calibration curve plot with all individual measurements."""
        if not self.calibration_weights:
            return
            
        # Collect all individual data points
        all_actual_forces = []
        all_measured_forces = []
        
        for weight_kg in self.calibration_weights:
            actual_force_n = weight_kg * 9.81
            for voltage, force in self.calibration_weights[weight_kg]:
                all_actual_forces.append(actual_force_n)
                all_measured_forces.append(force)
                
        all_actual_forces = np.array(all_actual_forces)
        all_measured_forces = np.array(all_measured_forces)
        
        # Update scatter plot with all points
        self.scatter_plot.setData(all_actual_forces, all_measured_forces)
        
        # Update best fit line
        if len(all_actual_forces) > 0:
            x_range = np.linspace(0, max(all_actual_forces) * 1.1, 100)
            y_fit = x_range  # Since we're plotting force vs force after applying N/V
            self.fit_line.setData(x_range, y_fit)
            
            # Update ideal line
            self.ideal_line.setData(x_range, x_range)
        
        # Auto-range
        self.plot_widget.autoRange()
        
    def remove_selected(self):
        """Remove selected rows from calibration data."""
        selected_rows = set()
        for item in self.data_table.selectedItems():
            selected_rows.add(item.row())
            
        if not selected_rows:
            return
            
        # Identify which weights and measurements to remove
        weights_to_remove = set()
        weights_to_update = {}
        
        # Build a map of row to weight/measurement
        row = 0
        for weight_kg in sorted(self.calibration_weights.keys()):
            measurements = self.calibration_weights[weight_kg]
            for i, measurement in enumerate(measurements):
                if row in selected_rows:
                    if weight_kg not in weights_to_update:
                        weights_to_update[weight_kg] = list(measurements)
                    # Mark measurement for removal
                    weights_to_update[weight_kg][i] = None
                row += 1
                
        # Update calibration data
        for weight_kg, updated_measurements in weights_to_update.items():
            # Filter out None values
            filtered = [m for m in updated_measurements if m is not None]
            if filtered:
                self.calibration_weights[weight_kg] = filtered
            else:
                # Remove weight entirely if no measurements left
                del self.calibration_weights[weight_kg]
                if weight_kg == self.weight_spinbox.value():
                    # Reset current measurement tracking
                    self.current_weight_measurements = []
                    self.current_measurement_number = 0
                    self.progress_label.setText("")
                    
        self.update_table()
        self.update_calibration_results()
        self.update_record_button_text()
        
    def clear_all_points(self):
        """Clear all calibration points."""
        reply = QMessageBox.question(
            self, "Clear All Points",
            "Are you sure you want to clear all calibration points?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.calibration_weights.clear()
            self.current_weight_measurements = []
            self.current_measurement_number = 0
            self.progress_label.setText("")
            self.update_table()
            self.update_calibration_results()
            self.update_record_button_text()
            
    def apply_calibration(self):
        """Apply the new calibration to the system."""
        if not hasattr(self, 'new_n_per_volt'):
            return
            
        reply = QMessageBox.question(
            self, "Apply Calibration",
            f"Apply new N/V ratio of {self.new_n_per_volt:.1f}?\n"
            f"Current ratio: {self.current_n_per_volt:.1f}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Prepare calibration data
            calibration_data = {
                'n_per_volt': self.new_n_per_volt,
                'calibration_weights': {str(k): v for k, v in self.calibration_weights.items()},
                'timestamp': datetime.now().isoformat(),
                'r_squared': float(self.r_squared_label.text().split(': ')[1]),
                'rmse': float(self.rmse_label.text().split(': ')[1].split(' ')[0]),
                'measurements_per_weight': self.measurements_spinbox.value()
            }
            
            # Emit signal to main app
            self.calibration_applied.emit(self.new_n_per_volt, calibration_data)
            
            # Update current ratio
            self.current_n_per_volt = self.new_n_per_volt
            self.current_ratio_label.setText(f"Current N/V: {self.current_n_per_volt:.1f}")
            
            # Save automatically
            self.save_calibration_data()
            
            QMessageBox.information(self, "Calibration Applied", 
                                  "New calibration has been applied successfully!")
            
    def save_calibration_data(self):
        """Save calibration data to JSON file."""
        # Calculate current statistics if we have points
        r_squared = None
        rmse = None
        num_weights = len(self.calibration_weights)
        total_measurements = sum(len(m) for m in self.calibration_weights.values())
        
        if num_weights >= 2:
            # Recalculate stats using averaged values
            actual_forces = []
            mean_voltages = []
            
            for weight_kg in sorted(self.calibration_weights.keys()):
                measurements = self.calibration_weights[weight_kg]
                if measurements:
                    actual_forces.append(weight_kg * 9.81)
                    mean_voltages.append(np.mean([m[0] for m in measurements]))
                    
            actual_forces = np.array(actual_forces)
            voltages = np.array(mean_voltages)
            slope = np.sum(actual_forces * voltages) / np.sum(voltages * voltages)
            predicted_forces = slope * voltages
            ss_res = np.sum((actual_forces - predicted_forces) ** 2)
            ss_tot = np.sum((actual_forces - np.mean(actual_forces)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            rmse = np.sqrt(np.mean((actual_forces - predicted_forces) ** 2))
        
        # Calculate per-weight statistics
        weight_statistics = {}
        for weight_kg, measurements in self.calibration_weights.items():
            if measurements:
                voltages = [m[0] for m in measurements]
                forces = [m[1] for m in measurements]
                weight_statistics[str(weight_kg)] = {
                    'mean_voltage': np.mean(voltages),
                    'std_voltage': np.std(voltages) if len(voltages) > 1 else 0,
                    'cv_percent': (np.std(voltages) / np.mean(voltages) * 100) if np.mean(voltages) > 0 and len(voltages) > 1 else 0,
                    'mean_force': np.mean(forces),
                    'num_measurements': len(measurements)
                }
        
        data = {
            'n_per_volt': self.current_n_per_volt,
            'calibration_weights': {str(k): v for k, v in self.calibration_weights.items()},
            'weight_statistics': weight_statistics,
            'timestamp': datetime.now().isoformat(),
            'r_squared': r_squared,
            'rmse': rmse,
            'num_weights': num_weights,
            'total_measurements': total_measurements,
            'measurements_per_weight': self.measurements_spinbox.value()
        }
        
        try:
            with open(self.calibration_file, 'w') as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(self, "Save Successful", 
                                  f"Calibration data saved to {self.calibration_file}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save: {str(e)}")
            
    def load_calibration_data(self):
        """Load calibration data from JSON file."""
        if not os.path.exists(self.calibration_file):
            return
            
        try:
            with open(self.calibration_file, 'r') as f:
                data = json.load(f)
                
            self.current_n_per_volt = data.get('n_per_volt', 327.0)
            
            # Handle both old format (calibration_points) and new format (calibration_weights)
            if 'calibration_weights' in data:
                # New format with multiple measurements
                self.calibration_weights = {}
                for weight_str, measurements in data['calibration_weights'].items():
                    self.calibration_weights[float(weight_str)] = measurements
                    
                # Load measurements per weight setting
                if 'measurements_per_weight' in data:
                    self.measurements_spinbox.setValue(data['measurements_per_weight'])
            elif 'calibration_points' in data:
                # Old format - convert to new format
                self.calibration_weights = {}
                for actual_n, voltage, measured_n in data['calibration_points']:
                    weight_kg = actual_n / 9.81
                    if weight_kg not in self.calibration_weights:
                        self.calibration_weights[weight_kg] = []
                    self.calibration_weights[weight_kg].append((voltage, measured_n))
            
            # Reset current measurement tracking
            self.current_weight_measurements = []
            self.current_measurement_number = 0
            self.progress_label.setText("")
            
            self.current_ratio_label.setText(f"Current N/V: {self.current_n_per_volt:.1f}")
            self.update_table()
            self.update_calibration_results()
            self.update_record_button_text()
            
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Failed to load calibration: {str(e)}")
            
    def export_csv(self):
        """Export calibration data to CSV file."""
        if not self.calibration_weights:
            QMessageBox.warning(self, "No Data", "No calibration data to export!")
            return
            
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Calibration Data", "",
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    # Write header
                    f.write("Weight_kg,Weight_lbs,Measurement_Num,Voltage_V,Force_N,")
                    f.write("Mean_Voltage_V,SD_Voltage_V,CV_Percent,Mean_Force_N,")
                    f.write("Expected_Force_N,Error_N,Error_Percent\n")
                    
                    # Write data
                    for weight_kg in sorted(self.calibration_weights.keys()):
                        measurements = self.calibration_weights[weight_kg]
                        if not measurements:
                            continue
                            
                        weight_lbs = weight_kg * 2.20462
                        actual_force_n = weight_kg * 9.81
                        
                        # Calculate statistics
                        voltages = [m[0] for m in measurements]
                        forces = [m[1] for m in measurements]
                        mean_voltage = np.mean(voltages)
                        std_voltage = np.std(voltages) if len(voltages) > 1 else 0
                        cv_voltage = (std_voltage / mean_voltage * 100) if mean_voltage > 0 else 0
                        mean_force = np.mean(forces)
                        error_n = mean_force - actual_force_n
                        error_pct = (error_n / actual_force_n * 100) if actual_force_n > 0 else 0
                        
                        # Write each measurement
                        for i, (voltage, force) in enumerate(measurements):
                            f.write(f"{weight_kg:.2f},{weight_lbs:.2f},{i+1},")
                            f.write(f"{voltage:.3f},{force:.1f},")
                            f.write(f"{mean_voltage:.3f},{std_voltage:.3f},{cv_voltage:.1f},")
                            f.write(f"{mean_force:.1f},{actual_force_n:.1f},{error_n:.1f},{error_pct:.1f}\n")
                        
                QMessageBox.information(self, "Export Successful", 
                                      f"Data exported to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export: {str(e)}")
                
    def on_zero_requested(self):
        """Handle zero plate button click."""
        reply = QMessageBox.question(
            self, "Zero Plate",
            "Remove all weight from the force plate and click Yes to zero.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Emit signal to main app to perform zeroing
            self.zero_plate_requested.emit()
            QMessageBox.information(self, "Zeroing", 
                "Zeroing in progress... This will take a few seconds.")
                
    def on_zero_complete(self):
        """Called when zero offset has been applied."""
        self.is_zeroed = True
        self.zero_status_label.setText("✓ Zeroed")
        self.zero_status_label.setStyleSheet("color: green;")