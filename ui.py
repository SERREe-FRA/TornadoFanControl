import ctypes
import mmap
import time
import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.animation as animation

class SharedData(ctypes.Structure):
    _fields_ = [
        ("cpuTemp", ctypes.c_double),
        ("gpuTemp", ctypes.c_double),
        ("cpuFanSpeed", ctypes.c_int),
        ("gpuFanSpeed", ctypes.c_int),

        ("cpu_hysteresis", ctypes.c_int),
        ("gpu_hysteresis", ctypes.c_int),

        ("cpu_temp_point_2", ctypes.c_int),
        ("cpu_temp_point_3", ctypes.c_int),
        ("cpu_temp_point_4", ctypes.c_int),

        ("gpu_temp_point_2", ctypes.c_int),
        ("gpu_temp_point_3", ctypes.c_int),
        ("gpu_temp_point_4", ctypes.c_int),

        ("cpu_fan_point_1", ctypes.c_int),
        ("cpu_fan_point_2", ctypes.c_int),
        ("cpu_fan_point_3", ctypes.c_int),
        ("cpu_fan_point_4", ctypes.c_int),
        ("cpu_fan_point_5", ctypes.c_int),

        ("gpu_fan_point_1", ctypes.c_int),
        ("gpu_fan_point_2", ctypes.c_int),
        ("gpu_fan_point_3", ctypes.c_int),
        ("gpu_fan_point_4", ctypes.c_int),
        ("gpu_fan_point_5", ctypes.c_int),

        ("write_sync", ctypes.c_bool),
    ]

try:
    shm = mmap.mmap(-1, ctypes.sizeof(SharedData), tagname="MySharedMemory", access=mmap.ACCESS_WRITE)
except Exception as e:
    print("Failed to open shared memory:", e)
    exit(1)

def read_shared_data():
    shm.seek(0)
    buf = shm.read(ctypes.sizeof(SharedData))
    return SharedData.from_buffer_copy(buf)

def write_shared_data(data):
    shm.seek(0)
    shm.write(bytes(data))

class FanControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Fan Control Curves")
        
        # Add protocol handler for window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Current editing values (local copy)
        self.edit_data = None
        self.dragging = None
        self.last_data_update = 0
        self.running = True  # Add this flag
        
        # Create the main frame
        main_frame = ttk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create control frame for buttons and settings
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Create apply button
        self.apply_button = ttk.Button(control_frame, text="Apply Changes", command=self.apply_changes)
        self.apply_button.pack(side=tk.LEFT)
        
        # Reset button
        self.reset_button = ttk.Button(control_frame, text="Reset", command=self.reset_curve)
        self.reset_button.pack(side=tk.LEFT, padx=(10, 0))
        
        # CPU Hysteresis
        ttk.Label(control_frame, text="CPU Hysteresis:").pack(side=tk.LEFT, padx=(20, 5))
        self.cpu_hysteresis_var = tk.IntVar()
        self.cpu_hysteresis_spinbox = ttk.Spinbox(control_frame, from_=0, to=10, width=5, 
                                                  textvariable=self.cpu_hysteresis_var,
                                                  command=self.on_hysteresis_change)
        self.cpu_hysteresis_spinbox.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(control_frame, text="°C").pack(side=tk.LEFT, padx=(0, 15))
        
        # GPU Hysteresis
        ttk.Label(control_frame, text="GPU Hysteresis:").pack(side=tk.LEFT, padx=(0, 5))
        self.gpu_hysteresis_var = tk.IntVar()
        self.gpu_hysteresis_spinbox = ttk.Spinbox(control_frame, from_=0, to=10, width=5,
                                                  textvariable=self.gpu_hysteresis_var,
                                                  command=self.on_hysteresis_change)
        self.gpu_hysteresis_spinbox.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(control_frame, text="°C").pack(side=tk.LEFT)

        # Create matplotlib figure with subplots
        self.fig, (self.ax1, self.ax2) = plt.subplots(1, 2, figsize=(12, 5))
        self.fig.suptitle("Fan Control Curves (Drag points to edit)")
        
        # Setup CPU plot
        self.ax1.set_title("CPU Fan Curve")
        self.ax1.set_xlabel("Temperature (°C)")
        self.ax1.set_ylabel("Fan Speed (%)")
        self.ax1.grid(True)
        self.ax1.set_xlim(0, 100)
        self.ax1.set_ylim(0, 100)
        
        # Setup GPU plot
        self.ax2.set_title("GPU Fan Curve")
        self.ax2.set_xlabel("Temperature (°C)")
        self.ax2.set_ylabel("Fan Speed (%)")
        self.ax2.grid(True)
        self.ax2.set_xlim(0, 100)
        self.ax2.set_ylim(0, 100)
        
        # Create canvas
        self.canvas = FigureCanvasTkAgg(self.fig, main_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Initialize lines
        self.cpu_line, = self.ax1.plot([], [], 'b-', linewidth=2, label='Fan Curve')
        self.cpu_point, = self.ax1.plot([], [], 'ro', markersize=8, label='Current Point')
        self.cpu_edit_points, = self.ax1.plot([], [], 'go', markersize=10, picker=True, label='Edit Points')
        
        self.gpu_line, = self.ax2.plot([], [], 'g-', linewidth=2, label='Fan Curve')
        self.gpu_point, = self.ax2.plot([], [], 'ro', markersize=8, label='Current Point')
        self.gpu_edit_points, = self.ax2.plot([], [], 'go', markersize=10, picker=True, label='Edit Points')
        
        self.ax1.legend()
        self.ax2.legend()
        
        # Connect mouse events
        self.canvas.mpl_connect('button_press_event', self.on_press)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.canvas.mpl_connect('button_release_event', self.on_release)
        
        # Start timer-based updates instead of animation
        self.update_ui()

    def update_ui(self):
        # Check if we should still be running and if window still exists
        if not self.running or not self.root.winfo_exists():
            return
            
        current_time = time.time()
        
        try:
            # Update data from shared memory every 500ms or when dragging
            if current_time - self.last_data_update > 0.5 or self.edit_data is None:
                data = read_shared_data()
                
                # Update local edit data if not currently editing
                if self.edit_data is None:
                    self.edit_data = data
                    # Update hysteresis spinboxes with current values
                    self.cpu_hysteresis_var.set(self.edit_data.cpu_hysteresis)
                    self.gpu_hysteresis_var.set(self.edit_data.gpu_hysteresis)
                
                # Update titles with current values
                self.ax1.set_title(f"CPU: {data.cpuTemp:.1f}°C, {data.cpuFanSpeed}% (Hyst: {self.edit_data.cpu_hysteresis}°C)")
                self.ax2.set_title(f"GPU: {data.gpuTemp:.1f}°C, {data.gpuFanSpeed}% (Hyst: {self.edit_data.gpu_hysteresis}°C)")
                
                # Update current point positions
                self.cpu_point.set_data([data.cpuTemp], [data.cpuFanSpeed])
                self.gpu_point.set_data([data.gpuTemp], [data.gpuFanSpeed])
                
                self.last_data_update = current_time
            
            # Always update curves (for smooth dragging)
            cpu_temps = [0, self.edit_data.cpu_temp_point_2, self.edit_data.cpu_temp_point_3, self.edit_data.cpu_temp_point_4, 100]
            cpu_fans = [self.edit_data.cpu_fan_point_1, self.edit_data.cpu_fan_point_2, self.edit_data.cpu_fan_point_3, self.edit_data.cpu_fan_point_4, self.edit_data.cpu_fan_point_5]
            
            gpu_temps = [0, self.edit_data.gpu_temp_point_2, self.edit_data.gpu_temp_point_3, self.edit_data.gpu_temp_point_4, 100]
            gpu_fans = [self.edit_data.gpu_fan_point_1, self.edit_data.gpu_fan_point_2, self.edit_data.gpu_fan_point_3, self.edit_data.gpu_fan_point_4, self.edit_data.gpu_fan_point_5]
            
            # Update CPU curve
            self.cpu_line.set_data(cpu_temps, cpu_fans)
            self.cpu_edit_points.set_data(cpu_temps, cpu_fans)
            
            # Update GPU curve
            self.gpu_line.set_data(gpu_temps, gpu_fans)
            self.gpu_edit_points.set_data(gpu_temps, gpu_fans)
            
            # Only redraw when necessary
            self.canvas.draw_idle()
            
        except Exception as e:
            print(f"Error updating UI: {e}")
            return  # Don't schedule next update on error
        
        # Schedule next update - faster when dragging for responsiveness
        if self.running and self.root.winfo_exists():  # Check both conditions
            if self.dragging is not None:
                self.root.after(16, self.update_ui)  # ~60 FPS when dragging
            else:
                self.root.after(100, self.update_ui)  # 10 FPS when idle

    def update_plots(self, frame):
        try:
            data = read_shared_data()
            
            # Update local edit data if not currently editing
            if self.edit_data is None:
                self.edit_data = data
            
            # CPU curve points (temp, fan%)
            cpu_temps = [0, self.edit_data.cpu_temp_point_2, self.edit_data.cpu_temp_point_3, self.edit_data.cpu_temp_point_4, 100]
            cpu_fans = [self.edit_data.cpu_fan_point_1, self.edit_data.cpu_fan_point_2, self.edit_data.cpu_fan_point_3, self.edit_data.cpu_fan_point_4, self.edit_data.cpu_fan_point_5]
            
            # GPU curve points (temp, fan%)
            gpu_temps = [0, self.edit_data.gpu_temp_point_2, self.edit_data.gpu_temp_point_3, self.edit_data.gpu_temp_point_4, 100]
            gpu_fans = [self.edit_data.gpu_fan_point_1, self.edit_data.gpu_fan_point_2, self.edit_data.gpu_fan_point_3, self.edit_data.gpu_fan_point_4, self.edit_data.gpu_fan_point_5]
            
            # Update CPU curve
            self.cpu_line.set_data(cpu_temps, cpu_fans)
            self.cpu_point.set_data([data.cpuTemp], [data.cpuFanSpeed])
            self.cpu_edit_points.set_data(cpu_temps, cpu_fans)
            
            # Update GPU curve
            self.gpu_line.set_data(gpu_temps, gpu_fans)
            self.gpu_point.set_data([data.gpuTemp], [data.gpuFanSpeed])
            self.gpu_edit_points.set_data(gpu_temps, gpu_fans)
            
            # Update titles with current values
            self.ax1.set_title(f"CPU: {data.cpuTemp:.1f}°C, {data.cpuFanSpeed}%")
            self.ax2.set_title(f"GPU: {data.gpuTemp:.1f}°C, {data.gpuFanSpeed}%")
            
        except Exception as e:
            print(f"Error updating plots: {e}")
        
        return self.cpu_line, self.cpu_point, self.gpu_line, self.gpu_point, self.cpu_edit_points, self.gpu_edit_points

    def on_press(self, event):
        if event.inaxes not in [self.ax1, self.ax2]:
            return
        
        # Find closest point
        if event.inaxes == self.ax1:
            temps = [0, self.edit_data.cpu_temp_point_2, self.edit_data.cpu_temp_point_3, self.edit_data.cpu_temp_point_4, 100]
            fans = [self.edit_data.cpu_fan_point_1, self.edit_data.cpu_fan_point_2, self.edit_data.cpu_fan_point_3, self.edit_data.cpu_fan_point_4, self.edit_data.cpu_fan_point_5]
            curve_type = 'cpu'
        else:
            temps = [0, self.edit_data.gpu_temp_point_2, self.edit_data.gpu_temp_point_3, self.edit_data.gpu_temp_point_4, 100]
            fans = [self.edit_data.gpu_fan_point_1, self.edit_data.gpu_fan_point_2, self.edit_data.gpu_fan_point_3, self.edit_data.gpu_fan_point_4, self.edit_data.gpu_fan_point_5]
            curve_type = 'gpu'
        
        # Find closest point (exclude fixed points 0 and 4)
        min_dist = float('inf')
        closest_idx = None
        for i in range(1, 4):  # Only points 1, 2, 3 are editable
            dist = ((temps[i] - event.xdata)**2 + (fans[i] - event.ydata)**2)**0.5
            if dist < min_dist and dist < 5:  # 5 unit tolerance
                min_dist = dist
                closest_idx = i
        
        if closest_idx is not None:
            self.dragging = (curve_type, closest_idx)

    def on_motion(self, event):
        if self.dragging is None or event.inaxes not in [self.ax1, self.ax2]:
            return
        
        curve_type, point_idx = self.dragging
        new_x = max(0, min(100, event.xdata))
        new_y = max(0, min(100, event.ydata))
        
        if curve_type == 'cpu':
            if point_idx == 1:
                self.edit_data.cpu_temp_point_2 = int(new_x)
                self.edit_data.cpu_fan_point_2 = int(new_y)
            elif point_idx == 2:
                self.edit_data.cpu_temp_point_3 = int(new_x)
                self.edit_data.cpu_fan_point_3 = int(new_y)
            elif point_idx == 3:
                self.edit_data.cpu_temp_point_4 = int(new_x)
                self.edit_data.cpu_fan_point_4 = int(new_y)
        else:  # gpu
            if point_idx == 1:
                self.edit_data.gpu_temp_point_2 = int(new_x)
                self.edit_data.gpu_fan_point_2 = int(new_y)
            elif point_idx == 2:
                self.edit_data.gpu_temp_point_3 = int(new_x)
                self.edit_data.gpu_fan_point_3 = int(new_y)
            elif point_idx == 3:
                self.edit_data.gpu_temp_point_4 = int(new_x)
                self.edit_data.gpu_fan_point_4 = int(new_y)

    def on_release(self, event):
        self.dragging = None

    def reset_curve(self):
        if self.edit_data is not None:
            # Set linear curve from 0 to 100
            # Temperature points: 0, 25, 50, 75, 100
            self.edit_data.cpu_temp_point_2 = 60
            self.edit_data.cpu_temp_point_3 = 80
            self.edit_data.cpu_temp_point_4 = 95
            
            self.edit_data.gpu_temp_point_2 = 50
            self.edit_data.gpu_temp_point_3 = 70
            self.edit_data.gpu_temp_point_4 = 85
            
            # Fan points: 0, 25, 50, 75, 100 (linear)
            self.edit_data.cpu_fan_point_1 = 0
            self.edit_data.cpu_fan_point_2 = 5
            self.edit_data.cpu_fan_point_3 = 10
            self.edit_data.cpu_fan_point_4 = 30
            self.edit_data.cpu_fan_point_5 = 100
            
            self.edit_data.gpu_fan_point_1 = 0
            self.edit_data.gpu_fan_point_2 = 5
            self.edit_data.gpu_fan_point_3 = 10
            self.edit_data.gpu_fan_point_4 = 30
            self.edit_data.gpu_fan_point_5 = 100
            
            # Reset hysteresis to 3
            self.edit_data.cpu_hysteresis = 3
            self.edit_data.gpu_hysteresis = 3
            
            # Update spinboxes
            self.cpu_hysteresis_var.set(3)
            self.gpu_hysteresis_var.set(3)

    def on_hysteresis_change(self):
        if self.edit_data is not None:
            # Update hysteresis values in edit_data
            self.edit_data.cpu_hysteresis = self.cpu_hysteresis_var.get()
            self.edit_data.gpu_hysteresis = self.gpu_hysteresis_var.get()

    def apply_changes(self):
        if self.edit_data is not None:
            # Update hysteresis values from spinboxes
            self.edit_data.cpu_hysteresis = self.cpu_hysteresis_var.get()
            self.edit_data.gpu_hysteresis = self.gpu_hysteresis_var.get()
            
            self.edit_data.write_sync = True
            write_shared_data(self.edit_data)
            print(f"Changes applied! CPU Hyst: {self.edit_data.cpu_hysteresis}°C, GPU Hyst: {self.edit_data.gpu_hysteresis}°C")

    def on_closing(self):
        """Handle window close event"""
        self.running = False  # Stop the update loop
        try:
            # Save current settings before closing
            if self.edit_data is not None:
                self.edit_data.write_sync = True
                write_shared_data(self.edit_data)
        except Exception as e:
            print(f"Error saving on close: {e}")
        finally:
            # Clean exit
            self.root.quit()
            # Remove destroy() and sys.exit() to prevent conflicts


if __name__ == "__main__":
    root = tk.Tk()
    app = FanControlGUI(root)
    root.mainloop()
