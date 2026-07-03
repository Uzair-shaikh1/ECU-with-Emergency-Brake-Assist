import tkinter as tk
import csv
import math
import re
import time
import glob
import threading
from pathlib import Path
from datetime import datetime

# ==========================================================
# SAFETY SUPERVISOR ECU DASHBOARD
# Raspberry Pi 7-inch Touch Display Version: 800 x 480
# ----------------------------------------------------------
# Connection:
#   STM32 USB cable -> Raspberry Pi USB port
#
# Expected STM32 serial output:
#   Distance:90 cm I State: Warning I Speed:80 I Brake: 0
#
# Speed unit:
#   PWM command from motor code
#
# Exit:
#   Press q to close
#   Press Esc to exit fullscreen
#   Press F11 to toggle fullscreen
# ==========================================================

# ---------------- USER SETTINGS ----------------
BAUD_RATE = 115200

# False = read real STM32 serial data
# True  = run without STM32 for dashboard testing
DEMO_MODE = False

START_FULLSCREEN = True
FORCE_FULLSCREEN = True

SCREEN_W = 800
SCREEN_H = 480

SPEED_UNIT = "PWM"
MIN_PWM = 0
MAX_PWM = 180

NO_DATA_TIMEOUT_SEC = 3
LOG_FOLDER_NAME = "logs"

# ---------------- COLORS ----------------
BG = "#06111d"
PANEL = "#0a1828"
PANEL_2 = "#0f2032"
INNER = "#122233"
BORDER = "#29415a"
TEXT = "#eef5ff"
MUTED = "#b4c0ce"
BLUE = "#68bbff"
GREEN = "#84da4e"
YELLOW = "#f4c142"
RED = "#f05c4d"
GRID = "#20374d"
SOFT_WARN = "#1b2220"
SOFT_LINE = "#1b3145"


# ---------------- HELPER FUNCTIONS ----------------
def find_serial_port():
    ports = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    if not ports:
        return None
    return ports[0]


def parse_stm32_line(line):
    """
    Accepted formats:
      Distance:90 cm I State: Warning I Speed:80 I Brake: 0
      Distance:90 cm | State: Warning | Speed:80 | Brake: 0
    """
    pattern = (
        r"Distance\s*:\s*(-?\d+)\s*cm\s*[|I]\s*"
        r"State\s*:\s*([A-Za-z_]+)\s*[|I]\s*"
        r"Speed\s*:\s*(-?\d+(?:\.\d+)?)\s*[|I]\s*"
        r"Brake\s*:\s*(-?\d+)"
    )

    match = re.search(pattern, line, re.IGNORECASE)
    if not match:
        return None

    distance = int(match.group(1))
    state = match.group(2).upper()
    pwm = float(match.group(3))
    brake = int(match.group(4))

    pwm = max(MIN_PWM, min(MAX_PWM, pwm))
    return distance, state, pwm, brake


def state_color(state):
    state = state.upper()
    if state == "NORMAL":
        return GREEN
    if state == "WARNING":
        return YELLOW
    if state in ["EMERGENCY", "DISTANCE_ERROR", "NO_DATA", "NO_STM32", "ERROR"]:
        return RED
    return MUTED


def brake_status(brake):
    return "ON" if int(brake) == 1 else "OFF"


def robot_action(state, brake):
    state = state.upper()

    if int(brake) == 1:
        return "Brake Applied"
    if state == "NORMAL":
        return "Moving Forward"
    if state == "WARNING":
        return "Slow Speed"
    if state == "EMERGENCY":
        return "Stopped"
    if state == "DISTANCE_ERROR":
        return "Safe Stop"
    return "Unknown"


def status_details(state):
    state = state.upper()

    if state == "NORMAL":
        return "All clear. Path is clear."
    if state == "WARNING":
        return "Obstacle detected. Reducing speed."
    if state == "EMERGENCY":
        return "Emergency! Brake applied."
    if state == "DISTANCE_ERROR":
        return "Invalid distance. Safe stop enabled."
    return "System status updated."


