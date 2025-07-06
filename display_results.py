from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import QApplication, QMainWindow, QTextEdit

class ResultsDisplay(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jump Analysis Results")
        self.results_display = QTextEdit()
        self.setCentralWidget(self.results_display)
        self.resize(600, 400)
        
    def update_status(self, message):
        """Updates status bar with the given message."""
        self.statusBar().showMessage(message)
        
    @pyqtSlot(dict)
    def display_results(self, results_dict):
        """Displays the analysis results in the text area, appending new results."""
        if not results_dict:
            # Append a message if the dictionary is empty (e.g., analysis failed early)
            self.results_display.append("--- Analysis Attempt Failed ---")
            return

        # Try to find a jump number in the keys to format the header
        jump_num_str = ""
        for key in results_dict.keys():
            if key.startswith("Jump #"):
                try:
                    jump_num_str = key.split(" ")[1] # Extract '#N'
                    break
                except IndexError:
                    pass # Malformed key, ignore

        if jump_num_str:
            results_text = f"--- JUMP {jump_num_str} RESULTS ---\n"
        else:
            results_text = "--- JUMP RESULTS ---\n" # Fallback header
        
        # Log all keys in results_dict for debugging
        print(f"DEBUG - Results dictionary keys: {list(results_dict.keys())}")
        
        # Extract important metrics first to display prominently
        flight_time = None
        flight_height = None
        impulse_height = None
        bodyweight = None
        
        # Direct key access for cleaner code
        for key, value in results_dict.items():
            if not isinstance(value, (int, float)):
                continue
                
            if "Flight Time" in key:
                flight_time = value
            elif "Jump Height (Flight Time)" in key:
                flight_height = value
            elif "Jump Height (Impulse)" in key:
                impulse_height = value
            elif "Body Weight" in key:
                bodyweight = value
                
        # Display metrics in a clear, consistent format
        if flight_time:
            results_text += f"FLIGHT TIME: {flight_time:.3f} s\n"
            
        if flight_height:
            results_text += f"JUMP HEIGHT (Flight Time): {flight_height:.3f} m\n"
            self.update_status(f"Jump Height: {flight_height:.3f} m (Flight Time)")
            
        if impulse_height:
            results_text += f"JUMP HEIGHT (Impulse): {impulse_height:.3f} m\n"
            
        if bodyweight:
            results_text += f"BODY WEIGHT: {bodyweight:.1f} N\n"
            
        # Add a blank line after key metrics
        if flight_time or flight_height or impulse_height:
            results_text += "\n"
        else:
            results_text += "No jump height detected. Check threshold settings.\n\n"
            print(f"DEBUG - Results values: {results_dict}")
            
        # Check for any error messages
        impulse_error = None
        for key, value in results_dict.items():
            if "Error" in key:
                impulse_error = value
                break
                
        if impulse_error:
            results_text += f"Impulse calculation issue: {impulse_error}\n\n"

        # Display the rest of the results
        for key, value in results_dict.items():
            # Skip the key metrics we already displayed
            if ("Flight Time" in key or 
                "Jump Height (Flight Time)" in key or 
                "Jump Height (Impulse)" in key or
                "Body Weight" in key or
                "Error" in key):
                continue

            # Remove the jump number prefix for cleaner display
            display_key = key
            if jump_num_str and key.startswith(f"Jump {jump_num_str}"):
                display_key = key.replace(f"Jump {jump_num_str} ", "", 1)

            # Format floats nicely
            if isinstance(value, float):
                results_text += f"{display_key}: {value:.3f}\n"
            else:
                results_text += f"{display_key}: {value}\n"

        self.results_display.append(results_text) # Use append instead of setText
        self.update_status("Analysis results updated.") 

# For standalone testing
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = ResultsDisplay()
    window.show()
    
    # Test with sample data
    test_results = {
        "Jump #1 Flight Time (s)": 0.5,
        "Jump #1 Jump Height (Flight Time) (m)": 0.3,
        "Jump #1 Jump Height (Impulse) (m)": 0.32,
        "Jump #1 Body Weight (N)": 750.0,
        "Jump #1 Peak Force (N)": 1500.0
    }
    window.display_results(test_results)
    
    sys.exit(app.exec()) 