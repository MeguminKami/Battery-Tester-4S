import os.path
import tkinter as tk
import math
from tkinter.ttk import Button
from ttkbootstrap import Style
from tkinter import scrolledtext, simpledialog
from tkinter import messagebox
from ttkbootstrap.constants import *
from tkinter import ttk, Toplevel
from tkinter import Listbox
import threading
import queue
import time
import csv
import json
import serial
import pandas as pd
import numpy as np
from datetime import datetime
from collections import deque
from typing import Optional, List, Tuple, Deque, Dict, Any
import logging
from emailbot.emailbot import send_completion_email
from emailbot.emailbot import send_warning_email

"""
#########################################################
#                                                       #
# Copyright (c) 2026 João Pedro Caldas Ferreira        #
#                                                       #
# This work was developed for INESC Technology         #
# and Science - Centre for Robotics and Autonomous     #
# Systems (INESC-TEC CRAS)                             #
#                                                       #
# LinkedIn:                                            #
# https://www.linkedin.com/in/autojoaoferreira/        #
#                                                       #
#                                                       #
# All rights reserved. Unauthorized copying,           #
# distribution, reproduction, or modification          #
# of this software, via any medium, is strictly        #
# prohibited without express permission of the         #
# author or INESC-TEC.                                 #
#                                                       #
#########################################################

Battery Tester Application

Version: 1.0
- Migrate from 1S1P i.e Battery Tester v2.0 to 
4S4P version

Last Updated: 01/05/2026
"""