# ---------------- MAIN DASHBOARD CLASS ----------------
class SafetyDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Safety Supervisor ECU Dashboard")
        self.root.configure(bg=BG)

        self.message_counter = 0
        self.last_data_time = 0
        self.serial_port = None
        self.ser = None
        self.event_rows = []
        self.last_raw_line = ""

        # CSV log setup
        script_dir = Path(__file__).resolve().parent
        self.log_dir = script_dir / LOG_FOLDER_NAME
        self.log_dir.mkdir(exist_ok=True)

        self.csv_filename = self.log_dir / datetime.now().strftime(
            "safety_dashboard_pi_pwm_%Y-%m-%d_%H-%M-%S.csv"
        )

        self.csv_file = open(self.csv_filename, "w", newline="")
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow([
            "PC_Time",
            "Distance_cm",
            "State",
            "Speed_PWM",
            "Brake_Value",
            "Brake_Status",
            "Robot_Action",
            "STM32_Link",
            "Raw_Line"
        ])

        # Window / fullscreen setup
        self.root.geometry(f"{SCREEN_W}x{SCREEN_H}+0+0")

        if START_FULLSCREEN:
            self.force_fullscreen()

        self.root.bind("<Escape>", self.exit_fullscreen)
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("q", lambda event: self.close_and_exit())

        if FORCE_FULLSCREEN:
            self.root.after(700, self.force_fullscreen)

        self.build_ui()

        if DEMO_MODE:
            self.set_header_status("DEMO", GREEN)
            self.start_demo_thread()
        else:
            self.set_header_status("SEARCH", YELLOW)
            self.start_serial_thread()

        self.check_no_data()

    # ---------------- FULLSCREEN ----------------
    def force_fullscreen(self, event=None):
        self.root.update_idletasks()
        self.root.geometry(f"{SCREEN_W}x{SCREEN_H}+0+0")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.lift()
        self.root.focus_force()

    def exit_fullscreen(self, event=None):
        self.root.overrideredirect(False)
        self.root.attributes("-fullscreen", False)
        self.root.attributes("-topmost", False)

    def toggle_fullscreen(self, event=None):
        current = self.root.attributes("-fullscreen")
        if current:
            self.exit_fullscreen()
        else:
            self.force_fullscreen()

    # ---------------- UI BUILD ----------------
    def build_ui(self):
        self.header = tk.Frame(self.root, bg=BG)
        self.header.place(x=0, y=0, width=800, height=50)
        self.draw_header()

        self.card_state = self.make_card(8, 58, 325, 122)
        self.card_speed = self.make_card(342, 58, 450, 122)

        self.card_system = self.make_card(8, 188, 195, 140)
        self.card_obstacle = self.make_card(213, 188, 355, 140)
        self.card_status = self.make_card(578, 188, 214, 140)

        self.card_log = self.make_card(8, 336, 784, 136)

        self.build_state_card()
        self.build_speed_card()
        self.build_system_card()
        self.build_obstacle_card()
        self.build_status_card()
        self.build_event_log()

    def make_card(self, x, y, w, h):
        frame = tk.Frame(
            self.root,
            bg=PANEL,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        frame.place(x=x, y=y, width=w, height=h)
        return frame

    def section_title(self, parent, text, x=10, y=7):
        label = tk.Label(
            parent,
            text=text,
            fg=TEXT,
            bg=PANEL,
            font=("DejaVu Sans", 8, "bold")
        )
        label.place(x=x, y=y)
        return label

    # ---------------- HEADER ----------------
    def draw_header(self):
        self.header_canvas = tk.Canvas(self.header, bg=BG, highlightthickness=0)
        self.header_canvas.pack(fill="both", expand=True)

        self.header_canvas.create_line(0, 49, 800, 49, fill=BORDER)

        self.header_canvas.create_oval(10, 9, 40, 39, outline=BLUE, width=2)
        self.header_canvas.create_text(25, 24, text="✓", fill=BLUE, font=("DejaVu Sans", 17, "bold"))

        # Title shortened in font size and status pills moved right so "ECU" is fully visible
        self.header_canvas.create_text(
            48, 24,
            text="SAFETY SUPERVISOR ECU",
            fill=TEXT,
            font=("DejaVu Sans", 15, "bold"),
            anchor="w"
        )

        self.draw_status_pill(405, 12, 125, "STM32:", "SEARCH", "stm32")
        self.draw_status_pill(540, 12, 112, "LOG:", "ACTIVE", "log")

        self.time_header = self.header_canvas.create_text(
            788, 24,
            text=datetime.now().strftime("%I:%M:%S %p"),
            fill=TEXT,
            font=("DejaVu Sans", 9, "bold"),
            anchor="e"
        )

    def draw_status_pill(self, x, y, w, label, value, key):
        self.header_canvas.create_rectangle(
            x, y, x + w, y + 28,
            outline=BORDER,
            fill="#0b1a22",
            width=1
        )

        dot_id = self.header_canvas.create_text(
            x + 8, y + 14,
            text="●",
            fill=GREEN,
            font=("DejaVu Sans", 7, "bold"),
            anchor="w"
        )

        self.header_canvas.create_text(
            x + 20, y + 14,
            text=label,
            fill=TEXT,
            font=("DejaVu Sans", 7, "bold"),
            anchor="w"
        )

        value_id = self.header_canvas.create_text(
            x + 66, y + 14,
            text=value,
            fill=GREEN,
            font=("DejaVu Sans", 7, "bold"),
            anchor="w"
        )

        if key == "stm32":
            self.stm32_dot_id = dot_id
            self.stm32_value_id = value_id
        elif key == "log":
            self.log_dot_id = dot_id
            self.log_value_id = value_id

    def set_header_status(self, text, color):
        try:
            self.header_canvas.itemconfig(self.stm32_value_id, text=text, fill=color)
            self.header_canvas.itemconfig(self.stm32_dot_id, fill=color)
        except Exception:
            pass

    # ---------------- STATE CARD ----------------
    def build_state_card(self):
        self.section_title(self.card_state, "SAFETY STATE", x=112, y=7)

        self.state_canvas = tk.Canvas(self.card_state, bg=PANEL, highlightthickness=0)
        self.state_canvas.place(x=10, y=28, width=305, height=68)

        self.legend_canvas = tk.Canvas(self.card_state, bg=PANEL, highlightthickness=0)
        self.legend_canvas.place(x=10, y=98, width=305, height=20)

        self.draw_state_box("NO_DATA", "Action: --")
        self.draw_legend()

    def draw_state_box(self, state, action_text):
        c = self.state_canvas
        c.delete("all")

        color = state_color(state)
        fill_color = SOFT_WARN if state == "WARNING" else INNER

        c.create_rectangle(0, 0, 305, 68, fill=fill_color, outline=SOFT_LINE)

        if state == "NORMAL":
            c.create_text(38, 34, text="✓", fill=color, font=("DejaVu Sans", 28, "bold"))
        elif state == "WARNING":
            c.create_polygon(38, 11, 18, 55, 58, 55, outline=color, fill="", width=3)
            c.create_text(38, 39, text="!", fill=color, font=("DejaVu Sans", 20, "bold"))
        elif state in ["EMERGENCY", "DISTANCE_ERROR", "NO_DATA", "NO_STM32", "ERROR"]:
            c.create_oval(16, 12, 60, 56, outline=color, width=3)
            c.create_text(38, 36, text="!", fill=color, font=("DejaVu Sans", 20, "bold"))
        else:
            c.create_text(38, 36, text="?", fill=color, font=("DejaVu Sans", 22, "bold"))

        c.create_rectangle(88, 10, 255, 50, fill="#10253b", outline="")

        # Reduce font for long states
        if len(state) > 9:
            state_font = ("DejaVu Sans", 15, "bold")
        else:
            state_font = ("DejaVu Sans", 19, "bold")

        c.create_text(171, 28, text=state, fill=color, font=state_font)
        c.create_text(171, 52, text=action_text, fill=TEXT, font=("DejaVu Sans", 8))

    def draw_legend(self):
        c = self.legend_canvas
        c.delete("all")

        items = [
            ("✓", "NORMAL", GREEN),
            ("⚠", "WARNING", YELLOW),
            ("!", "EMERGENCY", RED)
        ]

        x = 15
        for icon, label, color in items:
            c.create_text(x, 10, text=icon, fill=color, font=("DejaVu Sans", 9, "bold"))
            c.create_text(x + 16, 10, text=label, fill=color, font=("DejaVu Sans", 7, "bold"), anchor="w")
            x += 102

    # ---------------- SPEED CARD ----------------
    def build_speed_card(self):
        self.section_title(self.card_speed, "SPEED COMMAND", x=12, y=7)

        self.speed_canvas = tk.Canvas(self.card_speed, bg=PANEL, highlightthickness=0)
        self.speed_canvas.place(x=8, y=25, width=158, height=90)

        self.speed_info_panel = tk.Frame(
            self.card_speed,
            bg=PANEL_2,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        self.speed_info_panel.place(x=178, y=33, width=105, height=72)

        tk.Label(
            self.speed_info_panel,
            text="MOTOR SPEED",
            fg=TEXT,
            bg=PANEL_2,
            font=("DejaVu Sans", 7, "bold")
        ).place(x=8, y=7)

        self.speed_value_label = tk.Label(
            self.speed_info_panel,
            text="0",
            fg=BLUE,
            bg=PANEL_2,
            font=("DejaVu Sans", 17, "bold")
        )
        self.speed_value_label.place(x=8, y=23)

        tk.Label(
            self.speed_info_panel,
            text=SPEED_UNIT,
            fg=MUTED,
            bg=PANEL_2,
            font=("DejaVu Sans", 7, "bold")
        ).place(x=65, y=34)

        tk.Label(
            self.speed_info_panel,
            text="SOURCE",
            fg=MUTED,
            bg=PANEL_2,
            font=("DejaVu Sans", 6, "bold")
        ).place(x=8, y=55)

        self.speed_source_label = tk.Label(
            self.speed_info_panel,
            text="MOTOR CMD",
            fg=GREEN,
            bg=PANEL_2,
            font=("DejaVu Sans", 6, "bold")
        )
        self.speed_source_label.place(x=50, y=55)

        self.brake_panel = tk.Frame(
            self.card_speed,
            bg=PANEL_2,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        self.brake_panel.place(x=305, y=33, width=125, height=72)

        tk.Label(
            self.brake_panel,
            text="BRAKE STATUS",
            fg=TEXT,
            bg=PANEL_2,
            font=("DejaVu Sans", 7, "bold")
        ).place(x=8, y=8)

        tk.Label(
            self.brake_panel,
            text="!",
            fg=RED,
            bg=PANEL_2,
            font=("DejaVu Sans", 16, "bold")
        ).place(x=17, y=33)

        self.brake_value = tk.Label(
            self.brake_panel,
            text="--",
            fg=RED,
            bg=PANEL_2,
            font=("DejaVu Sans", 18, "bold")
        )
        self.brake_value.place(x=47, y=28)

    def draw_speed_gauge(self, pwm):
        c = self.speed_canvas
        c.delete("all")

        cx, cy, r = 79, 50, 43
        start_deg = 225
        end_deg = -45

        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#6f8294", width=2)
        c.create_oval(cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5, outline="#21384d", width=2)

        # Ticks: 0 to 180 PWM
        for i in range(0, 37):
            val = i * 5
            theta = math.radians(start_deg + (val / MAX_PWM) * (end_deg - start_deg))

            outer = r - 3
            major = val % 30 == 0
            inner = r - (9 if major else 6)

            x1 = cx + outer * math.cos(theta)
            y1 = cy - outer * math.sin(theta)
            x2 = cx + inner * math.cos(theta)
            y2 = cy - inner * math.sin(theta)

            c.create_line(x1, y1, x2, y2, fill=MUTED if major else "#576676", width=2 if major else 1)

        for num in [0, 45, 90, 135, 180]:
            theta = math.radians(start_deg + (num / MAX_PWM) * (end_deg - start_deg))
            tx = cx + (r - 17) * math.cos(theta)
            ty = cy - (r - 17) * math.sin(theta)
            c.create_text(tx, ty, text=str(num), fill=TEXT, font=("DejaVu Sans", 5, "bold"))

        pwm_clamped = max(MIN_PWM, min(MAX_PWM, pwm))
        theta = math.radians(start_deg + (pwm_clamped / MAX_PWM) * (end_deg - start_deg))

        nx = cx + (r - 18) * math.cos(theta)
        ny = cy - (r - 18) * math.sin(theta)

        c.create_line(cx, cy, nx, ny, fill=BLUE, width=3)
        c.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill="#7fcaff", outline="#d8f0ff")

        c.create_text(cx, cy + 13, text=SPEED_UNIT, fill=TEXT, font=("DejaVu Sans", 6, "bold"))
        c.create_text(cx, cy + 28, text=f"{int(pwm_clamped)}", fill=TEXT, font=("DejaVu Sans", 12, "bold"))

    # ---------------- SYSTEM STATUS ----------------
    def build_system_card(self):
        self.section_title(self.card_system, "SYSTEM STATUS")
        self.system_rows = {}

        rows = [
            ("▣", "STM32", "SEARCH"),
            ("◉", "DIST", "WAIT"),
            ("⇣", "DATA", "WAIT")
        ]

        y = 43

        for icon, label, value in rows:
            icon_box = tk.Label(
                self.card_system,
                text=icon,
                fg=BLUE,
                bg=PANEL_2,
                font=("DejaVu Sans", 9, "bold"),
                width=2
            )
            icon_box.place(x=10, y=y - 4)

            tk.Label(
                self.card_system,
                text=label,
                fg=TEXT,
                bg=PANEL,
                font=("DejaVu Sans", 8, "bold")
            ).place(x=42, y=y)

            dot = tk.Label(
                self.card_system,
                text="●",
                fg=YELLOW,
                bg=PANEL,
                font=("DejaVu Sans", 8, "bold")
            )
            dot.place(x=94, y=y)

            val = tk.Label(
                self.card_system,
                text=value,
                fg=YELLOW,
                bg=PANEL,
                font=("DejaVu Sans", 8, "bold")
            )
            val.place(x=113, y=y)

            self.system_rows[label] = (dot, val)
            y += 43

    # ---------------- OBSTACLE VIEW ----------------
    def build_obstacle_card(self):
        self.section_title(self.card_obstacle, "FRONT OBSTACLE VIEW (LIDAR)", x=95, y=7)

        self.obstacle_canvas = tk.Canvas(self.card_obstacle, bg=PANEL, highlightthickness=0)
        self.obstacle_canvas.place(x=5, y=26, width=345, height=106)

    def draw_obstacle_view(self, distance, state):
        c = self.obstacle_canvas
        c.delete("all")

        w = 345
        cx = w // 2
        by = 94

        for i in range(0, 5):
            y = by - i * 17
            c.create_line(58 + i * 8, y, w - (58 + i * 8), y, fill=GRID)

        c.create_line(cx - 52, by, 86, 16, fill="#495f76", width=2)
        c.create_line(cx + 52, by, w - 86, 16, fill="#495f76", width=2)

        for idx, label in enumerate([50, 100, 150, 200]):
            y = by - (idx * 21 + 20)
            c.create_text(8, y, text=f"{label} cm", fill=MUTED, font=("DejaVu Sans", 6), anchor="w")

        c.create_polygon(cx, by - 12, cx - 73, by - 55, cx + 73, by - 55, fill="#163822", outline=GREEN)
        c.create_polygon(cx, by - 12, cx - 55, by - 68, cx + 55, by - 68, fill="#363416", outline=YELLOW)
        c.create_polygon(cx, by - 12, cx - 35, by - 82, cx + 35, by - 82, fill="#44211d", outline=RED)

        # Robot
        c.create_rectangle(cx - 25, by - 17, cx + 25, by + 1, fill="#252f38", outline="#647583")
        c.create_oval(cx - 34, by - 20, cx - 18, by + 6, fill="#111820", outline="#536675")
        c.create_oval(cx + 18, by - 20, cx + 34, by + 6, fill="#111820", outline="#536675")
        c.create_rectangle(cx - 18, by + 1, cx + 18, by + 5, fill=BLUE, outline="")
        c.create_oval(cx - 13, by - 35, cx + 13, by - 11, fill="#2c3a45", outline="#768797")
        c.create_oval(cx - 7, by - 30, cx + 7, by - 16, fill="#0c1218", outline="#9fafbd")

        # Obstacle
        d = max(10, min(200, distance))
        oy = by - 12 - int((d / 200) * 65)
        oc = state_color(state)

        c.create_rectangle(cx - 25, oy - 12, cx + 25, oy + 12, fill="#8c4334", outline=oc)
        c.create_line(cx - 25, oy, cx + 25, oy, fill="#ad685a")
        c.create_line(cx, oy - 12, cx, oy + 12, fill="#ad685a")

        c.create_rectangle(cx - 30, oy - 34, cx + 30, oy - 16, fill="#111820", outline=YELLOW)
        c.create_text(cx, oy - 25, text=f"{distance} cm", fill=YELLOW, font=("DejaVu Sans", 8, "bold"))
        c.create_line(cx, oy - 16, cx, oy - 12, fill=YELLOW, width=2)

    # ---------------- RIGHT STATUS ----------------
    def build_status_card(self):
        self.status_canvas = tk.Canvas(self.card_status, bg=PANEL, highlightthickness=0)
        self.status_canvas.pack(fill="both", expand=True)
        self.draw_status_card("Waiting", 0, "WAIT", "WAIT")

    def draw_status_card(self, action, counter, data_status, distance_status):
        c = self.status_canvas
        c.delete("all")

        c.create_text(12, 17, text="ROBOT ACTION", fill=MUTED, font=("DejaVu Sans", 7, "bold"), anchor="w")
        c.create_text(12, 42, text=action, fill=YELLOW if "Slow" in action else TEXT, font=("DejaVu Sans", 11, "bold"), anchor="w")
        c.create_line(10, 60, 202, 60, fill=BORDER)

        c.create_text(12, 78, text="MESSAGE COUNTER", fill=MUTED, font=("DejaVu Sans", 7, "bold"), anchor="w")
        c.create_text(12, 105, text=str(counter), fill=BLUE, font=("DejaVu Sans", 15, "bold"), anchor="w")
        c.create_line(10, 122, 202, 122, fill=BORDER)

        c.create_text(12, 135, text=f"DATA: {data_status}", fill=GREEN if data_status == "RX" else RED, font=("DejaVu Sans", 7, "bold"), anchor="w")
        c.create_text(112, 135, text=f"DIST: {distance_status}", fill=GREEN if distance_status == "OK" else RED, font=("DejaVu Sans", 7, "bold"), anchor="w")

    # ---------------- EVENT LOG ----------------
    def build_event_log(self):
        self.section_title(self.card_log, "EVENT LOG", x=10, y=6)

        self.log_canvas = tk.Canvas(self.card_log, bg=PANEL, highlightthickness=0)
        self.log_canvas.place(x=8, y=26, width=768, height=104)

        self.draw_event_log()

    def draw_event_log(self):
        c = self.log_canvas
        c.delete("all")

        w = 768
        header_h = 18
        row_h = 16

        c.create_rectangle(0, 0, w, header_h, fill="#102238", outline=BORDER)

        cols = [
            (6, "TIME"),
            (92, "EVENT"),
            (205, "DIST"),
            (290, "SPEED PWM"),
            (390, "BRAKE"),
            (455, "DETAILS")
        ]

        for x, text in cols:
            c.create_text(x, 9, text=text, fill=MUTED, font=("DejaVu Sans", 7, "bold"), anchor="w")

        for idx in range(5):
            y = header_h + idx * row_h
            c.create_rectangle(0, y, w, y + row_h, fill="#0a1725", outline="#102238")

            if idx >= len(self.event_rows):
                continue

            row = self.event_rows[idx]
            color = state_color(row["state"])

            c.create_text(6, y + 8, text=row["time"], fill=TEXT, font=("DejaVu Sans", 6), anchor="w")
            c.create_text(92, y + 8, text=f"● {row['state']}", fill=color, font=("DejaVu Sans", 6, "bold"), anchor="w")
            c.create_text(205, y + 8, text=f"{row['distance']} cm", fill=TEXT, font=("DejaVu Sans", 6), anchor="w")
            c.create_text(290, y + 8, text=f"{int(row['speed'])} PWM", fill=TEXT, font=("DejaVu Sans", 6), anchor="w")
            c.create_text(390, y + 8, text=row["brake"], fill=RED if row["brake"] == "ON" else TEXT, font=("DejaVu Sans", 6), anchor="w")
            c.create_text(455, y + 8, text=row["details"], fill=TEXT, font=("DejaVu Sans", 6), anchor="w")

    # ---------------- SERIAL MODE ----------------
    def start_serial_thread(self):
        thread = threading.Thread(target=self.serial_loop, daemon=True)
        thread.start()

    def serial_loop(self):
        try:
            import serial
        except ImportError:
            self.root.after(0, self.show_error, "NO PYSERIAL")
            self.root.after(0, self.set_header_status, "NO LIB", RED)
            return

        self.serial_port = find_serial_port()

        if self.serial_port is None:
            self.root.after(0, self.show_error, "NO STM32")
            self.root.after(0, self.set_header_status, "NO USB", RED)
            return

        self.root.after(0, self.set_header_status, "USB OK", YELLOW)

        try:
            self.ser = serial.Serial(self.serial_port, BAUD_RATE, timeout=1)
            time.sleep(2)
        except Exception:
            self.root.after(0, self.show_error, "SERIAL ERR")
            self.root.after(0, self.set_header_status, "ERROR", RED)
            return

        self.root.after(0, self.set_header_status, "WAIT RX", YELLOW)

        while True:
            try:
                line = self.ser.readline().decode(errors="ignore").strip()

                if not line:
                    continue

                self.last_raw_line = line
                parsed = parse_stm32_line(line)

                if parsed:
                    distance, state, pwm, brake = parsed
                    self.root.after(0, self.set_header_status, "RX", GREEN)
                    self.process_data(distance, state, pwm, brake, "CONNECTED", line)
                else:
                    self.root.after(0, self.set_header_status, "BAD", YELLOW)

            except Exception:
                self.root.after(0, self.show_error, "SERIAL LOST")
                self.root.after(0, self.set_header_status, "LOST", RED)
                time.sleep(1)

    # ---------------- DEMO MODE ----------------
    def start_demo_thread(self):
        thread = threading.Thread(target=self.demo_loop, daemon=True)
        thread.start()

    def demo_loop(self):
        demo_lines = [
            "Distance:160 cm I State: Normal I Speed:180 I Brake: 0",
            "Distance:135 cm I State: Normal I Speed:160 I Brake: 0",
            "Distance:120 cm I State: Normal I Speed:145 I Brake: 0",
            "Distance:90 cm I State: Warning I Speed:80 I Brake: 0",
            "Distance:62 cm I State: Warning I Speed:80 I Brake: 0",
            "Distance:45 cm I State: Warning I Speed:60 I Brake: 0",
            "Distance:28 cm I State: Emergency I Speed:0 I Brake: 1",
            "Distance:15 cm I State: Emergency I Speed:0 I Brake: 1"
        ]

        while True:
            for line in demo_lines:
                parsed = parse_stm32_line(line)

                if parsed:
                    distance, state, pwm, brake = parsed
                    self.process_data(distance, state, pwm, brake, "DEMO", line)

                time.sleep(1.3)

    # ---------------- DATA UPDATE ----------------
    def process_data(self, distance, state, pwm, brake, link_status, raw_line):
        self.message_counter += 1
        self.last_data_time = time.time()

        distance_status = "OK"
        data_status = "RX"

        if distance <= 0 or distance > 400:
            distance_status = "ERROR"
            state = "DISTANCE_ERROR"
            pwm = 0
            brake = 1

        b_status = brake_status(brake)
        action = robot_action(state, brake)

        now = datetime.now()
        pc_time = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        display_time = now.strftime("%H:%M:%S")

        self.csv_writer.writerow([
            pc_time,
            distance,
            state,
            int(pwm),
            brake,
            b_status,
            action,
            link_status,
            raw_line
        ])
        self.csv_file.flush()

        self.root.after(
            0,
            self.update_dashboard,
            distance,
            state,
            pwm,
            b_status,
            action,
            link_status,
            distance_status,
            data_status,
            display_time
        )

    def update_dashboard(self, distance, state, pwm, b_status, action, link_status, distance_status, data_status, display_time):
        self.header_canvas.itemconfig(self.time_header, text=datetime.now().strftime("%I:%M:%S %p"))

        self.draw_state_box(state, f"Action: {action}")

        self.draw_speed_gauge(pwm)
        self.speed_value_label.config(text=f"{int(pwm)}")
        self.speed_source_label.config(text="MOTOR CMD", fg=GREEN if pwm > 0 else MUTED)

        self.brake_value.config(text=b_status, fg=RED)

        self.system_rows["STM32"][1].config(text="RX" if link_status == "CONNECTED" else link_status, fg=GREEN)
        self.system_rows["STM32"][0].config(fg=GREEN)

        self.system_rows["DIST"][1].config(text=distance_status, fg=GREEN if distance_status == "OK" else RED)
        self.system_rows["DIST"][0].config(fg=GREEN if distance_status == "OK" else RED)

        self.system_rows["DATA"][1].config(text=data_status, fg=GREEN)
        self.system_rows["DATA"][0].config(fg=GREEN)

        self.draw_obstacle_view(distance, state)
        self.draw_status_card(action, self.message_counter, data_status, distance_status)

        self.add_log_row(display_time, state, distance, pwm, b_status)

    def add_log_row(self, display_time, state, distance, pwm, b_status):
        self.event_rows.insert(
            0,
            {
                "time": display_time,
                "state": state,
                "distance": distance,
                "speed": pwm,
                "brake": b_status,
                "details": status_details(state)
            }
        )

        self.event_rows = self.event_rows[:5]
        self.draw_event_log()

    def show_error(self, text):
        self.draw_state_box("ERROR", "Action: Safe Stop")

        if hasattr(self, "system_rows"):
            self.system_rows["STM32"][1].config(text="FAILED", fg=RED)
            self.system_rows["STM32"][0].config(fg=RED)
            self.system_rows["DATA"][1].config(text="NO DATA", fg=RED)
            self.system_rows["DATA"][0].config(fg=RED)

        self.draw_status_card("Safe Stop", self.message_counter, "FAILED", "UNKNOWN")

    def check_no_data(self):
        if not DEMO_MODE and self.last_data_time != 0:
            if time.time() - self.last_data_time > NO_DATA_TIMEOUT_SEC:
                self.show_error("NO DATA")
                self.set_header_status("NO RX", RED)

        self.root.after(500, self.check_no_data)

    def close_and_exit(self):
        self.close()
        self.root.destroy()

    def close(self):
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass

        try:
            self.csv_file.close()
        except Exception:
            pass


# ---------------- MAIN ----------------
if __name__ == "__main__":
    root = tk.Tk()
    app = SafetyDashboard(root)

    def on_close():
        app.close_and_exit()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
