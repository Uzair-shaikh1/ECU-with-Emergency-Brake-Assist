import tkinter as tk
from tkinter import ttk
import csv
import os
import re
import time
import threading
from datetime import datetime

try:
    import serial
except ImportError:
    serial = None


# =====================================================
# USER SETTINGS
# =====================================================

# Keep this False if you only want to see dashboard design on PC
# Make this True when you connect STM32 to PC through USB
USE_SERIAL = False

# Change this when using STM32 on PC
# Example: COM3, COM4, COM5
SERIAL_PORT = "COM5"

BAUD_RATE = 115200

LOG_FOLDER = "logs"

NO_DATA_TIMEOUT = 3

# Expected STM32 output:
# Distance:90 cm I State: Warning I Speed:80 I Brake: 0

# =====================================================


def parse_stm32_line(line):
    pattern = r"Distance\s*:\s*(-?\d+)\s*cm\s*[|I]\s*State\s*:\s*([A-Za-z_]+)\s*[|I]\s*Speed\s*:\s*(-?\d+)\s*[|I]\s*Brake\s*:\s*(-?\d+)"
    match = re.search(pattern, line, re.IGNORECASE)

    if not match:
        return None

    distance = int(match.group(1))
    state = match.group(2).upper()
    speed = int(match.group(3))
    brake = int(match.group(4))

    return distance, state, speed, brake


def get_state_color(state):
    state = state.upper()

    if state == "NORMAL":
        return "#18d84f"
    elif state == "WARNING":
        return "#ffc400"
    elif state == "EMERGENCY":
        return "#ff3333"
    elif state in ["DISTANCE_ERROR", "NO_DATA", "ERROR"]:
        return "#ff3333"
    else:
        return "#aaaaaa"


def get_brake_status(brake):
    if brake == 1:
        return "ON"
    return "OFF"


def get_robot_action(state, speed, brake):
    state = state.upper()

    if brake == 1:
        return "Brake Applied"

    if state == "NORMAL":
        return "Moving Forward"
    elif state == "WARNING":
        return "Slow Speed"
    elif state == "EMERGENCY":
        return "Stopped"
    elif state == "DISTANCE_ERROR":
        return "Safe Stop"
    else:
        return "Unknown"


class SafetyDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Safety Supervisor ECU Dashboard - PC Preview")
        self.root.geometry("1000x600")
        self.root.configure(bg="#06111f")

        self.last_data_time = 0
        self.message_counter = 0
        self.serial_error = False

        os.makedirs(LOG_FOLDER, exist_ok=True)

        self.csv_filename = datetime.now().strftime(
            f"{LOG_FOLDER}/safety_dashboard_log_%Y-%m-%d_%H-%M-%S.csv"
        )

        self.csv_file = open(self.csv_filename, "w", newline="")
        self.csv_writer = csv.writer(self.csv_file)

        self.csv_writer.writerow([
            "PC_Time",
            "Distance_cm",
            "State",
            "Speed",
            "Brake_Value",
            "Brake_Status",
            "Robot_Action",
            "Source",
            "Raw_Line"
        ])

        self.build_ui()

        if USE_SERIAL:
            self.start_serial_thread()
        else:
            self.start_demo_thread()

        self.check_no_data()

    def build_ui(self):
        # Header
        header = tk.Frame(self.root, bg="#06111f")
        header.pack(fill="x", padx=20, pady=12)

        title = tk.Label(
            header,
            text="SAFETY SUPERVISOR ECU",
            fg="white",
            bg="#06111f",
            font=("Arial", 24, "bold")
        )
        title.pack(side="left")

        self.time_label = tk.Label(
            header,
            text="Time: -- | Msg: 0",
            fg="#9cc8ff",
            bg="#06111f",
            font=("Arial", 13, "bold")
        )
        self.time_label.pack(side="right")

        # Main frame
        main = tk.Frame(self.root, bg="#06111f")
        main.pack(fill="both", expand=True, padx=20, pady=5)

        left = tk.Frame(main, bg="#06111f")
        left.place(relx=0, rely=0, relwidth=0.47, relheight=0.65)

        right = tk.Frame(main, bg="#06111f")
        right.place(relx=0.49, rely=0, relwidth=0.51, relheight=0.65)

        bottom = tk.Frame(main, bg="#06111f")
        bottom.place(relx=0, rely=0.68, relwidth=1, relheight=0.32)

        # Distance card
        distance_card = self.card(left)
        distance_card.pack(fill="both", expand=True, pady=(0, 10))

        tk.Label(
            distance_card,
            text="LIDAR DISTANCE",
            fg="#b6c7e2",
            bg="#0b1b2e",
            font=("Arial", 13, "bold")
        ).pack(anchor="w", padx=18, pady=(16, 0))

        self.distance_label = tk.Label(
            distance_card,
            text="-- cm",
            fg="#18d84f",
            bg="#0b1b2e",
            font=("Arial", 60, "bold")
        )
        self.distance_label.pack(pady=15)

        self.distance_status_label = tk.Label(
            distance_card,
            text="Waiting for data",
            fg="#b6c7e2",
            bg="#0b1b2e",
            font=("Arial", 13)
        )
        self.distance_status_label.pack()

        # Small cards below distance
        left_row = tk.Frame(left, bg="#06111f")
        left_row.pack(fill="both", expand=True)

        self.link_card = self.small_card(left_row, "STM32 LINK", "DEMO" if not USE_SERIAL else "WAITING")
        self.link_card.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.log_card = self.small_card(left_row, "LOGGING", "ACTIVE")
        self.log_card.pack(side="left", fill="both", expand=True, padx=(5, 0))

        # Safety state card
        state_card = self.card(right)
        state_card.pack(fill="both", expand=True, pady=(0, 10))

        tk.Label(
            state_card,
            text="SAFETY STATE",
            fg="#b6c7e2",
            bg="#0b1b2e",
            font=("Arial", 13, "bold")
        ).pack(anchor="w", padx=18, pady=(16, 0))

        self.state_label = tk.Label(
            state_card,
            text="NO DATA",
            fg="#ff3333",
            bg="#0b1b2e",
            font=("Arial", 52, "bold")
        )
        self.state_label.pack(pady=18)

        self.action_label = tk.Label(
            state_card,
            text="Robot Action: --",
            fg="white",
            bg="#0b1b2e",
            font=("Arial", 16, "bold")
        )
        self.action_label.pack()

        # Speed and brake cards
        right_row = tk.Frame(right, bg="#06111f")
        right_row.pack(fill="both", expand=True)

        self.speed_card = self.small_card(right_row, "SPEED COMMAND", "--")
        self.speed_card.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.brake_card = self.small_card(right_row, "BRAKE STATUS", "--")
        self.brake_card.pack(side="left", fill="both", expand=True, padx=(5, 0))

        # Event log
        event_card = self.card(bottom)
        event_card.pack(fill="both", expand=True)

        tk.Label(
            event_card,
            text="EVENT LOG",
            fg="#b6c7e2",
            bg="#0b1b2e",
            font=("Arial", 11, "bold")
        ).pack(anchor="w", padx=12, pady=(7, 0))

        columns = ("time", "state", "distance", "speed", "brake", "source")
        self.tree = ttk.Treeview(event_card, columns=columns, show="headings", height=6)

        self.tree.heading("time", text="TIME")
        self.tree.heading("state", text="STATE")
        self.tree.heading("distance", text="DISTANCE")
        self.tree.heading("speed", text="SPEED")
        self.tree.heading("brake", text="BRAKE")
        self.tree.heading("source", text="SOURCE")

        self.tree.column("time", width=140)
        self.tree.column("state", width=160)
        self.tree.column("distance", width=120)
        self.tree.column("speed", width=100)
        self.tree.column("brake", width=100)
        self.tree.column("source", width=120)

        self.tree.pack(fill="both", expand=True, padx=12, pady=8)

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Treeview",
            background="#07111f",
            foreground="white",
            fieldbackground="#07111f",
            rowheight=25
        )
        style.configure(
            "Treeview.Heading",
            background="#102542",
            foreground="white",
            font=("Arial", 10, "bold")
        )

    def card(self, parent):
        return tk.Frame(
            parent,
            bg="#0b1b2e",
            highlightbackground="#1f4268",
            highlightthickness=1
        )

    def small_card(self, parent, title, value):
        frame = self.card(parent)

        tk.Label(
            frame,
            text=title,
            fg="#b6c7e2",
            bg="#0b1b2e",
            font=("Arial", 11, "bold")
        ).pack(anchor="w", padx=12, pady=(13, 0))

        value_label = tk.Label(
            frame,
            text=value,
            fg="#18d84f",
            bg="#0b1b2e",
            font=("Arial", 22, "bold")
        )
        value_label.pack(pady=22)

        frame.value_label = value_label
        return frame

    def start_demo_thread(self):
        thread = threading.Thread(target=self.demo_data_loop, daemon=True)
        thread.start()

    def demo_data_loop(self):
        demo_lines = [
            "Distance:130 cm I State: Normal I Speed:180 I Brake: 0",
            "Distance:90 cm I State: Warning I Speed:80 I Brake: 0",
            "Distance:45 cm I State: Warning I Speed:80 I Brake: 0",
            "Distance:18 cm I State: Emergency I Speed:0 I Brake: 1",
            "Distance:0 cm I State: Emergency I Speed:0 I Brake: 1"
        ]

        while True:
            for line in demo_lines:
                parsed = parse_stm32_line(line)
                if parsed:
                    distance, state, speed, brake = parsed
                    self.process_data(distance, state, speed, brake, line, "DEMO")
                time.sleep(1.5)

    def start_serial_thread(self):
        thread = threading.Thread(target=self.serial_loop, daemon=True)
        thread.start()

    def serial_loop(self):
        if serial is None:
            self.root.after(0, self.show_serial_error, "PY SERIAL MISSING")
            return

        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)
        except Exception:
            self.root.after(0, self.show_serial_error, "NO COM PORT")
            return

        while True:
            try:
                line = ser.readline().decode(errors="ignore").strip()

                if not line:
                    continue

                parsed = parse_stm32_line(line)

                if parsed:
                    distance, state, speed, brake = parsed
                    self.process_data(distance, state, speed, brake, line, "STM32")

            except Exception:
                self.root.after(0, self.show_serial_error, "SERIAL ERROR")
                time.sleep(1)

    def process_data(self, distance, state, speed, brake, raw_line, source):
        self.message_counter += 1
        self.last_data_time = time.time()

        now = datetime.now()
        pc_time = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        display_time = now.strftime("%H:%M:%S")

        distance_status = "Distance OK"

        if distance <= 0 or distance > 400:
            distance_status = "Distance Error"
            state = "DISTANCE_ERROR"
            speed = 0
            brake = 1

        brake_status = get_brake_status(brake)
        action = get_robot_action(state, speed, brake)
        color = get_state_color(state)

        self.csv_writer.writerow([
            pc_time,
            distance,
            state,
            speed,
            brake,
            brake_status,
            action,
            source,
            raw_line
        ])
        self.csv_file.flush()

        self.root.after(
            0,
            self.update_dashboard,
            distance,
            state,
            speed,
            brake_status,
            action,
            source,
            distance_status,
            display_time,
            color
        )

    def update_dashboard(self, distance, state, speed, brake_status, action, source, distance_status, display_time, color):
        self.distance_label.config(text=f"{distance} cm", fg=color)
        self.distance_status_label.config(text=distance_status)

        self.state_label.config(text=state, fg=color)
        self.action_label.config(text=f"Robot Action: {action}")

        self.link_card.value_label.config(
            text=source,
            fg="#18d84f" if source in ["STM32", "DEMO"] else "#ff3333"
        )

        self.log_card.value_label.config(text="ACTIVE", fg="#18d84f")

        self.speed_card.value_label.config(
            text=str(speed),
            fg="#18d84f" if speed > 0 else "#ff3333"
        )

        self.brake_card.value_label.config(
            text=brake_status,
            fg="#ff3333" if brake_status == "ON" else "#18d84f"
        )

        self.time_label.config(
            text=f"Time: {display_time} | Msg: {self.message_counter}"
        )

        self.tree.insert(
            "",
            0,
            values=(
                display_time,
                state,
                f"{distance} cm",
                speed,
                brake_status,
                source
            )
        )

        children = self.tree.get_children()
        if len(children) > 8:
            self.tree.delete(children[-1])

    def show_serial_error(self, text):
        self.state_label.config(text=text, fg="#ff3333")
        self.distance_status_label.config(text="Check STM32 USB connection")
        self.link_card.value_label.config(text="FAILED", fg="#ff3333")

    def check_no_data(self):
        if USE_SERIAL and self.last_data_time != 0:
            if time.time() - self.last_data_time > NO_DATA_TIMEOUT:
                self.state_label.config(text="NO DATA", fg="#ff3333")
                self.distance_status_label.config(text="No data from STM32")
                self.link_card.value_label.config(text="FAILED", fg="#ff3333")
                self.speed_card.value_label.config(text="0", fg="#ff3333")
                self.brake_card.value_label.config(text="ON", fg="#ff3333")
                self.action_label.config(text="Robot Action: Safe Stop")

        self.root.after(500, self.check_no_data)

    def close(self):
        try:
            self.csv_file.close()
        except Exception:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    app = SafetyDashboard(root)

    def on_close():
        app.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()