# Configuration Constants
class Config:
    """Application configuration constants loaded from JSON at startup."""

    CONFIG_FILE = "battery_tester_config.json"
    DEFAULT_CONFIG_FILE = "battery_tester_config.default.json"
    SUPPORTED_RESOLUTIONS = [
        (1024, 768),
        (1152, 864),
        (1280, 960),
        (1400, 1050),
        (1600, 1200),
    ]
    DEFAULT_WINDOW_WIDTH = 1280
    DEFAULT_WINDOW_HEIGHT = 960
    BAUD_RATE = 9600
    CELL_COUNT = 4

    DEFAULTS: Dict[str, Any] = {
        "application": {
            "window_width": DEFAULT_WINDOW_WIDTH,
            "window_height": DEFAULT_WINDOW_HEIGHT,
            "theme": "superhero",
            "data_dir": "data"
        },
        "battery": {
            "parallel_cells": 4,
            "cell_min_voltage": 2.50,
            "cell_max_voltage": 4.20,
            "nominal_capacity_ah": 13.6
        },
        "safety": {
            "max_temperature_c": 80.0,
            "charge_end_current_a": 0.05,
            "zero_current_threshold_a": 0.05
        },
        "hardware": {
            "idle_adc_reference_voltage_v": 4.94,
            "active_adc_reference_voltage_v": 4.90
        },
        "timing": {
            "arduino_reset_delay_s": 1.0,
            "command_retry_delay_s": 0.5,
            "max_command_retries": 3,
            "cycle_transition_min_seconds": 600,
            "sampling_period_ms": 500,
            "adc_samples": 8
        },
        "soc_ocv": {
            "soc_step_fraction": 0.05,
            "relax_window_s": 600,
            "relax_threshold_v": 0.001,
            "fallback_rest_s": 3600,
            "cutoff_cell_voltage": 2.50
        },
        "calibration": {
            "samples": 20
        }
    }

    @classmethod
    def _deepcopy_defaults(cls) -> Dict[str, Any]:
        return json.loads(json.dumps(cls.DEFAULTS))

    @classmethod
    def _deep_update(cls, base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                cls._deep_update(base[key], value)
            else:
                base[key] = value
        return base

    @classmethod
    def _clean_config(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate legacy keys and drop settings that are no longer user-facing."""
        cleaned = json.loads(json.dumps(data))
        cleaned.pop("arduino", None)
        cleaned.get("application", {}).pop("baud_rate", None)
        cleaned.get("application", {}).pop("open_config_on_startup", None)
        cleaned.get("battery", {}).pop("series_cells", None)
        cleaned.get("battery", {}).pop("complete_discharge_low_v", None)
        cleaned.get("battery", {}).pop("complete_discharge_high_v", None)
        cleaned.get("battery", {}).pop("complete_charge_low_v", None)
        cleaned.get("battery", {}).pop("complete_charge_high_v", None)
        cleaned.get("timing", {}).pop("relay_pulse_time_ms", None)

        hardware = cleaned.setdefault("hardware", {})
        legacy_vref = hardware.pop("adc_reference_voltage_v", None)
        if legacy_vref is not None:
            hardware.setdefault("idle_adc_reference_voltage_v", legacy_vref)
            hardware.setdefault("active_adc_reference_voltage_v", legacy_vref)
        return cleaned

    @classmethod
    def _write_json(cls, path: str, data: Dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)

    @classmethod
    def load_config(cls) -> Dict[str, Any]:
        """Load user configuration and ensure both active and default JSON files exist."""
        defaults = cls._deepcopy_defaults()
        if not os.path.exists(cls.DEFAULT_CONFIG_FILE):
            cls._write_json(cls.DEFAULT_CONFIG_FILE, defaults)

        if not os.path.exists(cls.CONFIG_FILE):
            cls._write_json(cls.CONFIG_FILE, defaults)
            data = defaults
        else:
            try:
                with open(cls.CONFIG_FILE, "r", encoding="utf-8") as file:
                    loaded = json.load(file)
                loaded = cls._clean_config(loaded) if isinstance(loaded, dict) else {}
                data = cls._deep_update(defaults, loaded)
                cls._write_json(cls.CONFIG_FILE, data)
            except Exception:
                data = defaults
                cls._write_json(cls.CONFIG_FILE, data)

        cls.apply(data)
        return data

    @classmethod
    def save_config(cls, data: Dict[str, Any]) -> None:
        defaults = cls._deepcopy_defaults()
        merged = cls._deep_update(defaults, cls._clean_config(data))
        cls._write_json(cls.CONFIG_FILE, merged)
        if not os.path.exists(cls.DEFAULT_CONFIG_FILE):
            cls._write_json(cls.DEFAULT_CONFIG_FILE, cls._deepcopy_defaults())
        cls.apply(merged)

    @classmethod
    def restore_defaults(cls) -> Dict[str, Any]:
        defaults = cls._deepcopy_defaults()
        cls._write_json(cls.CONFIG_FILE, defaults)
        cls._write_json(cls.DEFAULT_CONFIG_FILE, defaults)
        cls.apply(defaults)
        return defaults

    @classmethod
    def apply(cls, data: Dict[str, Any]) -> None:
        app = data.get("application", {})
        battery = data.get("battery", {})
        safety = data.get("safety", {})
        hardware = data.get("hardware", {})
        timing = data.get("timing", {})
        soc = data.get("soc_ocv", {})
        cal = data.get("calibration", {})

        width = int(app.get("window_width", cls.DEFAULT_WINDOW_WIDTH))
        height = int(app.get("window_height", cls.DEFAULT_WINDOW_HEIGHT))
        if (width, height) not in cls.SUPPORTED_RESOLUTIONS:
            width = cls.DEFAULT_WINDOW_WIDTH
            height = cls.DEFAULT_WINDOW_HEIGHT
        cls.WINDOW_WIDTH = width
        cls.WINDOW_HEIGHT = height
        cls.DEFAULT_THEME = str(app.get("theme", "superhero"))
        cls.DATA_DIR = str(app.get("data_dir", "data"))

        cls.PARALLEL_COUNT = int(battery.get("parallel_cells", 4))
        cls.CELL_MIN_VOLTAGE = float(battery.get("cell_min_voltage", 2.5))
        cls.CELL_MAX_VOLTAGE = float(battery.get("cell_max_voltage", 4.2))
        cls.BATTERY_MIN_VOLTAGE = cls.CELL_MIN_VOLTAGE * cls.CELL_COUNT
        cls.BATTERY_MAX_VOLTAGE = cls.CELL_MAX_VOLTAGE * cls.CELL_COUNT
        cls.NOMINAL_CAPACITY_AH = float(battery.get("nominal_capacity_ah", 13.6))

        cls.MAX_TEMPERATURE_C = float(safety.get("max_temperature_c", 80.0))
        cls.CHARGE_END_CURRENT_A = float(safety.get("charge_end_current_a", 0.05))
        cls.SOC_OCV_ZERO_CURRENT_THRESHOLD_A = float(safety.get("zero_current_threshold_a", 0.05))

        cls.IDLE_ADC_REFERENCE_VOLTAGE = float(hardware.get("idle_adc_reference_voltage_v", 4.94))
        cls.ACTIVE_ADC_REFERENCE_VOLTAGE = float(hardware.get("active_adc_reference_voltage_v", 4.90))

        cls.ARDUINO_RESET_DELAY = float(timing.get("arduino_reset_delay_s", 1.0))
        cls.COMMAND_RETRY_DELAY = float(timing.get("command_retry_delay_s", 0.5))
        cls.MAX_COMMAND_RETRIES = int(timing.get("max_command_retries", 3))
        cls.CYCLE_TRANSITION_MIN_SECONDS = int(timing.get("cycle_transition_min_seconds", 600))
        cls.SAMPLING_PERIOD_MS = int(timing.get("sampling_period_ms", 500))
        cls.ADC_SAMPLES = int(timing.get("adc_samples", 8))

        cls.SOC_STEP_FRACTION = float(soc.get("soc_step_fraction", 0.05))
        cls.SOC_OCV_RELAX_WINDOW_S = int(soc.get("relax_window_s", 600))
        cls.SOC_OCV_RELAX_THRESHOLD_V = float(soc.get("relax_threshold_v", 0.001))
        cls.SOC_OCV_FALLBACK_REST_S = int(soc.get("fallback_rest_s", 3600))
        cls.SOC_OCV_CUTOFF_V = float(soc.get("cutoff_cell_voltage", 2.5))

        cls.CALIBRATION_SAMPLES = int(cal.get("samples", 20))

    @classmethod
    def flatten(cls, data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        output: Dict[str, Any] = {}
        for key, value in data.items():
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                output.update(cls.flatten(value, name))
            else:
                output[name] = value
        return output

    @classmethod
    def set_nested(cls, data: Dict[str, Any], dotted_key: str, value: Any) -> None:
        keys = dotted_key.split(".")
        target = data
        for key in keys[:-1]:
            target = target.setdefault(key, {})
        target[keys[-1]] = value

    @classmethod
    def parse_value(cls, text: str, current_value: Any) -> Any:
        if isinstance(current_value, bool):
            return text.strip().lower() in ("1", "true", "yes", "y", "on")
        if isinstance(current_value, int) and not isinstance(current_value, bool):
            return int(float(text))
        if isinstance(current_value, float):
            return float(text)
        if isinstance(current_value, list):
            values = [v.strip() for v in text.split(",") if v.strip() != ""]
            try:
                return [float(item) for item in values]
            except ValueError:
                return values
        return text


class App(tk.Tk):
    """Main application class for Battery Tester"""

    def __init__(self):
        """Initialize the Battery Tester application"""
        Config.load_config()
        super().__init__()

        # Initialize ttkbootstrap style
        self.style = Style(theme=Config.DEFAULT_THEME)

        # Window parameters
        self.title("Battery Tester v1.0 - 4S4P")
        self._apply_main_window_geometry()

        # Initialize variables before creating frames
        self._initialize_variables()

        # Create frames
        self.data_frame = ttk.Frame(self)
        self.create_data_frame_vars()

        # Show the data frame initially
        self.show_frame(self.data_frame)

        # Start processing serial events on the UI thread
        self.after(20, self._process_event_queue)

        # Setup cleanup on window close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _apply_main_window_geometry(self):
        """Apply the configured fixed 4:3 main-window size."""
        self.minsize(1, 1)
        self.maxsize(10000, 10000)
        self.geometry(f"{Config.WINDOW_WIDTH}x{Config.WINDOW_HEIGHT}")
        self.minsize(Config.WINDOW_WIDTH, Config.WINDOW_HEIGHT)
        self.maxsize(Config.WINDOW_WIDTH, Config.WINDOW_HEIGHT)
        self.resizable(False, False)

    def _initialize_variables(self):
        """Initialize all application variables"""
        # Arduino connection
        self.arduino: Optional[serial.Serial] = None
        self.connected = False
        self.state = 'off'

        # Threading
        self.packet_reader_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        self.event_queue = queue.Queue(maxsize=1000)

        # Timing
        self.start_time = 0

        # Measurement control
        self.measuring = False

        # Calibration
        self.calibration_number = Config.CALIBRATION_SAMPLES
        self.calibration_count = 0
        self.calibration_sum = 0
        self.current_offset = 0

        # File handling
        self.filename: Optional[str] = None

        # Window references
        self.test_window: Optional[Toplevel] = None
        self.connect_window: Optional[Toplevel] = None
        self.config_window: Optional[Toplevel] = None

        # Test-specific variables
        self._initialize_test_variables()

    def _initialize_test_variables(self):
        """Initialize test-specific variables"""
        # Pulsed Charge/Discharge Test Variables
        self.pct_do_period = 0
        self.pct_resting_period = 0
        self.pct_time = 0
        self.pct_state: Optional[str] = None

        # Cycle Test Variables
        self.cycle_number = 0
        self.cycle_count = 0
        self.cycle_start: Optional[str] = None
        self.cycle_last_state: Optional[str] = None
        self.cycle_state: Optional[str] = None
        self.cycle_is_pulsed = False
        self.cycle_pulsed_resting_period = 0
        self.cycle_pulsed_do_period = 0
        self.cycle_pulsed_state: Optional[str] = None
        self.cycle_pulsed_time = 0.0
        self.overtemp_shutdown = False
        self.overtemp_warning_email_sent = False
        self._completion_in_progress = False
        self._test_saved = False
        self._completion_email_sent = False
        self.active_test_name = ""

        # Between-cycle calibration state
        self.cycle_calibrating = False  # True while calibrating between cycles
        self.verify_mode_after_calibration = False  # Flag to verify Arduino mode after calibration
        self.mode_verify_timeout = 0  # Timeout counter for mode verification
        self.last_voltage_received_time = 0  # Track when voltage was last received
        self.last_temperature_received_time = 0  # Track when temperature was last received

        # UI state
        self.start_test_button_state: Optional[bool] = None
        self.port_description: Optional[ttk.Label] = None
        self.selected_port: Optional[tk.StringVar] = None

        # SOC-OCV characterization variables
        self.soc_ocv_phase: Optional[str] = None
        self.soc_ocv_capacity_discharge_ah = 0.0
        self.soc_ocv_measured_capacity_ah: Optional[float] = None
        self.soc_ocv_characterization_discharged_ah = 0.0
        self.soc_ocv_step_discharged_ah = 0.0
        self.soc_ocv_step_ah = Config.SOC_STEP_FRACTION * Config.NOMINAL_CAPACITY_AH
        self.soc_ocv_soc_percent = 100.0
        self.soc_ocv_current_a: Optional[float] = None
        self.soc_ocv_last_integrated_time: Optional[float] = None
        self.soc_ocv_last_voltage_time: Optional[float] = None
        self.soc_ocv_cutoff_voltage = Config.SOC_OCV_CUTOFF_V
        self.soc_ocv_rest_start_time = 0.0
        self.soc_ocv_rest_voltage_history: Deque[Tuple[float, float]] = deque(maxlen=10000)
        self.soc_ocv_points: List[Dict[str, Any]] = []
        self.soc_ocv_step_index = 0
        self.soc_ocv_finalized = False
        self.soc_ocv_stop_reason = ""
        self.soc_ocv_final_cutoff_pending = False
        self.soc_ocv_final_cutoff_rest_completed = False
        self.soc_ocv_capacity_measurement_completed = False
        self.soc_ocv_full_charge_completed = False

    def show_frame(self, frame):
        """Display the specified frame"""
        for widget in self.winfo_children():
            widget.pack_forget()
        frame.pack(fill="both", expand=True)

    def create_data_frame_vars(self):
        """Create and configure all UI elements in the data frame"""
        # Create StringVars for display
        self.voltage = tk.StringVar(value="Pack Voltage: 0.00 V")
        self.voltage_ = 0.0
        self._voltage_: List[float] = []

        self.cell_voltage_vars: List[tk.StringVar] = [
            tk.StringVar(value=f"Cell {i + 1}: 0.000 V")
            for i in range(Config.CELL_COUNT)
        ]
        self.tap_voltage_vars: List[tk.StringVar] = [
            tk.StringVar(value=f"Tap {i + 1}S: 0.000 V")
            for i in range(Config.CELL_COUNT)
        ]
        self.cell_voltages: List[float] = [0.0 for _ in range(Config.CELL_COUNT)]
        self.tap_voltages: List[float] = [0.0 for _ in range(Config.CELL_COUNT)]
        self._cell_voltages: List[List[float]] = [[] for _ in range(Config.CELL_COUNT)]
        self._tap_voltages: List[List[float]] = [[] for _ in range(Config.CELL_COUNT)]
        self.cell_delta = tk.StringVar(value="Cell Δ: 0.000 V")
        self.pack_topology = tk.StringVar(value=f"Topology: {Config.CELL_COUNT}S{Config.PARALLEL_COUNT}P")

        self.current = tk.StringVar(value="0.00 A")
        self.current_ = 0.0
        self._current_: List[float] = []

        self.temperature = tk.StringVar(value="Temperature: 0.00 °C")
        self.temperature_ = 0.0
        self._temperature_: List[float] = []

        self.elapsed_time = tk.StringVar(value="Elapsed Time: 0.00 s")
        self.elapsed_time_ = 0.0
        self._elapsed_time_: List[float] = []

        self.offset = tk.StringVar(value="Current Offset: 0.00000000 A")
        self.status = tk.StringVar(value='Resting')
        self.running_test = tk.StringVar(value='No test running')
        self.cycle_target = tk.StringVar(value='Cycle Target: N/A')
        self.cycle_action = tk.StringVar(value='Cycle Action: N/A')
        self.cycle_progress = tk.StringVar(value='Cycle Progress: N/A')

        # Create frame structure
        self._create_frame_structure()

        # Create UI elements
        self._create_labels()
        self._create_buttons()
        self._create_battery_display()
        self._create_log_window()

    def _create_frame_structure(self):
        """Create the frame structure for the UI"""
        self._configure_dashboard_styles()

        self.data_frame.configure(style="Dashboard.TFrame")
        self.data_frame.columnconfigure(0, weight=1)
        self.data_frame.rowconfigure(0, weight=0)
        self.data_frame.rowconfigure(1, weight=1)
        self.data_frame.rowconfigure(2, weight=0)

        self.data_topframe = ttk.Frame(self.data_frame, style="Topbar.TFrame", padding=(14, 8))
        self.data_topframe.grid(row=0, column=0, sticky="ew")
        self.data_topframe.columnconfigure(0, weight=1)
        self.data_topframe.columnconfigure(1, weight=0)
        self.data_topframe.columnconfigure(2, weight=0)

        self.dashboard_frame = ttk.Frame(self.data_frame, style="Dashboard.TFrame", padding=(10, 8, 10, 6))
        self.dashboard_frame.grid(row=1, column=0, sticky="nsew")
        self.dashboard_frame.columnconfigure(0, weight=0, minsize=145)
        self.dashboard_frame.columnconfigure(1, weight=2)
        self.dashboard_frame.columnconfigure(2, weight=1, minsize=225)
        self.dashboard_frame.rowconfigure(0, weight=1)

        self.left_data_topframe = ttk.Frame(self.dashboard_frame, style="Panel.TFrame", padding=10)
        self.left_data_topframe.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.middle_data_topframe = ttk.Frame(self.dashboard_frame, style="Dashboard.TFrame")
        self.middle_data_topframe.grid(row=0, column=1, sticky="nsew", padx=4)
        self.middle_data_topframe.columnconfigure(0, weight=1)
        self.middle_data_topframe.rowconfigure(0, weight=0)
        self.middle_data_topframe.rowconfigure(1, weight=0)
        self.middle_data_topframe.rowconfigure(2, weight=1)

        self.right_data_topframe = ttk.Frame(self.dashboard_frame, style="Dashboard.TFrame")
        self.right_data_topframe.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        self.right_data_topframe.columnconfigure(0, weight=1)

        self.data_bottomframe = ttk.Frame(self.data_frame, style="Dashboard.TFrame", padding=(10, 0, 10, 10))
        self.data_bottomframe.grid(row=2, column=0, sticky="nsew")
        self.data_bottomframe.columnconfigure(0, weight=1)
        self.data_bottomframe.rowconfigure(0, weight=1)

    def _configure_dashboard_styles(self):
        """Configure the visual language for the main lab dashboard."""
        self.dashboard_colors = {
            "bg": "#101820",
            "panel": "#18232d",
            "panel_alt": "#202d38",
            "border": "#2f4352",
            "text": "#ecf2f8",
            "muted": "#9fb1bf",
            "accent": "#2dd4bf",
            "blue": "#38bdf8",
            "green": "#22c55e",
            "yellow": "#f59e0b",
            "red": "#ef4444",
            "empty": "#31404d",
        }
        colors = self.dashboard_colors

        self.configure(bg=colors["bg"])
        self.style.configure("Dashboard.TFrame", background=colors["bg"])
        self.style.configure("Topbar.TFrame", background="#0b1117")
        self.style.configure("Panel.TFrame", background=colors["panel"], relief="flat")
        self.style.configure("Card.TFrame", background=colors["panel_alt"], relief="flat")
        self.style.configure("DashboardTitle.TLabel", background="#0b1117", foreground=colors["text"],
                             font=("Segoe UI", 14, "bold"))
        self.style.configure("DashboardSubtle.TLabel", background="#0b1117", foreground=colors["muted"],
                             font=("Segoe UI", 9))
        self.style.configure("PanelMuted.TLabel", background=colors["panel"], foreground=colors["muted"],
                             font=("Segoe UI", 9))
        self.style.configure("PanelTitle.TLabel", background=colors["panel"], foreground=colors["text"],
                             font=("Segoe UI", 10, "bold"))
        self.style.configure("CardTitle.TLabel", background=colors["panel_alt"], foreground=colors["muted"],
                             font=("Segoe UI", 8, "bold"))
        self.style.configure("Metric.TLabel", background=colors["panel_alt"], foreground=colors["text"],
                             font=("Segoe UI", 10, "bold"))
        self.style.configure("MetricSmall.TLabel", background=colors["panel_alt"], foreground=colors["text"],
                             font=("Segoe UI", 8))
        self.style.configure("MetricLarge.TLabel", background=colors["panel_alt"], foreground=colors["text"],
                             font=("Segoe UI", 15, "bold"))
        self.style.configure("Console.TFrame", background=colors["panel"])

    def _create_section(self, parent, title: str, row: int = 0, column: int = 0, **grid_options):
        """Create a titled panel with consistent spacing."""
        section = ttk.Frame(parent, style="Panel.TFrame", padding=8)
        section.grid(row=row, column=column, sticky=grid_options.pop("sticky", "nsew"), **grid_options)
        section.columnconfigure(0, weight=1)
        ttk.Label(section, text=title, style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        return section

    def _create_dialog_body(self, window: Toplevel, title: str, subtitle: str = ""):
        """Create a consistent panel body for secondary windows."""
        colors = getattr(self, "dashboard_colors", {"bg": "#101820"})
        window.configure(bg=colors["bg"])
        body = ttk.Frame(window, style="Panel.TFrame", padding=16)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text=title, style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        if subtitle:
            ttk.Label(body, text=subtitle, style="PanelMuted.TLabel", wraplength=640, justify=tk.LEFT).grid(
                row=1, column=0, sticky="ew", pady=(6, 12)
            )
        return body

    def _create_metric_card(self, parent, title: str, variable: tk.StringVar, row: int, column: int,
                            style: str = "Metric.TLabel", columnspan: int = 1,
                            value_width: Optional[int] = None, value_anchor: str = "w"):
        """Create a compact dashboard metric bound to an existing StringVar."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=(8, 5))
        card.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=3, pady=3)
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=title.upper(), style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            card,
            textvariable=variable,
            style=style,
            anchor=value_anchor,
            width=value_width
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))
        return card

    def _config_display_label(self, key: str) -> str:
        """Return a user-facing label for a configuration key."""
        labels = {
            "application.theme": "Visual theme",
            "application.data_dir": "Data folder",
            "battery.parallel_cells": "Parallel cell count",
            "battery.cell_min_voltage": "Minimum cell voltage (V)",
            "battery.cell_max_voltage": "Maximum cell voltage (V)",
            "battery.nominal_capacity_ah": "Nominal pack capacity (Ah)",
            "safety.max_temperature_c": "Maximum safe temperature (C)",
            "safety.charge_end_current_a": "Charge end current (A)",
            "safety.zero_current_threshold_a": "Zero-current threshold (A)",
            "hardware.idle_adc_reference_voltage_v": "Arduino idle/rest 5V reference (V)",
            "hardware.active_adc_reference_voltage_v": "Arduino active relay 5V reference (V)",
            "timing.arduino_reset_delay_s": "Arduino reset delay (s)",
            "timing.command_retry_delay_s": "Command retry delay (s)",
            "timing.max_command_retries": "Maximum command retries",
            "timing.cycle_transition_min_seconds": "Minimum cycle transition time (s)",
            "timing.sampling_period_ms": "Sampling period (ms)",
            "timing.adc_samples": "ADC samples per reading",
            "soc_ocv.soc_step_fraction": "SOC-OCV step size (fraction)",
            "soc_ocv.relax_window_s": "OCV stability window (s)",
            "soc_ocv.relax_threshold_v": "OCV stability threshold (V)",
            "soc_ocv.fallback_rest_s": "Maximum rest fallback (s)",
            "soc_ocv.cutoff_cell_voltage": "SOC-OCV cutoff voltage (V/cell)",
            "calibration.samples": "Calibration sample count",
        }
        return labels.get(key, key.replace(".", " ").replace("_", " ").title())

    def _format_resolution(self, width: int, height: int) -> str:
        return f"{width} x {height}"

    def _create_status_panel(self):
        """Create the operational status and cycle information panel."""
        status_section = self._create_section(self.right_data_topframe, "Test Status")
        status_section.columnconfigure(0, weight=1)

        self._create_metric_card(status_section, "Running Test", self.running_test, 1, 0, style="MetricLarge.TLabel")
        self._create_metric_card(status_section, "State", self.status, 2, 0)
        self._create_metric_card(status_section, "Current Offset", self.offset, 3, 0, style="MetricSmall.TLabel")

        cycle_section = self._create_section(self.right_data_topframe, "Cycle Progress", row=1, column=0, pady=(6, 0))
        cycle_section.columnconfigure(0, weight=1)
        self._create_metric_card(cycle_section, "Target", self.cycle_target, 1, 0, style="MetricSmall.TLabel")
        self._create_metric_card(cycle_section, "Action", self.cycle_action, 2, 0, style="MetricSmall.TLabel")
        self._create_metric_card(cycle_section, "Progress", self.cycle_progress, 3, 0, style="MetricSmall.TLabel")

    def _create_labels(self):
        """Create display labels"""
        ttk.Label(self.data_topframe, text="Battery Tester v1.0 - 4S4P", style="DashboardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        live_section = self._create_section(self.middle_data_topframe, "Live Measurements")
        live_section.columnconfigure(0, weight=1)
        live_section.columnconfigure(1, weight=1)
        live_section.columnconfigure(2, weight=1)
        self._create_metric_card(live_section, "Temperature", self.temperature, 1, 0, style="MetricLarge.TLabel")
        self._create_metric_card(
            live_section,
            "Current",
            self.current,
            1,
            1,
            style="MetricLarge.TLabel",
            value_width=10,
            value_anchor="e"
        )
        self._create_metric_card(live_section, "Elapsed Time", self.elapsed_time, 1, 2, style="MetricLarge.TLabel")

        pack_section = self._create_section(self.middle_data_topframe, "Pack Overview", row=1, column=0, pady=(6, 0))
        pack_section.columnconfigure(0, weight=1)
        pack_section.columnconfigure(1, weight=1)
        self.pack_canvas_holder = ttk.Frame(pack_section, style="Card.TFrame", padding=10)
        self.pack_canvas_holder.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 4))
        self.pack_canvas_holder.columnconfigure(0, weight=1)

        cell_section = self._create_section(self.middle_data_topframe, "Cell Stack", row=2, column=0, pady=(6, 0))
        cell_section.rowconfigure(1, weight=1)
        for index in range(Config.CELL_COUNT):
            cell_section.columnconfigure(index, weight=1, uniform="cells")
        self.cell_canvas_holder = ttk.Frame(cell_section, style="Panel.TFrame")
        self.cell_canvas_holder.grid(
            row=1,
            column=0,
            columnspan=Config.CELL_COUNT,
            sticky="nsew",
            pady=(6, 0)
        )
        self.cell_canvas_holder.rowconfigure(0, weight=1)
        for index in range(Config.CELL_COUNT):
            self.cell_canvas_holder.columnconfigure(index, weight=1, uniform="cell_batteries")

        tap_section = self._create_section(self.right_data_topframe, "Tap Voltages", row=2, column=0, pady=(6, 0))
        tap_section.columnconfigure(0, weight=1)
        for index, var in enumerate(self.tap_voltage_vars):
            self._create_metric_card(tap_section, f"Tap {index + 1}S", var, index + 1, 0, style="MetricSmall.TLabel")

        self._create_status_panel()

    def _create_buttons(self):
        """Create control buttons"""
        ttk.Label(self.left_data_topframe, text="Controls", style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )
        self.left_data_topframe.columnconfigure(0, weight=1)

        self.connect_button = ttk.Button(
            self.left_data_topframe, 
            text="Connect", 
            command=self.connect,
            bootstyle=PRIMARY
        )
        self.connect_button.grid(row=1, column=0, sticky="ew", pady=5)

        self.start_test_button = ttk.Button(
            self.left_data_topframe, 
            text="Start Test", 
            command=self.start_test,
            bootstyle=SUCCESS
        )
        self.start_test_button.grid(row=2, column=0, sticky="ew", pady=5)

        self.calibration_button = ttk.Button(
            self.left_data_topframe, 
            text="Calibrate", 
            command=self.calibrate,
            bootstyle=WARNING
        )
        self.calibration_button.grid(row=3, column=0, sticky="ew", pady=5)

        self.config_button = ttk.Button(
            self.left_data_topframe,
            text="Configuration",
            command=self.open_config_window,
            bootstyle=INFO
        )
        self.config_button.grid(row=4, column=0, sticky="ew", pady=5)

    def _create_battery_display(self):
        """Create battery charge visualization"""
        colors = self.dashboard_colors
        self.pack_battery_canvas = tk.Canvas(
            self.pack_canvas_holder,
            width=520,
            height=108,
            bg=colors["panel_alt"],
            highlightthickness=0
        )
        self.pack_battery_canvas.grid(row=0, column=0, sticky="ew")
        self.pack_battery_canvas.bind("<Configure>", lambda _event: self._draw_pack_battery())
        self.canvas = self.pack_battery_canvas

        self.cell_battery_canvases = []
        for index in range(Config.CELL_COUNT):
            canvas = tk.Canvas(
                self.cell_canvas_holder,
                width=130,
                height=178,
                bg=colors["panel"],
                highlightthickness=0
            )
            canvas.grid(row=0, column=index, sticky="nsew", padx=6)
            canvas.bind("<Configure>", lambda _event, cell=index: self._draw_cell_battery(cell))
            self.cell_battery_canvases.append(canvas)

        self._refresh_battery_displays()

    def _battery_percent(self, value: float, minimum: float, maximum: float) -> float:
        """Convert a voltage into a display-only percentage."""
        if maximum <= minimum or value <= 0:
            return 0.0
        clamped = max(minimum, min(value, maximum))
        return ((clamped - minimum) / (maximum - minimum)) * 100

    def _battery_color(self, percent: float) -> str:
        """Choose the display color for a battery percentage."""
        colors = self.dashboard_colors
        if percent > 60:
            return colors["green"]
        if percent > 30:
            return colors["yellow"]
        if percent > 0:
            return colors["red"]
        return colors["empty"]

    def _draw_pack_battery(self):
        """Draw the horizontal pack battery visualization."""
        canvas = self.pack_battery_canvas
        colors = self.dashboard_colors
        canvas.delete("all")
        width = int(canvas.winfo_width() or 520)
        height = int(canvas.winfo_height() or 108)

        margin_x = 18
        body_x1 = margin_x
        body_y1 = 34
        body_x2 = max(body_x1 + 120, width - 60)
        body_y2 = max(body_y1 + 44, height - 28)
        terminal_x2 = min(width - 22, body_x2 + 22)
        terminal_y1 = body_y1 + 13
        terminal_y2 = body_y2 - 13

        percent = self._battery_percent(self.voltage_, Config.BATTERY_MIN_VOLTAGE, Config.BATTERY_MAX_VOLTAGE)
        fill_width = (body_x2 - body_x1 - 8) * (percent / 100)
        fill_color = self._battery_color(percent)

        canvas.create_text(body_x1, 16, text="PACK", anchor="w", fill=colors["muted"],
                           font=("Segoe UI", 9, "bold"))
        canvas.create_text(body_x2, 16, text=f"{percent:.0f}%", anchor="e", fill=colors["text"],
                           font=("Segoe UI", 15, "bold"))
        canvas.create_rectangle(body_x1, body_y1, body_x2, body_y2, outline=colors["border"], width=3,
                                fill=colors["bg"])
        canvas.create_rectangle(body_x2, terminal_y1, terminal_x2, terminal_y2, outline=colors["border"],
                                width=2, fill=colors["bg"])
        canvas.create_rectangle(body_x1 + 5, body_y1 + 5, body_x1 + 5 + fill_width, body_y2 - 5,
                                outline="", fill=fill_color)
        canvas.create_text(body_x1 + 8, height - 10, text=self.voltage.get(), anchor="sw",
                           fill=colors["text"], font=("Segoe UI", 10, "bold"))

    def _draw_cell_battery(self, cell_index: int):
        """Draw one vertical cell battery visualization."""
        if not (0 <= cell_index < len(self.cell_battery_canvases)):
            return
        canvas = self.cell_battery_canvases[cell_index]
        colors = self.dashboard_colors
        canvas.delete("all")

        value = self.cell_voltages[cell_index] if cell_index < len(self.cell_voltages) else 0.0
        percent = self._battery_percent(value, Config.CELL_MIN_VOLTAGE, Config.CELL_MAX_VOLTAGE)
        fill_color = self._battery_color(percent)

        width = int(canvas.winfo_width() or 130)
        height = int(canvas.winfo_height() or 230)
        body_width = max(54, min(118, int(width * 0.62)))
        body_x1 = (width - body_width) / 2
        body_x2 = body_x1 + body_width
        body_y1 = 46
        body_y2 = max(body_y1 + 92, height - 54)
        terminal_width = max(24, min(body_width - 18, int(body_width * 0.46)))
        terminal_x1 = (width - terminal_width) / 2
        terminal_x2 = terminal_x1 + terminal_width
        terminal_y1 = 34
        terminal_y2 = body_y1
        fill_height = (body_y2 - body_y1 - 8) * (percent / 100)
        fill_y1 = body_y2 - 4 - fill_height

        canvas.create_text(width / 2, 16, text=f"C{cell_index + 1}", fill=colors["text"],
                           font=("Segoe UI", 13, "bold"))
        canvas.create_rectangle(terminal_x1, terminal_y1, terminal_x2, terminal_y2, outline=colors["border"],
                                width=2, fill=colors["bg"])
        canvas.create_rectangle(body_x1, body_y1, body_x2, body_y2, outline=colors["border"], width=3,
                                fill=colors["bg"])
        canvas.create_rectangle(body_x1 + 5, fill_y1, body_x2 - 5, body_y2 - 5, outline="", fill=fill_color)
        canvas.create_text(width / 2, height - 31, text=f"{value:.3f} V", fill=colors["text"],
                           font=("Segoe UI", 10, "bold"))
        canvas.create_text(width / 2, height - 13, text=f"{percent:.0f}%", fill=colors["muted"],
                           font=("Segoe UI", 9))

    def _refresh_battery_displays(self, cell_index: Optional[int] = None):
        """Refresh pack and cell battery canvases."""
        if not hasattr(self, "pack_battery_canvas"):
            return
        self._draw_pack_battery()
        if cell_index is None:
            for index in range(len(getattr(self, "cell_battery_canvases", []))):
                self._draw_cell_battery(index)
        else:
            self._draw_cell_battery(cell_index)

    def _create_log_window(self):
        """Create log output window"""
        console = ttk.Frame(self.data_bottomframe, style="Console.TFrame", padding=12)
        console.grid(row=0, column=0, sticky="nsew")
        console.columnconfigure(0, weight=1)
        console.rowconfigure(1, weight=1)
        ttk.Label(console, text="Event Log", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.log_window = scrolledtext.ScrolledText(
            console,
            width=70, 
            height=8,
            wrap=tk.WORD,
            bg="#071018",
            fg="#dbeafe",
            insertbackground="#dbeafe",
            selectbackground="#1d4ed8",
            relief=tk.FLAT,
            borderwidth=0,
            font=("Consolas", 10)
        )
        self.log_window.grid(row=1, column=0, sticky="nsew")
        self.log("Battery Tester v1.0 4S4P initialized")

    def _reset_measurement_buffers(self):
        """Reset stored measurement rows without changing visible telemetry."""
        self._voltage_ = []
        self._cell_voltages = [[] for _ in range(Config.CELL_COUNT)]
        self._tap_voltages = [[] for _ in range(Config.CELL_COUNT)]
        self._current_ = []
        self._temperature_ = []
        self.elapsed_time_ = 0.0
        self._elapsed_time_ = []

    def _reset_visible_measurements(self):
        """Reset displayed telemetry and latest numeric values."""
        self.voltage.set("Pack Voltage: 0.00 V")
        self.voltage_ = 0.0
        self.cell_voltages = [0.0 for _ in range(Config.CELL_COUNT)]
        self.tap_voltages = [0.0 for _ in range(Config.CELL_COUNT)]
        for i, var in enumerate(self.cell_voltage_vars):
            var.set(f"Cell {i + 1}: 0.000 V")
        for i, var in enumerate(self.tap_voltage_vars):
            var.set(f"Tap {i + 1}S: 0.000 V")
        self.cell_delta.set("Cell Δ: 0.000 V")
        self.pack_topology.set(f"Topology: {Config.CELL_COUNT}S{Config.PARALLEL_COUNT}P")

        self.current.set("0.00 A")
        self.current_ = 0.0

        self.temperature.set("Temperature: 0.00 °C")
        self.temperature_ = 0.0

        self.elapsed_time.set("Elapsed Time: 0.00 s")
        self._refresh_battery_displays()

    def reset_data_variables(self, reset_visible: bool = True):
        """Reset measurement buffers, optionally resetting visible telemetry."""
        self._reset_measurement_buffers()
        if reset_visible:
            self._reset_visible_measurements()

    def warning_message(self, message: str):
        """Display warning message dialog

        Args:
            message: Warning message to display
        """
        messagebox.showwarning("Warning", message)
        self.log(f"WARNING: {message}")

    def log(self, message: str):
        """Print message to log console with timestamp

        Args:
            message: Message to log
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        self.log_window.insert(tk.END, formatted_message + "\n")
        self.log_window.see(tk.END)

    def arduino_write(self, packet: bytes) -> bool:
        """Send command to Arduino with retry logic

        Args:
            packet: Command packet to send

        Returns:
            bool: True if successful, False otherwise
        """
        with self.lock:
            if not self.connected:
                return False

            for attempt in range(1, Config.MAX_COMMAND_RETRIES + 1):
                try:
                    self.arduino.write(packet)
                    return True
                except Exception as e:
                    self.log(f"Failed to send arduino packet: {packet.decode().strip()} "
                            f"(attempt {attempt}/{Config.MAX_COMMAND_RETRIES}) - {str(e)}")
                    if attempt == Config.MAX_COMMAND_RETRIES:
                        self.log("Failed to establish arduino connection, disconnecting.")
                        self.force_disconnect()
                        return False
                    time.sleep(Config.COMMAND_RETRY_DELAY)
            return False

    def _send_idle_direct(self):
        """Best-effort idle command without retry/disconnect recursion."""
        if not self.connected or not self.arduino:
            return
        try:
            self.arduino.write(b"IDL\n")
        except Exception:
            pass

    def force_disconnect(self):
        """Force disconnection from Arduino and cleanup"""
        # Stop any running test
        if self.state not in ['off', 'connected']:
            self.measuring = False
            self.save_data_to_csv()
            self.log(f"{self.running_test.get()} test stopped")
            self.running_test.set("No test running")
            self.status.set("Resting")
            self.start_test_button.config(text="Start Test", bootstyle=SUCCESS)
            self.state = 'off'
            self.reset_data_variables()

        # Disconnect Arduino
        if self.connected:
            self._send_idle_direct()
            self.connected = False
            try:
                if self.arduino and self.arduino.is_open:
                    self.arduino.close()
            except Exception as e:
                self.log(f"Error closing Arduino connection: {str(e)}")

            self.connect_button.config(text="Connect", bootstyle=PRIMARY)
            self.log("Forced disconnect from Arduino!")

    def _reset_completion_guards(self):
        self._completion_in_progress = False
        self._test_saved = False
        self._completion_email_sent = False
        self.overtemp_warning_email_sent = False

    def _prepare_test_start(self):
        """Reset dashboard and completion state immediately before a test starts."""
        self._reset_completion_guards()
        self.reset_data_variables(reset_visible=False)
        self._reset_cycle_display()

    def _completion_outcome(self, stop_reason: str, completed: bool) -> Tuple[str, str]:
        reason = (stop_reason or "").lower()
        if "error" in reason or "failed" in reason or "invalid" in reason or "stale" in reason:
            return "error", "Error"
        if "overtemperature" in reason:
            return "overtemperature", "Stopped"
        if "user" in reason or not completed:
            return "stopped", "Stopped"
        if "cutoff" in reason or "minimum" in reason or "maximum" in reason or "voltage limit" in reason:
            return "voltage cutoff", "Completed"
        return "completed", "Completed"

    def _current_cycle_data_type(self) -> Optional[str]:
        if self.cycle_state in ("charge", "discharge", "pulsed_charge", "pulsed_discharge"):
            return self.cycle_state
        return None

    def _save_cycle_partial_if_needed(self):
        cycle_type = self._current_cycle_data_type()
        if not cycle_type or not self._elapsed_time_:
            return
        self.log(f"Saving partial cycle {cycle_type} data before test end")
        self._save_cycle_data(cycle_type)

    def _send_completion_email(self, test_name: str, stop_reason: str, completed: bool):
        if self._completion_email_sent:
            return

        outcome, _ = self._completion_outcome(stop_reason, completed)
        duration = self._elapsed_time_[-1] if self._elapsed_time_ else (
            time.time() - self.start_time if self.start_time else self.elapsed_time_
        )
        try:
            sent = send_completion_email(
                test_name=test_name if test_name else "None",
                duration=duration,
                filename=self.filename if self.filename else "None",
                voltage=self._voltage_[-1] if self._voltage_ else self.voltage_,
                current=self._current_[-1] if self._current_ else self.current_,
                temperature=self._temperature_[-1] if self._temperature_ else self.temperature_,
                outcome=outcome,
                stop_reason=stop_reason
            )
            self._completion_email_sent = True
            self.log("Completion email sent" if sent else "Completion email was not sent")
        except Exception as e:
            self._completion_email_sent = True
            self.log(f"Failed to send completion email: {str(e)}")

    def _complete_test(self, stop_reason: str, completed: bool = True,
                       save_raw: bool = True, send_email: bool = True):
        """End any running test through one safe, idempotent path."""
        if self._completion_in_progress:
            return

        self._completion_in_progress = True
        test_state = self.state
        test_name = self.running_test.get() if self.running_test.get() != "No test running" else self.active_test_name
        _, final_status = self._completion_outcome(stop_reason, completed)

        # IDL is intentionally first: terminal/load cutoffs must stop hardware before file/email work.
        self._send_idle_direct()
        self.log("Arduino IDL command sent for test completion")
        self.measuring = False

        if save_raw and not self._test_saved:
            try:
                if test_state == "soc_ocv":
                    self._soc_ocv_finalize(stop_reason)
                elif test_state == "cycle":
                    self._save_cycle_partial_if_needed()
                else:
                    self.save_data_to_csv()
                self._test_saved = True
            except Exception as e:
                self._test_saved = True
                self.log(f"Export/save failed before completion email: {str(e)}")

        if send_email:
            self._send_completion_email(test_name, stop_reason, completed)

        self.status.set(final_status)
        self.log(f"{test_name if test_name else 'Test'} finished: {stop_reason}")
        self.running_test.set("No test running")
        self.start_test_button.config(text="Start Test", bootstyle=SUCCESS)
        self._reset_cycle_display()
        self.state = 'connected' if self.connected else 'off'
        self.active_test_name = ""
        self.overtemp_shutdown = False

        self.reset_data_variables(reset_visible=False)
        if test_state == "soc_ocv":
            self._reset_soc_ocv_variables()

        self._completion_in_progress = False

    def update_voltage(self, value: float):
        """Update voltage display and storage

        Args:
            value: Voltage value in volts
        """
        # Track voltage receipt for mode verification after calibration
        if self.verify_mode_after_calibration:
            self.last_voltage_received_time = time.time()

        self.voltage.set(f"Pack Voltage: {value:.2f} V")
        self.voltage_ = value
        self.update_battery_charge()
        if self.measuring:
            self._voltage_.append(value)

    def update_cell_voltage(self, cell_index: int, value: float):
        """Update a derived 4S cell voltage display and storage."""
        if not (0 <= cell_index < Config.CELL_COUNT):
            return

        self.cell_voltages[cell_index] = value
        self.cell_voltage_vars[cell_index].set(f"Cell {cell_index + 1}: {value:.3f} V")
        valid_cells = [v for v in self.cell_voltages if v > 0]
        if valid_cells:
            self.cell_delta.set(f"Cell Δ: {max(valid_cells) - min(valid_cells):.3f} V")
        self._refresh_battery_displays(cell_index)
        if self.measuring:
            self._cell_voltages[cell_index].append(value)

    def update_tap_voltage(self, tap_index: int, value: float):
        """Update a cumulative tap voltage display and storage."""
        if not (0 <= tap_index < Config.CELL_COUNT):
            return

        self.tap_voltages[tap_index] = value
        self.tap_voltage_vars[tap_index].set(f"Tap {tap_index + 1}S: {value:.3f} V")
        if self.measuring:
            self._tap_voltages[tap_index].append(value)

    def _handle_cell_voltage_packet(self, code: str, value: str) -> bool:
        """Handle C01..C04 cell-voltage packets from the 4S firmware."""
        if len(code) == 3 and code.startswith("C") and code[1:].isdigit():
            try:
                cell_index = int(code[1:]) - 1
                self.update_cell_voltage(cell_index, float(value))
                return True
            except (TypeError, ValueError):
                self.log(f"Invalid cell voltage packet: {code};{value}")
                return True
        return False

    def _handle_tap_voltage_packet(self, code: str, value: str) -> bool:
        """Handle S01..S04 cumulative tap-voltage packets from the 4S firmware."""
        if len(code) == 3 and code.startswith("S") and code[1:].isdigit():
            try:
                tap_index = int(code[1:]) - 1
                self.update_tap_voltage(tap_index, float(value))
                return True
            except (TypeError, ValueError):
                self.log(f"Invalid tap voltage packet: {code};{value}")
                return True
        return False

    def _valid_cell_voltages(self) -> List[float]:
        return [v for v in self.cell_voltages[:Config.CELL_COUNT] if v > 0]

    def _min_cell_voltage(self) -> float:
        cells = self._valid_cell_voltages()
        if cells:
            return min(cells)
        return self.voltage_ / Config.CELL_COUNT if Config.CELL_COUNT else self.voltage_

    def _max_cell_voltage(self) -> float:
        cells = self._valid_cell_voltages()
        if cells:
            return max(cells)
        return self.voltage_ / Config.CELL_COUNT if Config.CELL_COUNT else self.voltage_

    def _measurement_header(self) -> List[str]:
        return (
            ["Time (s)", "Pack Voltage (V)"]
            + [f"Cell {i + 1} Voltage (V)" for i in range(Config.CELL_COUNT)]
            + [f"Tap {i + 1}S Cumulative Voltage (V)" for i in range(Config.CELL_COUNT)]
            + ["Current (A)", "Temperature (°C)"]
        )

    def _measurement_row_count(self) -> int:
        base_lengths = [len(self._elapsed_time_), len(self._voltage_), len(self._current_), len(self._temperature_)]
        positive_base_lengths = [n for n in base_lengths if n > 0]
        if not positive_base_lengths:
            return 0
        return min(positive_base_lengths)

    def _measurement_row(self, index: int, formatted: bool = True) -> List[Any]:
        def get(items, default=""):
            return items[index] if index < len(items) else default

        row = [
            get(self._elapsed_time_),
            get(self._voltage_),
            *[get(self._cell_voltages[i]) if i < len(self._cell_voltages) else "" for i in range(Config.CELL_COUNT)],
            *[get(self._tap_voltages[i]) if i < len(self._tap_voltages) else "" for i in range(Config.CELL_COUNT)],
            get(self._current_),
            get(self._temperature_)
        ]

        if not formatted:
            return row

        formatted_row = []
        for item in row:
            if item == "":
                formatted_row.append("")
            elif isinstance(item, float):
                formatted_row.append(f"{item:.4f}")
            else:
                formatted_row.append(item)
        if isinstance(row[0], float):
            formatted_row[0] = f"{row[0]:.2f}"
        if isinstance(row[-1], float):
            formatted_row[-1] = f"{row[-1]:.2f}"
        return formatted_row

    def update_current(self, value: float):
        """Update current display and storage

        Args:
            value: Current value in amperes
        """
        corrected_value = abs(float(value - self.current_offset))
        self.current.set(f"{corrected_value:.2f} A")
        self.current_ = corrected_value
        if self.measuring:
            self._current_.append(corrected_value)

    def update_elapsed_time(self):
        """Update elapsed time display and storage"""
        value = time.time() - self.start_time
        self.elapsed_time.set(f"Elapsed Time: {value:.2f} s")
        if self.measuring:
            self.elapsed_time_ = value
            self._elapsed_time_.append(value)

    def update_temperature(self, value: float):
        """Update temperature display and storage

        Args:
            value: Temperature value in Celsius
        """
        # Track temperature receipt for mode verification after calibration
        if self.verify_mode_after_calibration:
            self.last_temperature_received_time = time.time()

        self.temperature.set(f"Temperature: {value:.2f} °C")
        self.temperature_ = value
        if self.measuring:
            self._temperature_.append(value)
        if value >= Config.MAX_TEMPERATURE_C:
            self._trigger_overtemp(value)

    def _trigger_overtemp(self, value: float):
        if self.overtemp_shutdown:
            return
        self.overtemp_shutdown = True
        self.arduino_write("IDL\n".encode())
        self.status.set("Overtemperature")
        self.log(f"Overtemperature detected at {value:.2f} °C. Charging/discharging disabled.")

        if not self.overtemp_warning_email_sent:
            try:
                sent = send_warning_email(
                    test_name=self.running_test.get() if self.running_test.get() else "Unknown",
                    temperature=value,
                    filename=self.filename if self.filename else "None",
                    voltage=self.voltage_,
                    current=self.current_
                )
                self.overtemp_warning_email_sent = True
                self.log("Overtemperature warning email sent" if sent else "Overtemperature warning email was not sent")
            except Exception as e:
                self.overtemp_warning_email_sent = True
                self.log(f"Failed to send overtemperature warning email: {str(e)}")

        if self.state not in ['off', 'connected', 'calibrating']:
            self._complete_test("Overtemperature safety stop", completed=False)

    def update_battery_charge(self):
        """Update battery charge visualization based on voltage"""
        self._refresh_battery_displays()

    def _reset_cycle_display(self):
        self.cycle_target.set("Cycle Target: N/A")
        self.cycle_action.set("Cycle Action: N/A")
        self.cycle_progress.set("Cycle Progress: N/A")

    def _reset_soc_ocv_variables(self):
        self.soc_ocv_phase = None
        self.soc_ocv_capacity_discharge_ah = 0.0
        self.soc_ocv_measured_capacity_ah = None
        self.soc_ocv_characterization_discharged_ah = 0.0
        self.soc_ocv_step_discharged_ah = 0.0
        self.soc_ocv_step_ah = Config.SOC_STEP_FRACTION * Config.NOMINAL_CAPACITY_AH
        self.soc_ocv_soc_percent = 100.0
        self.soc_ocv_current_a = None
        self.soc_ocv_last_integrated_time = None
        self.soc_ocv_last_voltage_time = None
        self.soc_ocv_cutoff_voltage = Config.SOC_OCV_CUTOFF_V
        self.soc_ocv_rest_start_time = 0.0
        self.soc_ocv_rest_voltage_history.clear()
        self.soc_ocv_points = []
        self.soc_ocv_step_index = 0
        self.soc_ocv_finalized = False
        self.soc_ocv_stop_reason = ""
        self.soc_ocv_final_cutoff_pending = False
        self.soc_ocv_final_cutoff_rest_completed = False
        self.soc_ocv_capacity_measurement_completed = False
        self.soc_ocv_full_charge_completed = False

    def _update_soc_ocv_display(self):
        measured = (
            f"{self.soc_ocv_measured_capacity_ah:.4f} Ah"
            if self.soc_ocv_measured_capacity_ah and self.soc_ocv_measured_capacity_ah > 0
            else "pending"
        )
        target = (
            f"SOC-OCV Capacity: {measured} | Step: {self.soc_ocv_step_ah:.4f} Ah | "
            f"Cutoff: {self.soc_ocv_cutoff_voltage:.2f} V"
        )
        action = f"SOC-OCV Phase: {self.soc_ocv_phase or 'N/A'}"
        progress = (
            f"SOC {self.soc_ocv_soc_percent:.2f}% | Capacity Q {self.soc_ocv_capacity_discharge_ah:.4f} Ah | "
            f"Char Q {self.soc_ocv_characterization_discharged_ah:.4f} Ah | "
            f"Step {self.soc_ocv_step_discharged_ah:.4f}/{self.soc_ocv_step_ah:.4f} Ah"
        )
        self.cycle_target.set(target)
        self.cycle_action.set(action)
        self.cycle_progress.set(progress)

    def _soc_ocv_start_capacity_discharge(self):
        self.soc_ocv_phase = "capacity_discharge"
        self.soc_ocv_last_integrated_time = None
        self.soc_ocv_last_voltage_time = None
        self.status.set("Discharging")
        self.arduino_write("STD\n".encode())
        self.log(
            f"SOC-OCV starting capacity discharge to per-cell terminal cutoff {self.soc_ocv_cutoff_voltage:.2f} V"
        )
        self._update_soc_ocv_display()

    def _soc_ocv_start_capacity_rest(self, reason: str):
        self.arduino_write("IDL\n".encode())
        self.soc_ocv_phase = "capacity_discharge_rest"
        self.soc_ocv_rest_start_time = time.time()
        self.soc_ocv_rest_voltage_history.clear()
        self.soc_ocv_measured_capacity_ah = self.soc_ocv_capacity_discharge_ah
        self.soc_ocv_soc_percent = 0.0
        self.status.set("Resting")
        self.log(
            f"Capacity cutoff reached ({reason}). Measured discharge so far: "
            f"{self.soc_ocv_capacity_discharge_ah:.4f} Ah. Resting for 0% OCV."
        )

    def _soc_ocv_start_full_charge(self):
        self.soc_ocv_phase = "charge"
        self.soc_ocv_last_integrated_time = None
        self.status.set("Charging")
        self.arduino_write("STC\n".encode())
        self.log(f"Starting full charge to {Config.CELL_MAX_VOLTAGE:.2f} V/cell ({Config.BATTERY_MAX_VOLTAGE:.2f} V pack)")

    def _soc_ocv_start_full_charge_rest(self, reason: str):
        self.arduino_write("IDL\n".encode())
        self.soc_ocv_phase = "full_charge_rest"
        self.soc_ocv_rest_start_time = time.time()
        self.soc_ocv_rest_voltage_history.clear()
        self.status.set("Resting")
        self.log(f"Full charge reached ({reason}). Resting for 100% OCV.")

    def _soc_ocv_start_characterization_discharge(self):
        self.soc_ocv_phase = "characterization_discharge"
        self.soc_ocv_last_integrated_time = None
        self.status.set("Discharging")
        self.arduino_write("STD\n".encode())
        self.log(
            f"Starting 5% SOC-OCV characterization using {self.soc_ocv_step_ah:.4f} Ah steps"
        )

    def _soc_ocv_start_characterization_rest(self, reason: str):
        self.arduino_write("IDL\n".encode())
        self.soc_ocv_phase = "characterization_rest"
        self.soc_ocv_rest_start_time = time.time()
        self.soc_ocv_rest_voltage_history.clear()
        self.status.set("Resting")
        self.log(
            f"Characterization step reached ({reason}). Resting at SOC {self.soc_ocv_soc_percent:.2f}%"
        )

    def _soc_ocv_start_final_rest(self, reason: str):
        self.arduino_write("IDL\n".encode())
        self.soc_ocv_phase = "final_rest"
        self.soc_ocv_final_cutoff_pending = True
        self.soc_ocv_rest_start_time = time.time()
        self.soc_ocv_rest_voltage_history.clear()
        self.status.set("Resting")
        self.log(
            f"Final cutoff reached ({reason}). Active discharge stopped immediately; resting for final OCV."
        )

    def _soc_ocv_integrate_discharge(self, currenttime: float):
        if self.soc_ocv_phase not in ("capacity_discharge", "characterization_discharge"):
            return
        if self.soc_ocv_current_a is None:
            self.soc_ocv_last_integrated_time = currenttime
            return
        if self.soc_ocv_last_integrated_time is None:
            self.soc_ocv_last_integrated_time = currenttime
            return

        delta_s = currenttime - self.soc_ocv_last_integrated_time
        self.soc_ocv_last_integrated_time = currenttime
        if delta_s <= 0:
            return
        if delta_s > 60:
            self.log("SOC-OCV skipped an invalid integration interval greater than 60 seconds")
            return

        dQ_Ah = abs(self.soc_ocv_current_a) * delta_s / 3600.0
        if self.soc_ocv_phase == "capacity_discharge":
            self.soc_ocv_capacity_discharge_ah += dQ_Ah
        else:
            self.soc_ocv_characterization_discharged_ah += dQ_Ah
            self.soc_ocv_step_discharged_ah += dQ_Ah
            capacity = self.soc_ocv_measured_capacity_ah or Config.NOMINAL_CAPACITY_AH
            if capacity > 0:
                self.soc_ocv_soc_percent = 100.0 * (
                    1.0 - self.soc_ocv_characterization_discharged_ah / capacity
                )
                self.soc_ocv_soc_percent = max(0.0, min(100.0, self.soc_ocv_soc_percent))

    def _soc_ocv_is_rest_stable(self, currenttime: float) -> Tuple[bool, float, float]:
        rest_elapsed = currenttime - self.soc_ocv_rest_start_time
        voltage_change = 0.0
        reference_voltage = None
        target_time = currenttime - Config.SOC_OCV_RELAX_WINDOW_S

        for timestamp, voltage in self.soc_ocv_rest_voltage_history:
            if timestamp <= target_time:
                reference_voltage = voltage
            else:
                break

        if reference_voltage is not None:
            voltage_change = self.voltage_ - reference_voltage
        elif self.soc_ocv_rest_voltage_history:
            voltage_change = self.voltage_ - self.soc_ocv_rest_voltage_history[0][1]

        stable = (
            reference_voltage is not None
            and rest_elapsed >= Config.SOC_OCV_RELAX_WINDOW_S
            and abs(voltage_change) <= Config.SOC_OCV_RELAX_THRESHOLD_V
        )
        fallback_timeout = rest_elapsed >= Config.SOC_OCV_FALLBACK_REST_S
        ready = stable or fallback_timeout
        return ready, rest_elapsed, voltage_change

    def _soc_ocv_accept_rest_point(self, point_type: str, rest_duration_s: float, voltage_change_v: float):
        if point_type == "capacity_0_percent":
            soc_percent = 0.0
            cumulative_ah = self.soc_ocv_capacity_discharge_ah
            self.soc_ocv_capacity_measurement_completed = True
            measured = self.soc_ocv_measured_capacity_ah or 0.0
            if measured <= 0:
                self.log(
                    f"Measured capacity {measured:.4f} Ah is invalid; falling back to nominal capacity "
                    f"{Config.NOMINAL_CAPACITY_AH:.4f} Ah for SOC-OCV step size"
                )
                self.soc_ocv_measured_capacity_ah = Config.NOMINAL_CAPACITY_AH
            self.soc_ocv_step_ah = Config.SOC_STEP_FRACTION * self.soc_ocv_measured_capacity_ah
            self.log(
                f"Capacity measured: {self.soc_ocv_measured_capacity_ah:.4f} Ah; "
                f"step size set to {self.soc_ocv_step_ah:.4f} Ah"
            )
        elif point_type == "full_charge_100_percent":
            soc_percent = 100.0
            cumulative_ah = 0.0
            self.soc_ocv_full_charge_completed = True
            self.soc_ocv_characterization_discharged_ah = 0.0
            self.soc_ocv_step_discharged_ah = 0.0
            self.soc_ocv_soc_percent = 100.0
            self.log("Full charge rest accepted; 100% OCV point recorded")
        else:
            capacity = self.soc_ocv_measured_capacity_ah or Config.NOMINAL_CAPACITY_AH
            soc_percent = 100.0 * (1.0 - self.soc_ocv_characterization_discharged_ah / capacity)
            soc_percent = max(0.0, min(100.0, soc_percent))
            self.soc_ocv_soc_percent = soc_percent
            cumulative_ah = self.soc_ocv_characterization_discharged_ah
            if point_type == "final_cutoff":
                self.soc_ocv_final_cutoff_rest_completed = True
                self.log("Final rest accepted; final cutoff OCV point recorded")
            else:
                self.log("Rest accepted; characterization OCV point recorded")

        point = {
            "step_index": self.soc_ocv_step_index,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "SOC_percent": round(soc_percent, 4),
            "cumulative_discharged_Ah": round(cumulative_ah, 6),
            "relaxed_voltage_V": round(self.voltage_, 5),  # Pack OCV kept for backward compatibility.
            "relaxed_pack_voltage_V": round(self.voltage_, 5),
            "rest_duration_s": round(rest_duration_s, 2),
            "voltage_change_during_rest_V": round(voltage_change_v, 6),
            "temperature_C": round(self.temperature_, 2),
            "point_type": point_type
        }
        for idx, cell_v in enumerate(self.cell_voltages[:Config.CELL_COUNT], start=1):
            point[f"relaxed_cell_{idx}_voltage_V"] = round(cell_v, 5)
        self.soc_ocv_points.append(point)
        self.log(
            f"Recorded {point_type} point #{self.soc_ocv_step_index}: "
            f"SOC={point['SOC_percent']:.2f}%, OCV={point['relaxed_voltage_V']:.4f} V, "
            f"rest={point['rest_duration_s']:.1f} s"
        )
        self.soc_ocv_step_index += 1

    def _soc_ocv_export_outputs(self):
        if not self.filename:
            return None

        folder_path = os.path.join(Config.DATA_DIR, self.filename)
        os.makedirs(folder_path, exist_ok=True)

        csv_path = os.path.join(folder_path, "ocv_soc_points.csv")
        json_path = os.path.join(folder_path, "ocv_soc_points.json")
        lut_csv_path = os.path.join(folder_path, "ocv_soc_lookup_1pct.csv")
        raw_csv_path = os.path.join(folder_path, "raw_timeseries.csv")

        point_fields = [
            "step_index",
            "timestamp",
            "SOC_percent",
            "cumulative_discharged_Ah",
            "relaxed_voltage_V",
            "relaxed_pack_voltage_V",
            *[f"relaxed_cell_{i + 1}_voltage_V" for i in range(Config.CELL_COUNT)],
            "rest_duration_s",
            "voltage_change_during_rest_V",
            "temperature_C",
            "point_type"
        ]
        with open(csv_path, mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=point_fields)
            writer.writeheader()
            writer.writerows(self.soc_ocv_points)

        raw_exported = False
        row_count = self._measurement_row_count()
        if row_count > 0:
            with open(raw_csv_path, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(self._measurement_header())
                for i in range(row_count):
                    writer.writerow(self._measurement_row(i, formatted=True))
            raw_exported = True

        valid_points = [
            p for p in self.soc_ocv_points
            if p.get("relaxed_voltage_V", 0) > 0 and 0 <= p.get("SOC_percent", -1) <= 100
        ]
        lut_rows = []
        if len(valid_points) >= 2:
            sorted_points = sorted(valid_points, key=lambda p: p["SOC_percent"])
            socs = np.array([p["SOC_percent"] for p in sorted_points], dtype=float)
            ocvs = np.array([p["relaxed_voltage_V"] for p in sorted_points], dtype=float)
            socs_unique, idx = np.unique(socs, return_index=True)
            ocvs_unique = ocvs[idx]
            soc_grid = np.arange(0.0, 101.0, 1.0)
            ocv_grid = np.interp(soc_grid, socs_unique, ocvs_unique)
            lut_rows = [{"SOC_percent": float(s), "OCV_V": float(v)} for s, v in zip(soc_grid, ocv_grid)]

        with open(lut_csv_path, mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=["SOC_percent", "OCV_V"])
            writer.writeheader()
            if lut_rows:
                writer.writerows(lut_rows)

        rest_values = [p["rest_duration_s"] for p in self.soc_ocv_points]
        avg_rest_time = float(np.mean(rest_values)) if rest_values else 0.0
        summary = {
            "total_ocv_points": len(self.soc_ocv_points),
            "average_rest_time_s": round(avg_rest_time, 2),
            "stop_reason": self.soc_ocv_stop_reason,
            "raw_timeseries_exported": raw_exported
        }

        payload = {
            "meta": {
                "topology": f"{Config.CELL_COUNT}S{Config.PARALLEL_COUNT}P",
                "nominal_capacity_Ah": Config.NOMINAL_CAPACITY_AH,
                "measured_capacity_Ah": self.soc_ocv_measured_capacity_ah,
                "step_fraction": Config.SOC_STEP_FRACTION,
                "step_Ah": self.soc_ocv_step_ah,
                "cutoff_cell_voltage_V": self.soc_ocv_cutoff_voltage,
                "max_cell_voltage_V": Config.CELL_MAX_VOLTAGE,
                "max_pack_voltage_V": Config.BATTERY_MAX_VOLTAGE,
                "relax_window_s": Config.SOC_OCV_RELAX_WINDOW_S,
                "relax_threshold_V": Config.SOC_OCV_RELAX_THRESHOLD_V,
                "fallback_rest_s": Config.SOC_OCV_FALLBACK_REST_S,
                "stop_reason": self.soc_ocv_stop_reason,
                "total_ocv_points": len(self.soc_ocv_points),
                "final_cutoff_rest_completed": self.soc_ocv_final_cutoff_rest_completed,
                "capacity_measurement_completed": self.soc_ocv_capacity_measurement_completed,
                "full_charge_completed": self.soc_ocv_full_charge_completed
            },
            "summary": summary,
            "points": self.soc_ocv_points,
            "interpolation_lut_1pct": lut_rows
        }
        with open(json_path, mode='w', encoding='utf-8') as file:
            json.dump(payload, file, indent=2)

        return {
            "folder": folder_path,
            "csv": csv_path,
            "json": json_path,
            "lut_csv": lut_csv_path,
            "raw_csv": raw_csv_path if raw_exported else None,
            "summary": summary
        }

    def _soc_ocv_finalize(self, stop_reason: str):
        if self.soc_ocv_finalized:
            return
        self.soc_ocv_finalized = True
        self.soc_ocv_stop_reason = stop_reason
        self.soc_ocv_phase = "completed"
        export_info = self._soc_ocv_export_outputs()
        if export_info:
            self.log(f"SOC-OCV export complete: {export_info['folder']}")
            self.log(f"OCV points exported: {export_info['summary']['total_ocv_points']}")

    def _handle_soc_ocv_rest_phase(self, currenttime: float):
        self.soc_ocv_rest_voltage_history.append((currenttime, self.voltage_))
        ready, rest_elapsed, voltage_change = self._soc_ocv_is_rest_stable(currenttime)
        if not ready:
            return
        if abs(self.current_) > Config.SOC_OCV_ZERO_CURRENT_THRESHOLD_A:
            self.log(
                f"Rest ready but current is {self.current_:.3f} A; waiting for near-zero current before OCV"
            )
            return

        phase = self.soc_ocv_phase
        if phase == "capacity_discharge_rest":
            self._soc_ocv_accept_rest_point("capacity_0_percent", rest_elapsed, voltage_change)
            self._soc_ocv_start_full_charge()
        elif phase == "full_charge_rest":
            self._soc_ocv_accept_rest_point("full_charge_100_percent", rest_elapsed, voltage_change)
            self._soc_ocv_start_characterization_discharge()
        elif phase == "characterization_rest":
            self._soc_ocv_accept_rest_point("characterization_step", rest_elapsed, voltage_change)
            self.soc_ocv_step_discharged_ah = 0.0
            if self.soc_ocv_soc_percent <= 0.0:
                self._complete_test("Completed 5% characterization down to 0% SOC", completed=True)
            else:
                self._soc_ocv_start_characterization_discharge()
        elif phase == "final_rest":
            self._soc_ocv_accept_rest_point("final_cutoff", rest_elapsed, voltage_change)
            self._complete_test("Completed SOC-OCV characterization at terminal voltage cutoff", completed=True)

    def _handle_soc_ocv_state(self, code: str, value: str):
        currenttime = time.time()
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            numeric_value = 0.0

        if code == 'VVV':
            self.update_voltage(numeric_value)
            self.soc_ocv_last_voltage_time = currenttime
        elif code == 'III':
            self.update_current(numeric_value)
            self.soc_ocv_current_a = self.current_
        elif code == 'TTT':
            self.update_temperature(numeric_value)
            if self.state != "soc_ocv":
                return
        elif code == 'DDD':
            self.update_elapsed_time()

        if self.state != "soc_ocv" or self.overtemp_shutdown:
            return

        self._soc_ocv_integrate_discharge(currenttime)

        active_discharge = self.soc_ocv_phase in ("capacity_discharge", "characterization_discharge")
        if code == 'MIN':
            if self.soc_ocv_phase == "capacity_discharge":
                self._soc_ocv_start_capacity_rest("MIN packet")
            elif self.soc_ocv_phase == "characterization_discharge":
                self._soc_ocv_start_final_rest("MIN packet")
            self._update_soc_ocv_display()
            return

        if active_discharge:
            stale_voltage = (
                self.soc_ocv_last_voltage_time is None
                and currenttime - self.start_time > 5
            ) or (
                self.soc_ocv_last_voltage_time is not None
                and currenttime - self.soc_ocv_last_voltage_time > 5
            )
            if stale_voltage or not math.isfinite(self.voltage_):
                self.log("SOC-OCV voltage reading is stale or invalid during active discharge")
                self._complete_test("Error: stale or invalid SOC-OCV voltage reading", completed=False)
                return

        # This is terminal/load cell voltage while discharging, not relaxed OCV.
        min_cell_v = self._min_cell_voltage()
        max_cell_v = self._max_cell_voltage()
        if active_discharge and min_cell_v <= self.soc_ocv_cutoff_voltage:
            reason = f"minimum cell terminal voltage {min_cell_v:.3f} V"
            if self.soc_ocv_phase == "capacity_discharge":
                self._soc_ocv_start_capacity_rest(reason)
            else:
                self._soc_ocv_start_final_rest(reason)
            self._update_soc_ocv_display()
            return

        if self.soc_ocv_phase == "charge" and (code in ('MAX', 'END') or max_cell_v >= Config.CELL_MAX_VOLTAGE):
            if code == 'MAX':
                reason = "maximum cell-voltage cutoff"
            elif code == 'END':
                reason = f"charge-end current {numeric_value:.3f} A"
            else:
                reason = f"maximum cell voltage {max_cell_v:.3f} V"
            self._soc_ocv_start_full_charge_rest(reason)
            self._update_soc_ocv_display()
            return

        if self.soc_ocv_phase == "characterization_discharge":
            measured_capacity = self.soc_ocv_measured_capacity_ah or Config.NOMINAL_CAPACITY_AH
            if self.soc_ocv_characterization_discharged_ah >= measured_capacity:
                self._soc_ocv_start_characterization_rest("0% SOC reached by measured capacity")
            elif self.soc_ocv_step_discharged_ah >= self.soc_ocv_step_ah:
                self._soc_ocv_start_characterization_rest("5% measured-capacity step reached")

        if self.soc_ocv_phase in ("capacity_discharge_rest", "full_charge_rest", "characterization_rest", "final_rest") and code == 'VVV':
            self._handle_soc_ocv_rest_phase(currenttime)
            if self.state != "soc_ocv":
                return

        self._update_soc_ocv_display()

    def _format_cycle_progress(self, step_index: int, target_mode: str, is_rest: bool = False,
                               next_step_index: Optional[int] = None, next_target: Optional[str] = None,
                               is_pulsed: bool = False) -> str:
        total = "infinite" if self.cycle_number == 0 else str(self.cycle_number)
        cycle_index = self.cycle_count + 1
        step_label = "First" if step_index == 1 else "Second"
        pulsed_text = " (pulsed)" if is_pulsed else ""
        if is_rest and next_step_index is not None and next_target is not None:
            next_step_label = "First" if next_step_index == 1 else "Second"
            return (
                f"Cycle {cycle_index} of {total} - Resting before {next_step_label} step "
                f"{next_step_index}/2 ({next_target}{pulsed_text})"
            )
        return (
            f"Cycle {cycle_index} of {total} - {step_label} step {step_index}/2 "
            f"({target_mode}{pulsed_text})"
        )

    def _update_cycle_display(self, target_mode: str, action: str, progress: str):
        self.cycle_target.set(f"Cycle Target: {target_mode}")
        self.cycle_action.set(f"Cycle Action: {action}")
        self.cycle_progress.set(f"Cycle Progress: {progress}")

    def _is_pulsed_cycle(self, cycle_index: int) -> bool:
        if cycle_index == 1:
            return True
        if cycle_index % 10 == 0:
            return True
        if self.cycle_number > 0 and cycle_index == self.cycle_number:
            return True
        return False

    def _cycle_step_index(self, target_mode: str) -> int:
        return 1 if target_mode.lower() == self.cycle_start else 2

    def _start_cycle_step(self, target_mode: str, pulsed: bool):
        is_charge = target_mode.lower() == "charge"
        if target_mode.lower() == self.cycle_start:
            self.cycle_is_pulsed = pulsed
            total_text = self.cycle_number if self.cycle_number > 0 else "infinite"
            pulsed_text = " (pulsed)" if pulsed else ""
            self.log(f"Starting cycle {self.cycle_count + 1}/{total_text}{pulsed_text}")

        if pulsed:
            self.cycle_state = "pulsed_charge" if is_charge else "pulsed_discharge"
            self.cycle_pulsed_state = "resting"
            self.cycle_pulsed_time = time.time()
            self.status.set("Resting")
            self.arduino_write(("SPC\n" if is_charge else "SPD\n").encode())
        else:
            self.cycle_state = "charge" if is_charge else "discharge"
            self.status.set("Charging" if is_charge else "Discharging")
            self.arduino_write(("STC\n" if is_charge else "STD\n").encode())

        self.measuring = True
        self.start_time = time.time()

    def _cycle_action_label(self, target_mode: str) -> str:
        if self.cycle_state in ("pulsed_charge", "pulsed_discharge"):
            if self.cycle_pulsed_state == "resting":
                return "Pulsed Resting"
            if self.cycle_pulsed_state == "charging":
                return "Pulsed Charging"
            if self.cycle_pulsed_state == "discharging":
                return "Pulsed Discharging"
            return "Pulsed"
        return "Charging" if target_mode == "Charge" else "Discharging"

    def _finish_cycle_step(self, mode: str, cycle_type: str) -> bool:
        self.arduino_write("IDL\n".encode())
        self.cycle_last_state = mode
        self.cycle_pulsed_state = None
        self.measuring = False
        self._save_cycle_data(cycle_type)
        self.reset_data_variables(reset_visible=False)

        step_index = self._cycle_step_index(mode)
        if step_index == 2:
            self.cycle_count += 1
            if self.cycle_number > 0 and self.cycle_count >= self.cycle_number:
                self.log("All cycles completed!")
                self._test_saved = True
                self._complete_test("All cycles completed", completed=True, save_raw=False)
                return True

        self.cycle_state = "rest"
        self.status.set("Calibrating")
        self.start_time = time.time()

        # Perform between-cycle calibration
        self.log("Starting between-cycle calibration...")
        self.calibration_count = 0
        self.calibration_sum = 0
        self.cycle_calibrating = True
        self.arduino_write("CSC\n".encode())
        self.calibration_button.config(text="Calibrating", bootstyle=WARNING, state=DISABLED)
        self.state = 'calibrating'
        return False

    def _enqueue_event(self, event: Tuple[str, ...]):
        """Queue events from the reader thread for UI-thread processing."""
        try:
            self.event_queue.put_nowait(event)
        except queue.Full:
            try:
                self.event_queue.get_nowait()
            except queue.Empty:
                return
            try:
                self.event_queue.put_nowait(event)
            except queue.Full:
                pass

    def _process_event_queue(self):
        """Process queued events on the UI thread."""
        processed = 0
        while processed < 200:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break

            event_type = event[0]
            if event_type == "packet":
                _, code, value = event
                self.machine_state(code, value)
            elif event_type == "log":
                _, message = event
                self.log(message)
            elif event_type == "disconnect":
                _, message = event
                self.log(message)
                self.force_disconnect()
            processed += 1

        # Check if Arduino is stuck in calibration mode after calibration completes
        self._check_arduino_mode_after_calibration()

        if self.winfo_exists():
            self.after(20, self._process_event_queue)

    def _check_arduino_mode_after_calibration(self):
        """Verify Arduino mode after calibration and resend command if stuck in calibration.

        During calibration, Arduino only sends current (III) data.
        After calibration, it should send voltage (VVV), current (III), and temperature (TTT).
        If we don't receive voltage/temp within a timeout, Arduino is stuck in calibration mode.
        """
        if not self.verify_mode_after_calibration:
            return

        current_time = time.time()
        retry_seconds = 2.0

        # Check if we've received both voltage and temperature data
        if self.last_voltage_received_time > 0 and self.last_temperature_received_time > 0:
            # Arduino has exited calibration mode successfully
            self.log("Arduino confirmed to have exited calibration mode successfully")
            self.verify_mode_after_calibration = False
            self.last_voltage_received_time = 0
            self.last_temperature_received_time = 0
            return

        # If normal telemetry has not resumed, keep nudging the firmware back to idle.
        if current_time - self.mode_verify_timeout >= retry_seconds:
            # Arduino is stuck in calibration mode - resend idle command
            self.log("WARNING: Arduino appears stuck in calibration mode (no voltage/temp data). Resending idle command...")
            self.arduino_write("IDL\n".encode())
            # Reset timeout to try again
            self.mode_verify_timeout = current_time


    def packet_reader(self):
        """Thread function to continuously read packets from Arduino"""
        while self.connected:
            try:
                bytes_to_read = self.arduino.inWaiting()

                if bytes_to_read > 0:
                    packet = self.arduino.readline().decode("utf-8", errors="replace").strip()

                    # Skip empty packets
                    if not packet:
                        continue

                    try:
                        parts = packet.split(';')
                        if len(parts) != 3:
                            # Silently ignore improperly formatted packets (startup messages, debug output)
                            # Only log if it looks like it should be a valid packet
                            if ';' in packet:
                                self._enqueue_event(("log", f"Malformed packet: {packet}"))
                            continue

                        code, value, control_byte = parts

                        if control_byte != '1':
                            self._enqueue_event(("log", f"Invalid control byte in packet: {packet}"))
                            continue

                        self._enqueue_event(("packet", code, value))

                    except ValueError as e:
                        # Only log parsing errors for packets that look valid
                        if ';' in packet:
                            self._enqueue_event(("log", f"Parse error: {packet} - {e}"))

            except Exception as e:
                self._enqueue_event(("disconnect", f"Error in packet reader: {str(e)}"))
                break

            time.sleep(0.01)  # Small delay to prevent CPU overuse

    def machine_state(self, code: str, value: str):
        """Main state machine handler for processing Arduino data

        Args:
            code: Command code from Arduino
            value: Data value from Arduino
        """
        # Dispatch common 4S telemetry before state-specific logic.
        if self._handle_cell_voltage_packet(code, value):
            return
        if self._handle_tap_voltage_packet(code, value):
            return

        # Dispatch based on machine state
        if self.state == 'off':
            return

        elif self.state == 'connected':
            self._handle_connected_state(code, value)

        elif self.state == 'calibrating':
            self._handle_calibration_state(code, value)

        elif self.state == 'measuring':
            self._handle_measuring_state(code, value)

        elif self.state in ['pulsed_charge', 'pulsed_discharge']:
            self._handle_pulsed_state(code, value)

        elif self.state == 'cycle':
            self._handle_cycle_state(code, value)

        elif self.state == 'soc_ocv':
            self._handle_soc_ocv_state(code, value)

        else:
            self.log(f"Unhandled machine state: {self.state}")

    def _handle_connected_state(self, code: str, value: str):
        """Handle data in connected state"""
        if code == 'VVV':
            self.update_voltage(float(value))
        elif code == 'III':
            self.update_current(float(value))
        elif code == 'TTT':
            self.update_temperature(float(value))

    def _handle_calibration_state(self, code: str, value: str):
        """Handle calibration state"""
        if self.calibration_number <= 0:
            self.calibration_number = 1

        if code != 'III' or self.calibration_count >= self.calibration_number:
            return

        self.calibration_sum += float(value)
        self.calibration_count += 1
        self.log(f"Calibration progress: {self.calibration_count}/{self.calibration_number}")

        if self.calibration_count >= self.calibration_number:
            self._complete_calibration()

    def _complete_calibration(self):
        """Finish current calibration and return the Arduino to idle telemetry."""
        self.current_offset = self.calibration_sum / self.calibration_number
        self.log(f"Calibration complete! Current offset: {self.current_offset:.8f} A")
        self.offset.set(f"Current Offset: {self.current_offset:.8f} A")
        self.calibration_button.config(text="Calibrate", bootstyle=PRIMARY, state=tk.NORMAL)

        # Calibration firmware emits only current packets. Return it to idle
        # and confirm that normal voltage and temperature telemetry resumes.
        self.verify_mode_after_calibration = True
        self.mode_verify_timeout = time.time()
        self.last_voltage_received_time = 0
        self.last_temperature_received_time = 0

        if self.cycle_calibrating:
            # Return to cycle rest state to continue with the next step.
            self.cycle_calibrating = False
            self.state = 'cycle'
            self.start_time = time.time()
            self.status.set("Resting")
            self.log("Between-cycle calibration complete. Resuming rest period...")
        else:
            self.state = 'connected'
            self.log("Calibration complete. Returning Arduino to idle mode...")

        self.arduino_write("IDL\n".encode())

    def _handle_measuring_state(self, code: str, value: str):
        """Handle measuring state"""
        if code == 'VVV':
            self.update_voltage(float(value))
        elif code == 'III':
            self.update_current(float(value))
        elif code == 'TTT':
            self.update_temperature(float(value))
            if self.state != 'measuring':
                return
        elif code == 'DDD':
            self.update_elapsed_time()
        elif code == 'MAX':
            if not self.overtemp_shutdown:
                self.log(f"Maximum cell voltage reached at {float(value):.2f} V")
                self._complete_test("Maximum cell-voltage cutoff reached", completed=True)
        elif code == 'END':
            if not self.overtemp_shutdown:
                self.log(f"Charge-end current reached at {float(value):.3f} A")
                self._complete_test("Charge-end current cutoff reached", completed=True)
        elif code == 'MIN':
            if not self.overtemp_shutdown:
                self.log(f"Minimum cell voltage reached at {float(value):.2f} V")
                self._complete_test("Minimum cell-voltage cutoff reached", completed=True)

    def _handle_pulsed_state(self, code: str, value: str):
        """Handle pulsed charge/discharge state"""
        # Update measurements
        if code == 'VVV':
            self.update_voltage(float(value))
        elif code == 'III':
            self.update_current(float(value))
        elif code == 'TTT':
            self.update_temperature(float(value))
            if self.state not in ['pulsed_charge', 'pulsed_discharge']:
                return
        elif code == 'DDD':
            self.update_elapsed_time()
        elif code == 'MAX':
            self.log(f"Maximum cell voltage reached at {float(value):.2f} V")
            self._complete_test("Maximum cell-voltage cutoff reached", completed=True)
            return
        elif code == 'END':
            self.log(f"Charge-end current reached at {float(value):.3f} A")
            self._complete_test("Charge-end current cutoff reached", completed=True)
            return
        elif code == 'MIN':
            self.log(f"Minimum cell voltage reached at {float(value):.2f} V")
            self._complete_test("Minimum cell-voltage cutoff reached", completed=True)
            return

        if self.overtemp_shutdown:
            return

        is_charge = self.state == 'pulsed_charge'
        current_time = time.time()

        if self.pct_state == 'resting':
            if current_time - self.pct_time >= self.pct_resting_period:
                self.pct_state = 'charging' if is_charge else 'discharging'
                self.arduino_write(("STC\n" if is_charge else "STD\n").encode())
                self.pct_time = current_time
                self.status.set("Charging" if is_charge else "Discharging")

        elif self.pct_state in ('charging', 'discharging'):
            if current_time - self.pct_time >= self.pct_do_period:
                self.pct_state = 'resting'
                self.arduino_write(("SPC\n" if is_charge else "SPD\n").encode())
                self.pct_time = current_time
                self.status.set("Resting")

    def _handle_cycle_state(self, code: str, value: str):
        """Handle cycle test state"""
        if self.cycle_state == 'rest':
            if code == 'VVV':
                self.update_voltage(float(value))
            elif code == 'III':
                self.update_current(float(value))
            elif code == 'TTT':
                self.update_temperature(float(value))
                if self.state != 'cycle':
                    return

            next_target = "Discharge" if self.cycle_last_state == 'charge' else "Charge"
            if self.cycle_last_state is None:
                next_target = "Charge" if self.cycle_start == 'charge' else "Discharge"
            next_step_index = self._cycle_step_index(next_target)
            next_is_pulsed = self.cycle_is_pulsed
            if next_target.lower() == self.cycle_start:
                next_is_pulsed = self._is_pulsed_cycle(self.cycle_count + 1)

            rest_progress = self._format_cycle_progress(
                step_index=next_step_index,
                target_mode=next_target,
                is_rest=True,
                next_step_index=next_step_index,
                next_target=next_target,
                is_pulsed=next_is_pulsed
            )
            action_text = "Overtemperature" if self.overtemp_shutdown else "Resting"
            self._update_cycle_display(next_target, action_text, rest_progress)

            if self.overtemp_shutdown:
                return

            if time.time() - self.start_time >= Config.CYCLE_TRANSITION_MIN_SECONDS:
                if next_target.lower() == self.cycle_start:
                    if self.cycle_number > 0 and self.cycle_count >= self.cycle_number:
                        self.log("All cycles completed!")
                        self._complete_test("All cycles completed", completed=True, save_raw=False)
                        return

                self._start_cycle_step(next_target, next_is_pulsed)
                step_index = self._cycle_step_index(next_target)
                progress = self._format_cycle_progress(step_index, next_target, is_pulsed=next_is_pulsed)
                action = self._cycle_action_label(next_target)
                self._update_cycle_display(next_target, action, progress)

        elif self.cycle_state == 'charge':
            step_index = self._cycle_step_index("Charge")
            progress = self._format_cycle_progress(step_index, "Charge", is_pulsed=self.cycle_is_pulsed)
            self._update_cycle_display("Charge", "Charging", progress)

            if code == 'VVV':
                self.update_voltage(float(value))
            elif code == 'III':
                self.update_current(float(value))
            elif code == 'TTT':
                self.update_temperature(float(value))
                if self.state != 'cycle':
                    return
            elif code == 'DDD':
                self.update_elapsed_time()
            elif code == 'MAX':
                self.log(f"Maximum cell voltage reached at {float(value):.2f} V")
                if self._finish_cycle_step("charge", "charge"):
                    return
            elif code == 'END':
                self.log(f"Charge-end current reached at {float(value):.3f} A")
                if self._finish_cycle_step("charge", "charge"):
                    return

        elif self.cycle_state == 'discharge':
            step_index = self._cycle_step_index("Discharge")
            progress = self._format_cycle_progress(step_index, "Discharge", is_pulsed=self.cycle_is_pulsed)
            self._update_cycle_display("Discharge", "Discharging", progress)

            if code == 'VVV':
                self.update_voltage(float(value))
            elif code == 'III':
                self.update_current(float(value))
            elif code == 'TTT':
                self.update_temperature(float(value))
                if self.state != 'cycle':
                    return
            elif code == 'DDD':
                self.update_elapsed_time()
            elif code == 'MIN':
                self.log(f"Minimum cell voltage reached at {float(value):.2f} V")
                if self._finish_cycle_step("discharge", "discharge"):
                    return

        elif self.cycle_state in ('pulsed_charge', 'pulsed_discharge'):
            if code == 'VVV':
                self.update_voltage(float(value))
            elif code == 'III':
                self.update_current(float(value))
            elif code == 'TTT':
                self.update_temperature(float(value))
                if self.state != 'cycle':
                    return
            elif code == 'DDD':
                self.update_elapsed_time()
            elif code == 'MAX' and self.cycle_state == 'pulsed_charge':
                self.log(f"Maximum cell voltage reached at {float(value):.2f} V")
                if self._finish_cycle_step("charge", "pulsed_charge"):
                    return
            elif code == 'END' and self.cycle_state == 'pulsed_charge':
                self.log(f"Charge-end current reached at {float(value):.3f} A")
                if self._finish_cycle_step("charge", "pulsed_charge"):
                    return
            elif code == 'MIN' and self.cycle_state == 'pulsed_discharge':
                self.log(f"Minimum cell voltage reached at {float(value):.2f} V")
                if self._finish_cycle_step("discharge", "pulsed_discharge"):
                    return

            if self.overtemp_shutdown:
                return

            target_mode = "Charge" if self.cycle_state == "pulsed_charge" else "Discharge"
            step_index = self._cycle_step_index(target_mode)
            progress = self._format_cycle_progress(step_index, target_mode, is_pulsed=True)
            action = self._cycle_action_label(target_mode)
            self._update_cycle_display(target_mode, action, progress)

            current_time = time.time()
            if self.cycle_pulsed_state == 'resting':
                if current_time - self.cycle_pulsed_time >= self.cycle_pulsed_resting_period:
                    self.cycle_pulsed_state = 'charging' if self.cycle_state == 'pulsed_charge' else 'discharging'
                    self.arduino_write(("STC\n" if self.cycle_state == 'pulsed_charge' else "STD\n").encode())
                    self.cycle_pulsed_time = current_time
                    self.status.set("Charging" if self.cycle_state == 'pulsed_charge' else "Discharging")

            elif self.cycle_pulsed_state in ('charging', 'discharging'):
                if current_time - self.cycle_pulsed_time >= self.cycle_pulsed_do_period:
                    self.cycle_pulsed_state = 'resting'
                    self.arduino_write(("SPC\n" if self.cycle_state == 'pulsed_charge' else "SPD\n").encode())
                    self.cycle_pulsed_time = current_time
                    self.status.set("Resting")

    def _save_cycle_data(self, cycle_type: str):
        """Save cycle data to file

        Args:
            cycle_type: Type of cycle ('charge', 'discharge', 'pulsed_charge', 'pulsed_discharge')
        """
        cycle_index = self.cycle_count + 1
        folder_path = os.path.join(Config.DATA_DIR, self.filename, str(cycle_index))
        os.makedirs(folder_path, exist_ok=True)

        file_labels = {
            "charge": "C",
            "discharge": "D",
            "pulsed_charge": "PC",
            "pulsed_discharge": "PD"
        }
        file_label = file_labels.get(cycle_type, cycle_type)
        file_path = os.path.join(folder_path, f'{file_label}.csv')

        try:
            row_count = self._measurement_row_count()
            if row_count <= 0:
                self.log(f"No complete {cycle_type} data rows to save")
                return
            with open(file_path, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(self._measurement_header())
                for i in range(row_count):
                    writer.writerow(self._measurement_row(i, formatted=False))
            self.log(f"Saved {cycle_type} data to {file_path}")
        except Exception as e:
            self.log(f"Failed to save {cycle_type} data: {str(e)}")

    def _send_runtime_config_to_arduino(self):
        """Send runtime configuration values to the 4S firmware."""
        if not self.connected:
            return

        packets = {
            "CMIN": Config.CELL_MIN_VOLTAGE,
            "CMAX": Config.CELL_MAX_VOLTAGE,
            "ENDC": Config.CHARGE_END_CURRENT_A,
            "VREFI": Config.IDLE_ADC_REFERENCE_VOLTAGE,
            "VREFA": Config.ACTIVE_ADC_REFERENCE_VOLTAGE,
            "SAMP": Config.SAMPLING_PERIOD_MS,
            "ADCS": Config.ADC_SAMPLES,
        }

        for key, value in packets.items():
            self.arduino_write(f"CFG;{key};{value}\n".encode())

        self.log("Runtime configuration sent to Arduino")

    def open_config_window(self):
        """Open the JSON-backed configuration editor."""
        if self.config_window is not None and self.config_window.winfo_exists():
            self.config_window.lift()
            return

        config_data = Config.load_config()
        self.config_window = Toplevel(self)
        self.config_window.title("Battery Tester Configuration")
        self.config_window.geometry("780x660")
        self.config_window.resizable(True, True)

        body = self._create_dialog_body(
            self.config_window,
            "Battery Tester Configuration",
            (
                "Edit user-facing settings, then Save to apply and persist them. Lists use comma-separated values."
            )
        )
        body.rowconfigure(2, weight=1)

        outer = ttk.Frame(body, style="Panel.TFrame")
        outer.grid(row=2, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(
            outer,
            highlightthickness=0,
            bg=self.dashboard_colors["panel"],
            bd=0
        )
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas, style="Panel.TFrame")

        scroll_frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        entries: Dict[str, Tuple[tk.StringVar, Any]] = {}
        flat = Config.flatten(config_data)
        resolution_choices = [self._format_resolution(width, height) for width, height in Config.SUPPORTED_RESOLUTIONS]
        current_resolution = self._format_resolution(
            int(config_data.get("application", {}).get("window_width", Config.WINDOW_WIDTH)),
            int(config_data.get("application", {}).get("window_height", Config.WINDOW_HEIGHT))
        )
        if current_resolution not in resolution_choices:
            current_resolution = self._format_resolution(Config.WINDOW_WIDTH, Config.WINDOW_HEIGHT)

        resolution_var = tk.StringVar(value=current_resolution)
        ttk.Label(scroll_frame, text="Window resolution", width=38, anchor="w", style="PanelMuted.TLabel").grid(
            row=0, column=0, padx=4, pady=4, sticky="w"
        )
        resolution_dropdown = ttk.Combobox(
            scroll_frame,
            textvariable=resolution_var,
            values=resolution_choices,
            state="readonly",
            width=36
        )
        resolution_dropdown.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        row = 1
        for key, value in flat.items():
            if key in ("application.window_width", "application.window_height"):
                continue
            ttk.Label(scroll_frame, text=self._config_display_label(key), width=38, anchor="w", style="PanelMuted.TLabel").grid(
                row=row, column=0, padx=4, pady=4, sticky="w"
            )
            display = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
            var = tk.StringVar(value=display)
            entry = ttk.Entry(scroll_frame, textvariable=var, width=36)
            entry.grid(row=row, column=1, padx=4, pady=4, sticky="ew")
            entries[key] = (var, value)
            row += 1

        scroll_frame.columnconfigure(1, weight=1)

        def collect_config() -> Optional[Dict[str, Any]]:
            updated = Config._deepcopy_defaults()
            try:
                width_text, height_text = [part.strip() for part in resolution_var.get().split("x")]
                Config.set_nested(updated, "application.window_width", int(width_text))
                Config.set_nested(updated, "application.window_height", int(height_text))
                for key, (var, old_value) in entries.items():
                    Config.set_nested(updated, key, Config.parse_value(var.get(), old_value))
                return updated
            except Exception as exc:
                self.warning_message(f"Invalid configuration value: {exc}")
                return None

        def on_save():
            updated = collect_config()
            if updated is None:
                return
            Config.save_config(updated)
            self._apply_main_window_geometry()
            self.pack_topology.set(f"Topology: {Config.CELL_COUNT}S{Config.PARALLEL_COUNT}P")
            self._refresh_battery_displays()
            self.soc_ocv_step_ah = Config.SOC_STEP_FRACTION * Config.NOMINAL_CAPACITY_AH
            self.calibration_number = Config.CALIBRATION_SAMPLES
            if self.connected:
                self._send_runtime_config_to_arduino()
            self.log("Configuration saved and applied")
            self.config_window.destroy()
            self.config_window = None

        def on_restore_defaults():
            if not messagebox.askyesno("Restore Defaults", "Restore all configuration values to defaults?"):
                return
            Config.restore_defaults()
            if self.connected:
                self._send_runtime_config_to_arduino()
            self.log("Configuration restored to defaults")
            self.config_window.destroy()
            self.config_window = None
            self.open_config_window()

        def on_close():
            self.config_window.destroy()
            self.config_window = None

        buttons = ttk.Frame(body, style="Panel.TFrame")
        buttons.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        buttons.columnconfigure(2, weight=1)
        ttk.Button(buttons, text="Save", bootstyle=SUCCESS, command=on_save).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(buttons, text="Restore Defaults", bootstyle=WARNING, command=on_restore_defaults).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(buttons, text="Close", bootstyle=SECONDARY, command=on_close).grid(
            row=0, column=2, sticky="ew", padx=(6, 0)
        )

        self.config_window.protocol("WM_DELETE_WINDOW", on_close)

    def calibrate(self):
        """Start current sensor calibration"""
        if not self.connected:
            self.warning_message("Please connect to an Arduino before calibrating.")
            return

        if self.state != 'connected':
            self.warning_message("Please stop any ongoing test before calibrating.")
            return

        self.log("Starting calibration...")
        self.calibration_count = 0
        self.calibration_sum = 0
        self.arduino_write("CSC\n".encode())
        self.state = 'calibrating'
        self.calibration_button.config(text="Calibrating", bootstyle=WARNING, state=DISABLED)

    def connect(self):
        """Handle Arduino connection/disconnection"""
        # Prevent multiple connection windows
        if self.connect_window is not None and self.connect_window.winfo_exists():
            return

        if self.connected:
            self._disconnect_arduino()
        else:
            self._show_connect_window()

    def _disconnect_arduino(self):
        """Disconnect from Arduino"""
        if self.state not in ['off', 'connected']:
            self.warning_message("Please stop the test before disconnecting from the Arduino!")
            return

        if not self.arduino_write("CLS\n".encode()):
            return

        self.connected = False
        self.arduino.close()
        self.connect_button.config(text="Connect", bootstyle=PRIMARY)
        self.log("Disconnected from the Arduino!")

    def _show_connect_window(self):
        """Show Arduino connection window"""
        import serial.tools.list_ports

        ports = serial.tools.list_ports.comports()

        if not ports:
            self.warning_message("No serial ports found. Please check your Arduino connection.")
            return

        # Get button coordinates for window positioning
        button_x = self.connect_button.winfo_rootx()
        button_y = self.connect_button.winfo_rooty()

        self.connect_window = Toplevel(self)
        self.connect_window.title("Select Serial Port")
        self.connect_window.geometry("420x300")
        self.connect_window.resizable(False, False)
        self.connect_window.geometry(f"+{button_x}+{button_y + 50}")

        body = self._create_dialog_body(
            self.connect_window,
            "Connect Arduino",
            "Select the serial interface for the battery tester controller."
        )

        self.selected_port = tk.StringVar()
        port_dropdown = ttk.Combobox(
            body,
            textvariable=self.selected_port, 
            state="readonly",
            width=42
        )
        port_dropdown['values'] = [f"{port.device} - {port.description}" for port in ports]
        port_dropdown.grid(row=2, column=0, sticky="ew", pady=(0, 12))

        self.port_description = ttk.Label(body, text="", style="PanelMuted.TLabel", wraplength=360)
        self.port_description.grid(row=3, column=0, sticky="ew", pady=(0, 16))

        port_dropdown.bind("<<ComboboxSelected>>", self.update_port_description)

        ttk.Button(
            body,
            text="Connect", 
            command=lambda: self.run_connect(self.connect_window, ports),
            bootstyle=SUCCESS
        ).grid(row=4, column=0, sticky="ew")

    def update_port_description(self, event=None):
        """Update port description when selection changes"""
        selected_text = self.selected_port.get()
        self.port_description.config(text=f"Selected: {selected_text}")

    def run_connect(self, connect_window: Toplevel, ports: list):
        """Execute Arduino connection

        Args:
            connect_window: Connection window to close
            ports: List of available ports
        """
        selected_text = self.selected_port.get()

        if not selected_text:
            self.log("No port selected")
            return

        # Extract port device name
        selected_port = selected_text.split(' - ')[0]

        self.log(f"Connecting to {selected_port}...")

        try:
            # Connect to Arduino
            self.arduino = serial.Serial(selected_port, Config.BAUD_RATE, timeout=1)

            # Reset Arduino
            self.arduino.setDTR(False)
            time.sleep(Config.ARDUINO_RESET_DELAY)
            self.arduino.flushInput()
            self.arduino.setDTR(True)
            time.sleep(Config.ARDUINO_RESET_DELAY)

            self.log("Connected successfully!")
            self.connect_button.config(text="Disconnect", bootstyle=DANGER)
            self.connected = True

            # Start packet reader thread
            self.packet_reader_thread = threading.Thread(target=self.packet_reader, daemon=True)
            self.packet_reader_thread.start()

            # Force idle state on Arduino and then apply the JSON-backed runtime configuration.
            for _ in range(2):
                self.arduino_write("IDL\n".encode())
                time.sleep(0.5)

            self._send_runtime_config_to_arduino()
            self.state = 'connected'

        except Exception as e:
            self.log(f"Failed to connect: {str(e)}")
            self.force_disconnect()

        connect_window.destroy()
        self.connect_window = None
        
    def start_test(self):
        """Start or stop a battery test"""
        if self.state not in ['off', 'connected']:
            self._stop_test()
        else:
            self._start_new_test()

    def _stop_test(self):
        """Stop the currently running test"""
        self._complete_test("Stopped by user", completed=False)

    def _start_new_test(self):
        """Start a new test"""
        if self.test_window is not None and self.test_window.winfo_exists():
            return

        if not self.connected:
            self.warning_message("Please connect to an Arduino to start a test")
            return

        # Get button coordinates
        button_x = self.start_test_button.winfo_rootx()
        button_y = self.start_test_button.winfo_rooty()

        # Create test selection window
        self.test_window = Toplevel(self)
        self.test_window.title("Select Test")
        self.test_window.geometry("460x340")
        self.test_window.resizable(False, False)
        self.test_window.geometry(f"+{button_x}+{button_y + 50}")

        body = self._create_dialog_body(
            self.test_window,
            "Select Test",
            "Choose the operation to run. The execution flow is unchanged."
        )

        self.selected_test = tk.StringVar()
        test_dropdown = ttk.Combobox(
            body,
            textvariable=self.selected_test, 
            state="readonly",
            width=36
        )
        test_dropdown['values'] = (
            "Discharge", 
            "Charge", 
            "Pulsed Charge", 
            "Pulsed Discharge",
            "Cycle",
            "SOC-OCV Characterization"
        )
        test_dropdown.grid(row=2, column=0, sticky="ew", pady=(0, 12))

        self.test_description = ttk.Label(body, text="", style="PanelMuted.TLabel", wraplength=380)
        self.test_description.grid(row=3, column=0, sticky="ew", pady=(0, 18))

        test_dropdown.bind("<<ComboboxSelected>>", self.update_test_description)

        ttk.Button(
            body,
            text="Run Test", 
            command=lambda: self.run_test(self.test_window),
            bootstyle=SUCCESS
        ).grid(row=4, column=0, sticky="ew")

    def update_test_description(self, event):
        """Update test description based on selection"""
        selected_test = self.selected_test.get()

        descriptions = {
            "Discharge": "Decreases voltage and current until minimum voltage is reached.",
            "Charge": "Increases voltage and current until maximum voltage is reached.",
            "Pulsed Charge": "Alternates between resting and charging at specified periods.",
            "Pulsed Discharge": "Alternates between resting and discharging at specified periods.",
            "Cycle": "Performs N charge/discharge cycles with pulsed steps every 10 cycles. Data saved per cycle.",
            "SOC-OCV Characterization": (
                "Measures usable capacity, fully charges, then records OCV in 5% measured-capacity "
                "discharge steps with final cutoff rest."
            )
        }

        description = descriptions.get(selected_test, "")
        self.test_description.config(text=description)

    def run_test(self, test_window: Toplevel):
        """Execute the selected test

        Args:
            test_window: Test selection window to close
        """
        selected_test = self.selected_test.get()

        if not selected_test:
            self.warning_message("Please select a test")
            return

        # Destroy test window
        test_window.destroy()

        # Get filename for data collection tests
        if selected_test != "Cycle":
            self.get_filename()
            if not self.filename:
                self.log("Test cancelled - no filename provided")
                return

        # Execute specific test
        self.active_test_name = selected_test
        if selected_test == "Discharge":
            self._run_discharge_test()
        elif selected_test == "Charge":
            self._run_charge_test()
        elif selected_test in ["Pulsed Charge", "Pulsed Discharge"]:
            self._run_pulsed_test(selected_test)
        elif selected_test == "Cycle":
            self._run_cycle_test()
        elif selected_test == "SOC-OCV Characterization":
            self._run_soc_ocv_test()

        # Update UI
        if self.state not in ['off', 'connected']:
            self.running_test.set(selected_test)
            self.start_test_button.config(text="Stop Test", bootstyle=DANGER)
            self.log(f"{selected_test} test started")

    def _run_discharge_test(self):
        """Run discharge test"""
        self._prepare_test_start()
        self.status.set("Discharging")
        self.arduino_write("STD\n".encode())
        self.start_time = time.time()
        self.state = 'measuring'
        self.measuring = True

    def _run_charge_test(self):
        """Run charge test"""
        self._prepare_test_start()
        self.status.set("Charging")
        self.arduino_write("STC\n".encode())
        self.start_time = time.time()
        self.state = 'measuring'
        self.measuring = True

    def _run_pulsed_test(self, test_type: str):
        """Run pulsed charge or discharge test

        Args:
            test_type: "Pulsed Charge" or "Pulsed Discharge"
        """
        # Reset variables
        self.pct_do_period = 0
        self.pct_resting_period = 0
        self.pct_time = 0
        self.pct_state = None

        # Get resting period
        while True:
            resting_period = simpledialog.askfloat(
                "Resting Period",
                "Enter resting period in minutes (0-60, decimal allowed):"
            )
            if resting_period is None:
                return
            if 0 <= resting_period <= 60:
                self.pct_resting_period = resting_period * 60
                break
            self.warning_message("Resting period must be between 0 and 60 minutes")

        # Get charge/discharge period
        status = "Discharging" if "Discharge" in test_type else "Charging"
        while True:
            do_period = simpledialog.askfloat(
                f"{status} Period",
                f"Enter {status.lower()} period in minutes (0-60, decimal allowed):"
            )
            if do_period is None:
                return
            if 0 <= do_period <= 60:
                self.pct_do_period = do_period * 60
                break
            self.warning_message(f"{status} period must be between 0 and 60 minutes")

        # Start test
        self._prepare_test_start()
        is_charge = (test_type == "Pulsed Charge")
        self.status.set("Resting")
        self.arduino_write(("SPC\n" if is_charge else "SPD\n").encode())
        self.start_time = time.time()
        self.pct_time = time.time()
        self.state = 'pulsed_charge' if is_charge else 'pulsed_discharge'
        self.pct_state = 'resting'
        self.measuring = True

    def _run_cycle_test(self):
        """Run cycle test – first asks Create New or Continue."""
        button_x = self.start_test_button.winfo_rootx()
        button_y = self.start_test_button.winfo_rooty()

        choice_window = Toplevel(self)
        choice_window.title("Cycle Test")
        choice_window.geometry("430x210")
        choice_window.resizable(False, False)
        choice_window.geometry(f"+{button_x}+{button_y + 50}")

        body = self._create_dialog_body(
            choice_window,
            "Cycle Test",
            "Start a fresh cycle record or continue from an existing cycle folder."
        )

        btn_frame = ttk.Frame(body, style="Panel.TFrame")
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)

        def on_create_new():
            choice_window.destroy()
            # Ask for filename, then show settings
            self.get_filename()
            if not self.filename:
                self.log("Cycle test cancelled – no filename provided")
                return
            self._show_cycle_settings_window(start_cycle=1)

        def on_continue():
            choice_window.destroy()
            self._continue_cycle_test()

        ttk.Button(btn_frame, text="Create New", bootstyle=PRIMARY, command=on_create_new).grid(
            row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(btn_frame, text="Continue", bootstyle=SUCCESS, command=on_continue).grid(
            row=0, column=1, sticky="ew", padx=6)
        ttk.Button(btn_frame, text="Cancel", bootstyle=SECONDARY,
                   command=choice_window.destroy).grid(row=0, column=2, sticky="ew", padx=(6, 0))

    def _run_soc_ocv_test(self):
        """Run capacity-calibrated SOC-OCV characterization."""
        cutoff_v = simpledialog.askfloat(
            "SOC-OCV Settings",
            "Enter lower per-cell cutoff voltage (V, 2.0-3.2):",
            initialvalue=Config.SOC_OCV_CUTOFF_V,
            minvalue=2.0,
            maxvalue=3.2
        )
        if cutoff_v is None:
            self.log("SOC-OCV test cancelled - no cutoff voltage provided")
            return

        self._prepare_test_start()
        self._reset_soc_ocv_variables()
        self.soc_ocv_cutoff_voltage = cutoff_v
        self.start_time = time.time()
        self.measuring = True
        self.state = "soc_ocv"
        self.log(
            "SOC-OCV started. Measuring usable capacity first using terminal/load voltage cutoff; "
            "relaxed OCV is recorded only during rest."
        )
        self._soc_ocv_start_capacity_discharge()

    def _detect_last_cycle(self, folder_path: str) -> int:
        """Detect the highest numbered sub-folder (cycle) in *folder_path*.

        Returns:
            The highest cycle number found, or 0 if none found.
        """
        last = 0
        try:
            for entry in os.scandir(folder_path):
                if entry.is_dir():
                    try:
                        num = int(entry.name)
                        if num > last:
                            last = num
                    except ValueError:
                        pass
        except Exception:
            pass
        return last

    def _continue_cycle_test(self):
        """Handle the Continue path: folder selection, cycle detection, settings."""
        from tkinter import filedialog
        folder_path = filedialog.askdirectory(
            title="Select existing cycle test folder",
            initialdir=Config.DATA_DIR if os.path.isdir(Config.DATA_DIR) else "."
        )
        if not folder_path:
            self.log("Cycle test continuation cancelled – no folder selected")
            return

        last_cycle = self._detect_last_cycle(folder_path)
        proposed_start = last_cycle + 1

        if last_cycle == 0:
            msg = ("No existing cycle sub-folders found in the selected folder.\n"
                   "Starting from cycle 1.")
            messagebox.showinfo("Cycle Detection", msg)
            start_cycle = 1
        else:
            answer = messagebox.askyesno(
                "Resume Cycle",
                f"Last completed cycle detected: {last_cycle}\n"
                f"Would you like to start from cycle {proposed_start}?\n\n"
                f"Click YES to start from cycle {proposed_start}, "
                f"NO to start from cycle {last_cycle} (redo last)."
            )
            start_cycle = proposed_start if answer else last_cycle

        # Derive folder name (basename) as the test filename
        self.filename = os.path.basename(folder_path)
        self.log(f"Continuing cycle test in folder: {folder_path} from cycle {start_cycle}")

        self._show_cycle_settings_window(start_cycle=start_cycle, existing_folder=folder_path)

    def _show_cycle_settings_window(self, start_cycle: int = 1, existing_folder: Optional[str] = None):
        """Show cycle configuration dialog, then launch the cycle test.

        Args:
            start_cycle: The cycle count to begin from (1-based; internal cycle_count = start_cycle - 1).
            existing_folder: If continuing, the full path to the existing data folder (used to set DATA_DIR).
        """
        button_x = self.start_test_button.winfo_rootx()
        button_y = self.start_test_button.winfo_rooty()

        cycle_window = Toplevel(self)
        cycle_window.title("Cycle Settings")
        cycle_window.geometry("460x430")
        cycle_window.resizable(False, False)
        cycle_window.geometry(f"+{button_x}+{button_y + 50}")

        body = self._create_dialog_body(
            cycle_window,
            "Cycle Settings",
            "Configure the cycle order and pulsed timing limits."
        )

        # Starting mode input
        ttk.Label(body, text="Start with", style="PanelMuted.TLabel").grid(row=2, column=0, sticky="w")
        cycle_first_var = tk.StringVar(value="Charge")
        start_dropdown = ttk.Combobox(
            body,
            textvariable=cycle_first_var,
            state="readonly",
            width=15
        )
        start_dropdown['values'] = ("Charge", "Discharge")
        start_dropdown.grid(row=3, column=0, sticky="ew", pady=(3, 10))

        # Number of cycles input
        ttk.Label(body, text="Number of cycles (0-1000, 0=infinite)", style="PanelMuted.TLabel").grid(
            row=4, column=0, sticky="w"
        )
        cycle_number_var = tk.IntVar(value=1)
        spin = tk.Spinbox(
            body,
            from_=0,
            to=1000,
            textvariable=cycle_number_var,
            width=10
        )
        spin.grid(row=5, column=0, sticky="ew", pady=(3, 10))

        # Pulsed settings
        ttk.Label(body, text="Pulsed rest (min, decimal allowed)", style="PanelMuted.TLabel").grid(
            row=6, column=0, sticky="w"
        )
        pulsed_rest_var = tk.DoubleVar(value=3.0)
        pulsed_rest_spin = tk.Spinbox(
            body,
            from_=0,
            to=60,
            increment=0.1,
            textvariable=pulsed_rest_var,
            width=10
        )
        pulsed_rest_spin.grid(row=7, column=0, sticky="ew", pady=(3, 10))

        ttk.Label(body, text="Pulsed active period (min, decimal allowed)", style="PanelMuted.TLabel").grid(
            row=8, column=0, sticky="w"
        )
        pulsed_do_var = tk.DoubleVar(value=3.0)
        pulsed_do_spin = tk.Spinbox(
            body,
            from_=0,
            to=60,
            increment=0.1,
            textvariable=pulsed_do_var,
            width=10
        )
        pulsed_do_spin.grid(row=9, column=0, sticky="ew", pady=(3, 12))

        def on_cycle_ok():
            """Process cycle configuration"""
            start = cycle_first_var.get()
            try:
                num = int(cycle_number_var.get())
                pulsed_rest = float(pulsed_rest_var.get())
                pulsed_do = float(pulsed_do_var.get())
            except (TypeError, ValueError):
                self.warning_message("Please enter valid numbers for cycle settings.")
                return

            if not (0 <= num <= 1000):
                self.warning_message("Number of cycles must be between 0 and 1000.")
                return

            if not (0 <= pulsed_rest <= 60) or not (0 <= pulsed_do <= 60):
                self.warning_message("Pulsed periods must be between 0 and 60 minutes.")
                return

            # Save settings
            self.cycle_start = start.lower()
            self.cycle_number = num
            self.cycle_count = start_cycle - 1   # so first logged cycle = start_cycle
            self.cycle_last_state = None
            self.cycle_state = None
            self.cycle_calibrating = False
            self.cycle_pulsed_resting_period = pulsed_rest * 60
            self.cycle_pulsed_do_period = pulsed_do * 60
            self.cycle_pulsed_state = None

            self.log(
                f"Cycle settings: start={start}, starting_cycle={start_cycle}, "
                f"total={num if num > 0 else 'infinite'}, "
                f"pulsed_rest={pulsed_rest}m, pulsed_do={pulsed_do}m"
            )
            cycle_window.destroy()

            # Determine and ensure the data folder exists
            if existing_folder:
                folder_path = existing_folder
                # Derive DATA_DIR dynamically so _save_cycle_data works correctly
                # Store the parent dir and folder name
                parent = os.path.dirname(existing_folder)
                # Temporarily override DATA_DIR for this session isn't ideal;
                # instead, keep self.filename as the basename and adjust DATA_DIR
                Config.DATA_DIR = parent if parent else Config.DATA_DIR
            else:
                folder_path = os.path.join(Config.DATA_DIR, self.filename)

            os.makedirs(folder_path, exist_ok=True)

            # Initialize cycle test
            self._prepare_test_start()
            self.state = 'cycle'
            self.measuring = True
            self.start_time = time.time()

            first_target = "Charge" if self.cycle_start == "charge" else "Discharge"
            first_pulsed = self._is_pulsed_cycle(start_cycle)
            self._start_cycle_step(first_target, first_pulsed)
            first_step_index = self._cycle_step_index(first_target)
            first_action = self._cycle_action_label(first_target)
            first_progress = self._format_cycle_progress(first_step_index, first_target, is_pulsed=first_pulsed)
            self._update_cycle_display(first_target, first_action, first_progress)

            self.running_test.set("Cycle")
            self.start_test_button.config(text="Stop Test", bootstyle=DANGER)
            self.log(f"Cycle test started from cycle {start_cycle}")

        btn_frame = ttk.Frame(body, style="Panel.TFrame")
        btn_frame.grid(row=10, column=0, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        ttk.Button(btn_frame, text="OK", bootstyle=SUCCESS, command=on_cycle_ok).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(btn_frame, text="Cancel", bootstyle=SECONDARY, command=cycle_window.destroy).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

    def save_data_to_csv(self):
        """Save collected data to CSV file"""
        if not self._elapsed_time_:
            self.log("No data to save")
            return False

        os.makedirs(Config.DATA_DIR, exist_ok=True)
        path = os.path.join(Config.DATA_DIR, f'{self.filename}.csv')

        try:
            row_count = self._measurement_row_count()
            if row_count <= 0:
                self.log("No complete data rows to save")
                return False
            with open(path, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(self._measurement_header())
                for i in range(row_count):
                    writer.writerow(self._measurement_row(i, formatted=True))
            self.log(f"Saved data to {path} ({row_count} samples)")
            return True

        except Exception as e:
            self.log(f"Failed to save data: {str(e)}")
            return False

    def get_filename(self):
        """Prompt user for filename and sanitize input"""
        filename = simpledialog.askstring("Input", "Enter filename for data:")

        if filename is None:
            self.filename = None
            return

        # Sanitize filename
        sanitized = filename.replace("\\", "_").replace("/", "_").strip()

        # Remove invalid characters
        invalid_chars = '<>:"|?*'
        for char in invalid_chars:
            sanitized = sanitized.replace(char, "_")

        if not sanitized:
            sanitized = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.filename = sanitized
        self.log(f"Filename set to: {self.filename}")

    def on_closing(self):
        """Handle application closing"""
        if self.connected:
            response = messagebox.askyesno(
                "Confirm Exit",
                "Arduino is still connected. Disconnect and exit?"
            )
            if response:
                self.force_disconnect()
                self.destroy()
        else:
            self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
