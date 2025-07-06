"""
Manages memory-bounded data buffers for force plate data acquisition.
Provides circular buffers to prevent unbounded memory growth during long sessions.
"""
import numpy as np
from collections import deque
import config


class BufferManager:
    """
    Manages time and force data buffers with bounded memory usage.
    Uses circular buffers (deque) to prevent memory leaks during extended acquisitions.
    """
    
    def __init__(self, sample_rate, num_channels, max_duration_seconds=300):
        """
        Initialize the buffer manager.
        
        Args:
            sample_rate: Sampling rate in Hz
            num_channels: Number of force channels
            max_duration_seconds: Maximum buffer duration in seconds (default 5 minutes)
        """
        self.sample_rate = sample_rate
        self.num_channels = num_channels
        self.max_duration_seconds = max_duration_seconds
        
        # Calculate maximum number of samples to store
        self.max_samples = int(sample_rate * max_duration_seconds)
        
        # Initialize circular buffers using deque
        # These will automatically discard oldest data when full
        self._time_buffer = deque(maxlen=self.max_samples)
        self._force_buffers = [deque(maxlen=self.max_samples) for _ in range(num_channels)]
        
        # For efficient chunk appending, we'll temporarily store chunks
        self._time_chunks = []
        self._force_chunks = []
        
    def reset(self):
        """Clear all buffers and reset to initial state."""
        self._time_buffer.clear()
        for buffer in self._force_buffers:
            buffer.clear()
        self._time_chunks.clear()
        self._force_chunks.clear()
        
    def append_chunk(self, time_chunk, force_chunk_multi_channel):
        """
        Append a new chunk of data to the buffers.
        
        Args:
            time_chunk: 1D array of timestamps
            force_chunk_multi_channel: 2D array [chunk_size, num_channels]
        """
        # Validate input
        if force_chunk_multi_channel.shape[1] != self.num_channels:
            raise ValueError(f"Expected {self.num_channels} channels, got {force_chunk_multi_channel.shape[1]}")
        
        # Store chunks for efficient retrieval
        self._time_chunks.append(time_chunk)
        self._force_chunks.append(force_chunk_multi_channel)
        
        # Add to circular buffers
        self._time_buffer.extend(time_chunk)
        
        # Transpose for easier channel-wise storage
        forces_by_channel = force_chunk_multi_channel.T
        for i in range(self.num_channels):
            self._force_buffers[i].extend(forces_by_channel[i])
            
    def get_full_data(self):
        """
        Get all buffered data as numpy arrays.
        
        Returns:
            tuple: (time_array, force_array_multi_channel) or (None, None) if empty
                   time_array: 1D array of timestamps
                   force_array_multi_channel: 2D array [samples, channels]
        """
        if not self._time_buffer:
            return None, None
            
        # Convert deques to numpy arrays
        time_array = np.array(self._time_buffer)
        
        # Stack channel data into 2D array
        force_array = np.column_stack([np.array(buffer) for buffer in self._force_buffers])
        
        return time_array, force_array
        
    def get_recent_data(self, duration_seconds):
        """
        Get the most recent data within the specified duration.
        
        Args:
            duration_seconds: How many seconds of recent data to retrieve
            
        Returns:
            tuple: (time_array, force_array_multi_channel) or (None, None) if empty
        """
        if not self._time_buffer:
            return None, None
            
        # Calculate how many samples to retrieve
        num_samples = min(int(duration_seconds * self.sample_rate), len(self._time_buffer))
        
        # Get recent samples from the end of buffers
        time_array = np.array(list(self._time_buffer))[-num_samples:]
        
        # Stack channel data
        force_arrays = []
        for buffer in self._force_buffers:
            force_arrays.append(np.array(list(buffer))[-num_samples:])
        force_array = np.column_stack(force_arrays)
        
        return time_array, force_array
        
    def get_summed_force_history(self, num_samples):
        """
        Get recent summed force data for jump detection.
        
        Args:
            num_samples: Number of recent samples to retrieve
            
        Returns:
            1D array of summed forces or None if insufficient data
        """
        if len(self._time_buffer) < num_samples:
            return None
            
        # Get recent force data and sum across channels
        force_arrays = []
        for buffer in self._force_buffers:
            force_arrays.append(np.array(list(buffer))[-num_samples:])
        
        # Sum across channels (axis=1 after stacking)
        summed_force = np.sum(np.column_stack(force_arrays), axis=1)
        
        return summed_force
        
    def get_buffer_size(self):
        """Get current number of samples in buffers."""
        return len(self._time_buffer)
        
    def get_chunks_for_analysis(self):
        """
        Get stored chunks for efficient batch analysis.
        Returns the raw chunks as they were appended.
        
        Returns:
            tuple: (time_chunks_list, force_chunks_list)
        """
        return self._time_chunks.copy(), self._force_chunks.copy()