"""
Manages the PyQtGraph plot for displaying live Force vs. Time data.
"""
import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import pyqtSlot, QObject, QTimer
from collections import deque

import config

pg.setConfigOptions(useOpenGL=True, antialias=True)

class PlotHandler(QObject):
    """
    Handles plotting of Fz data using PyQtGraph.
    Receives processed data chunks via a slot.
    Keeps all data for the trial, but view scrolls to show the latest window.
    Supports viewing individual channels or their sum.
    """
    def __init__(self, plot_widget):
        super().__init__()
        self.plot_widget = plot_widget
        self.plot_item = None
        self.plot_curves = [] # List to hold all plot curves (individual + sum)
        self.num_channels = 0 # Will be set in setup_plot
        self.current_view_mode = 'summed' # 'summed' or 'individual'

        # Define colors for the plot lines (add more if > 4 channels needed)
        self._channel_colors = [(0, 0, 255), (0, 180, 0), (200, 0, 0), (200, 150, 0), (150, 0, 200)]
        self._sum_color = (30, 30, 30) # Dark grey/black for sum

        # Buffers for plotting, will be initialized in clear_plot()
        self.plot_buffer_time = None
        self.plot_buffer_forces = None
        self._last_time = 0.0  # Track the latest time point for view range
        # Throttle plot updates: collect chunks and update at 20 FPS
        self._pending_chunks = []
        self._plot_timer = QTimer(self)
        self._plot_timer.setInterval(33)  # 33ms interval (~30 FPS) for smoother updates
        self._plot_timer.timeout.connect(self._flush_pending)
        self._plot_timer.start()
        
        # Initialize Y-axis max for live plot and lock min at -20N
        self._y_max = config.PLOT_Y_AXIS_INITIAL_MAX
        self._y_min = -20  # Fixed Y-axis minimum with padding below x-axis
        
        
        # Add event markers for jump analysis
        self._event_markers = {}
        
    def setup_plot(self, num_channels):
        """Initializes the plot appearance and data structures for multi-channel data."""
        self.num_channels = num_channels
        if self.plot_item:
             self.plot_item.clear() # Clear previous items if re-setting up
        else:
            self.plot_widget.setBackground('w') # White background
            self.plot_item = self.plot_widget.getPlotItem()

        # Add Legend
        self.plot_item.addLegend()

        # Set labels and title (can be updated in set_view_mode)
        self.plot_item.setLabel('left', "Force", units='N')
        self.plot_item.setLabel('bottom', "Time", units='s')
        self.plot_item.setTitle("Live Force Data - Summed Channels")

        # Enable mouse interaction
        self.plot_item.setMouseEnabled(x=True, y=True)
        self.plot_item.showGrid(x=True, y=True)
        
        # Set up the ViewBox to limit Y-axis minimum value
        view_box = self.plot_item.getViewBox()
        view_box.setLimits(yMin=self._y_min)  # Lock Y-axis minimum
        
        # Create plot curves (initially empty)
        self.plot_curves = []
        # Individual channel curves
        for i in range(self.num_channels):
            pen = pg.mkPen(color=self._channel_colors[i % len(self._channel_colors)], width=1)
            curve = self.plot_item.plot(pen=pen, name=f"Channel {i}")
            # Improve performance with clip-to-view and downsampling
            try:
                curve.setClipToView(True)
                curve.setDownsampling(auto=True, downsampleMethod='peak')
            except Exception:
                pass
            curve.setVisible(False) # Initially hidden
            self.plot_curves.append(curve)

        # Summed curve
        pen = pg.mkPen(color=self._sum_color, width=2)
        sum_curve = self.plot_item.plot(pen=pen, name="Summed")
        # Improve performance for summed curve
        try:
            sum_curve.setClipToView(True)
            sum_curve.setDownsampling(auto=True, downsampleMethod='peak')
        except Exception:
            pass
        sum_curve.setVisible(True) # Initially visible
        self.plot_curves.append(sum_curve)

        self.clear_plot() # Ensure data buffers are initialized correctly
        
    def set_view_mode(self, mode):
        """Switches between 'individual' and 'summed' plot views."""
        if mode not in ['individual', 'summed'] or not self.plot_item:
            return
        self.current_view_mode = mode

        if mode == 'individual':
            self.plot_item.setTitle("Live Force Data - Individual Channels")
            self.plot_item.setLabel('left', "Channel Force", units='N')
            # Show individual, hide sum
            for i in range(self.num_channels):
                self.plot_curves[i].setVisible(True)
            self.plot_curves[self.num_channels].setVisible(False) # Hide sum curve
        else: # mode == 'summed'
            self.plot_item.setTitle("Live Force Data - Summed Channels")
            self.plot_item.setLabel('left', "Total Vertical Force (Fz)", units='N')
            # Hide individual, show sum
            for i in range(self.num_channels):
                self.plot_curves[i].setVisible(False)
            self.plot_curves[self.num_channels].setVisible(True) # Show sum curve

        # Maintain Y-axis locked range [_y_min, current max]
        self.plot_item.enableAutoRange('y', False)
        # Set Y range without _updating_range flag
        self.plot_item.setYRange(self._y_min, self._y_max)

    @pyqtSlot(np.ndarray, np.ndarray) # Expecting time_chunk (1D), force_chunk_multi (2D: chunk_size, num_channels)
    def update_plot(self, time_chunk, force_chunk_multi_channel):
        """
        Updates the plot with new multi-channel data chunk.
        Appends to internal lists and updates the plot curves.
        Sets the X-axis view range to scroll.
        """
        if not self.plot_curves or force_chunk_multi_channel.shape[1] != self.num_channels:
            print(f"PlotHandler Error: Plot not initialized or channel mismatch (expected {self.num_channels}, got {force_chunk_multi_channel.shape[1]})")
            return # Plot not initialized or channel mismatch

        # Ensure force_chunk has the correct shape (chunk_size, num_channels)
        if len(time_chunk) != force_chunk_multi_channel.shape[0]:
             print(f"PlotHandler Error: Time chunk size ({len(time_chunk)}) != Force chunk size ({force_chunk_multi_channel.shape[0]})")
             return

        # Transpose forces for easier channel access: shape becomes [num_channels, chunk_size]
        forces_by_channel = force_chunk_multi_channel.T

        # Queue the chunk for throttled plotting
        self._pending_chunks.append((time_chunk, force_chunk_multi_channel))

    def clear_plot(self):
        """
        Clears the data from the plot and resets buffers and view.
        """
        # Initialize ring buffers for plotting
        buffer_len = int(config.SAMPLE_RATE * config.PLOT_WINDOW_DURATION_S)
        self.plot_buffer_time = deque(maxlen=buffer_len)
        self.plot_buffer_forces = [deque(maxlen=buffer_len) for _ in range(self.num_channels + 1)]
        # Clear any pending chunks
        self._pending_chunks.clear()
        self._last_time = 0.0

        # Clear visual data from all curves
        for curve in self.plot_curves:
            curve.setData([], [])
            
        # Clear all event markers
        self._remove_event_markers()

        if self.plot_item:
            # Reset plot ranges for the new acquisition
            self.plot_item.enableAutoRange('x', False) # Keep X control
            self.plot_item.setXRange(0, config.PLOT_WINDOW_DURATION_S, padding=0.01)
            # Reset Y-axis to fixed initial range [_y_min, initial max]
            self._y_max = config.PLOT_Y_AXIS_INITIAL_MAX
            self.plot_item.enableAutoRange('y', False)
            self.plot_item.setYRange(self._y_min, self._y_max)
            
            # Ensure Y-axis minimum limit is set
            view_box = self.plot_item.getViewBox()
            view_box.setLimits(yMin=self._y_min)

    def _flush_pending(self):
        """Process queued chunks and update the visible curves."""
        if not self._pending_chunks:
            return
        # Only use the most recent chunk to keep UI at target FPS and avoid backlog
        time_chunk, force_chunk_multi = self._pending_chunks[-1]
        self._pending_chunks.clear()
        forces_by_channel = force_chunk_multi.T
        self.plot_buffer_time.extend(time_chunk)
        for i in range(self.num_channels):
            self.plot_buffer_forces[i].extend(forces_by_channel[i])
        summed = np.sum(forces_by_channel, axis=0)
        self.plot_buffer_forces[self.num_channels].extend(summed)
        # Update only visible curve(s)
        if self.plot_buffer_time:
            # Use the time values directly - they are already relative to acquisition start
            plot_times = list(self.plot_buffer_time)
            
            if self.current_view_mode == 'summed':
                idx = self.num_channels
                self.plot_curves[idx].setData(plot_times, list(self.plot_buffer_forces[idx]))
            else:
                for i in range(self.num_channels):
                    self.plot_curves[i].setData(plot_times, list(self.plot_buffer_forces[i]))
            
            # Scroll X-axis to show latest
            if len(plot_times) > 0:
                self._last_time = plot_times[-1]
                start = max(0, self._last_time - config.PLOT_WINDOW_DURATION_S)
                self.plot_item.enableAutoRange('x', False)
                self.plot_item.setXRange(start, self._last_time, padding=0.01) 
                # Adjust Y-axis max if data exceeds the current max
                if self.current_view_mode == 'summed':
                    idxs = [self.num_channels]
                else:
                    idxs = range(self.num_channels)
                # Compute the maximum force among visible channels
                current_max = max((max(self.plot_buffer_forces[i]) for i in idxs if self.plot_buffer_forces[i]), default=0)
                if current_max > self._y_max:
                    self._y_max = current_max * 1.1  # Add 10% padding
                    self.plot_item.setYRange(self._y_min, self._y_max)  # Update range while keeping minimum fixed
                    
    def reset_view(self):
        """Resets the plot view to the initial X and Y ranges."""
        if self.plot_item:
            self._y_max = config.PLOT_Y_AXIS_INITIAL_MAX # Reset Y max too
            self.plot_item.enableAutoRange('x', False)
            self.plot_item.enableAutoRange('y', False)
            self.plot_item.setXRange(0, config.PLOT_WINDOW_DURATION_S, padding=0.01)
            self.plot_item.setYRange(self._y_min, self._y_max, padding=0) # Reset Y with fixed min 
    
    def _remove_event_markers(self):
        """Removes all event markers from the plot."""
        for marker_name, marker_items in self._event_markers.items():
            for item in marker_items:
                if item in self.plot_item.items:
                    self.plot_item.removeItem(item)
        
        self._event_markers = {}
    
    @pyqtSlot(dict)
    def add_event_markers(self, events_dict):
        """
        Adds markers for jump analysis events (start, takeoff, landing).
        
        Args:
            events_dict: Dictionary containing event times and force values
                Required keys:
                - 'jump_start_time': time (s) when jump movement began
                - 'takeoff_time': time (s) of takeoff
                - 'landing_time': time (s) of landing
                - 'jump_start_force': force (N) at jump start
                - 'takeoff_force': force (N) at takeoff
                - 'landing_force': force (N) at landing
                - 'jump_number': the jump number for labeling
        """
        # First remove any existing markers
        self._remove_event_markers()
        
        if not events_dict:
            print("No event data provided to add_event_markers")
            return
            
        jump_num = events_dict.get('jump_number', 0)
        
        # Define marker colors and styles
        marker_colors = {
            'jump_start': (0, 150, 0),     # Green
            'takeoff': (255, 0, 0),        # Red
            'landing': (0, 0, 255)         # Blue
        }
        
        # Define marker sizes and text offsets
        marker_size = 10
        
        # Create markers for each jump event
        for event_type, color in marker_colors.items():
            time_key = f"{event_type}_time"
            force_key = f"{event_type}_force"
            
            if time_key in events_dict and force_key in events_dict:
                time_val = events_dict[time_key]
                force_val = events_dict[force_key]
                
                # Create scatter point marker
                scatter_item = pg.ScatterPlotItem()
                scatter_item.setBrush(pg.mkBrush(color))
                scatter_item.setSize(marker_size)
                scatter_item.addPoints([time_val], [force_val])
                
                # Create text label
                label_text = f"{event_type.capitalize()}"
                text_item = pg.TextItem(text=label_text, color=color, anchor=(0.5, 1.5))
                text_item.setPos(time_val, force_val)
                
                # Add items to plot
                self.plot_item.addItem(scatter_item)
                self.plot_item.addItem(text_item)
                
                # Store references to the markers
                if event_type not in self._event_markers:
                    self._event_markers[event_type] = []
                self._event_markers[event_type].extend([scatter_item, text_item])
                
                print(f"Added marker for Jump #{jump_num} {event_type} at t={time_val:.3f}s, F={force_val:.1f}N")
            else:
                print(f"Missing data for {event_type} marker: {time_key} or {force_key} not in events_dict")
                
        # Adjust view range to show all markers if needed
        self._ensure_event_markers_visible(events_dict)
    
    def _ensure_event_markers_visible(self, events_dict):
        """Adjusts the view range to ensure all event markers are visible."""
        if not events_dict:
            return
            
        # Find min and max times in the events
        time_keys = [k for k in events_dict.keys() if k.endswith('_time')]
        if not time_keys:
            return
            
        times = [events_dict[k] for k in time_keys]
        min_time = min(times)
        max_time = max(times)
        
        # Add padding
        padding = 0.5  # seconds
        min_time = max(0, min_time - padding)
        max_time = max_time + padding
        
        # Set the X-range to show all events
        duration = max_time - min_time
        if duration > 0:
            # Only adjust if necessary (markers not visible)
            current_range = self.plot_item.viewRange()
            current_min, current_max = current_range[0]
            
            if min_time < current_min or max_time > current_max:
                self.plot_item.setXRange(min_time, max_time, padding=0.05)
                print(f"Adjusted view to show all jump markers: t=[{min_time:.2f}, {max_time:.2f}]") 