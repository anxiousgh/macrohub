#!/usr/bin/env python3

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog, colorchooser
import json
import os
import subprocess
import threading
import time
import signal
from datetime import datetime
import evdev
from pathlib import Path
import sys
import glob

# Set appearance mode
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class StyleManager:
    def __init__(self, theme_manager):
        self.styles_dir = os.path.expanduser("~/macro-manager/styles/")
        self.theme_manager = theme_manager
        self.ensure_styles_dir()
        self.current_style = self.load_current_style()

    def ensure_styles_dir(self):
        """Create styles directory and default style files if they don't exist"""
        os.makedirs(self.styles_dir, exist_ok=True)

        # Only create files if they don't exist - no hardcoded styles in the script
        style_files = ["modern.json", "futuristic.json", "classic.json", "oldschool.json", "gothic.json", "minimal.json"]

        for style_file in style_files:
            file_path = os.path.join(self.styles_dir, style_file)
            if not os.path.exists(file_path):
                # Create minimal empty style file
                style_name = style_file.replace('.json', '').title()
                minimal_style = {
                    "name": style_name,
                    "corner_radius_large": 8,
                    "corner_radius_medium": 6,
                    "corner_radius_small": 4,
                    "border_width": 1,
                    "spacing": 6,
                    "button_height": 25,
                    "font_family": "default",
                    "font_size_multiplier": 1.0,
                    "shadow_enabled": False,
                    "gradient_enabled": False,
                    "animation_speed": "normal"
                }

                with open(file_path, 'w') as f:
                    json.dump(minimal_style, f, indent=4)
                print(f"Created default style: {style_name}")

    def load_current_style(self):
        """Load current style from settings or default to Modern"""
        current_theme = self.theme_manager.current_theme
        style_name = current_theme.get("current_style", "Modern")
        return self.load_style(style_name)

    def load_style(self, style_name):
        """Load a specific style"""
        try:
            style_file = os.path.join(self.styles_dir, f"{style_name.lower()}.json")
            if os.path.exists(style_file):
                with open(style_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading style {style_name}: {e}")

        # Return default Modern style
        return {
            "corner_radius_large": 12,
            "corner_radius_medium": 8,
            "corner_radius_small": 6,
            "border_width": 1,
            "spacing": 6,
            "button_height": 30,
            "font_family": "default",
            "font_size_multiplier": 1.0,
            "shadow_enabled": False,
            "gradient_enabled": False,
            "animation_speed": "normal"
        }

    def get_available_styles(self):
        """Get list of available style files"""
        style_files = glob.glob(os.path.join(self.styles_dir, "*.json"))
        styles = []
        for file_path in style_files:
            style_name = os.path.splitext(os.path.basename(file_path))[0]
            style_display = style_name.replace('_', ' ').title()
            styles.append(style_display)
        return styles

    def apply_style(self, style_name):
        """Apply a style and update theme settings"""
        self.current_style = self.load_style(style_name)

        # Update theme with style settings
        self.theme_manager.current_theme.update({
            "corner_radius": self.current_style["corner_radius_medium"],
            "border_width": self.current_style["border_width"],
            "spacing": self.current_style["spacing"],
            "button_height": self.current_style["button_height"],
            "current_style": style_name
        })

        # Apply font size multiplier
        multiplier = self.current_style["font_size_multiplier"]
        base_small = 10
        base_medium = 12
        base_large = 14

        self.theme_manager.current_theme.update({
            "font_size_small": int(base_small * multiplier),
            "font_size_medium": int(base_medium * multiplier),
            "font_size_large": int(base_large * multiplier)
        })

        self.theme_manager.save_settings()
        return True

class ThemeManager:
    def __init__(self):
        self.themes_dir = os.path.expanduser("~/macro-manager/themes/")
        self.settings_file = os.path.expanduser("~/macro-manager/settings.json")
        self.ensure_themes_dir()
        self.current_theme = self.load_settings()

    def ensure_themes_dir(self):
        """Create themes directory if it doesn't exist"""
        os.makedirs(self.themes_dir, exist_ok=True)

        # Create minimal theme files if they don't exist
        theme_files = ["red_blood.json", "cyber_blue.json"]

        for theme_file in theme_files:
            file_path = os.path.join(self.themes_dir, theme_file)
            if not os.path.exists(file_path):
                # Create minimal theme file
                theme_name = theme_file.replace('.json', '').replace('_', ' ').title()
                minimal_theme = {
                    "name": theme_name,
                    "primary": "#ff3333" if "red" in theme_file else "#00ddff",
                    "primary_hover": "#dd2222" if "red" in theme_file else "#00bbdd",
                    "background": "#000000",
                    "surface": "#111111",
                    "surface_variant": "#1a1a1a",
                    "surface_dark": "#0a0a0a",
                    "text_primary": "#ffffff",
                    "text_secondary": "#aaaaaa",
                    "text_accent": "#ff3333" if "red" in theme_file else "#00ddff",
                    "success": "#44ff44",
                    "error": "#ff4444",
                    "border": "#333333",
                }

                with open(file_path, 'w') as f:
                    json.dump(minimal_theme, f, indent=4)
                print(f"Created default theme: {theme_name}")

    def load_settings(self):
        """Load user settings or create default"""
        settings = {}
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
        except Exception as e:
            print(f"Error loading settings: {e}")

        # Default settings with all required keys
        defaults = {
            "primary": "#ff3333",
            "primary_hover": "#dd2222",
            "secondary": "#ff4444",
            "background": "#000000",
            "surface": "#111111",
            "surface_variant": "#1a1a1a",
            "surface_dark": "#0a0a0a",
            "text_primary": "#ffffff",
            "text_secondary": "#aaaaaa",
            "text_accent": "#ff3333",
            "success": "#44ff44",
            "success_hover": "#33dd33",
            "warning": "#ffaa44",
            "error": "#ff4444",
            "border": "#333333",
            "corner_radius": 6,
            "border_width": 1,
            "font_size_small": 10,
            "font_size_medium": 12,
            "font_size_large": 14,
            "button_height": 22,
            "spacing": 3,
            "current_style": "Modern"
        }

        # Merge loaded settings with defaults (defaults take precedence for missing keys)
        for key, default_value in defaults.items():
            if key not in settings:
                settings[key] = default_value

        return settings

    def save_settings(self):
        """Save current settings to file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.current_theme, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    def get_available_themes(self):
        """Get list of available theme files"""
        theme_files = glob.glob(os.path.join(self.themes_dir, "*.json"))
        themes = []
        for file_path in theme_files:
            theme_name = os.path.splitext(os.path.basename(file_path))[0]
            theme_display = theme_name.replace('_', ' ').title()
            themes.append((theme_display, file_path))
        return themes

    def load_theme(self, theme_file):
        """Load a theme from file"""
        try:
            with open(theme_file, 'r') as f:
                self.current_theme = json.load(f)
                self.save_settings()
                return True
        except Exception as e:
            print(f"Failed to load theme: {e}")
            return False

class DevicePicker:
    def __init__(self, parent, theme):
        self.selected_device = None
        self.theme = theme

        # Create toplevel window - bigger size
        self.window = ctk.CTkToplevel()
        self.window.title("Select Input Device")
        self.window.geometry("650x450")
        self.window.configure(fg_color=self.theme["background"])

        # Get parent window position for proper centering
        parent.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()

        # Center relative to parent window (not screen)
        x = parent_x + (parent_width - 650) // 2
        y = parent_y + (parent_height - 450) // 2

        # Ensure window stays on screen
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = max(0, min(x, screen_width - 650))
        y = max(0, min(y, screen_height - 450))

        self.window.geometry(f"650x450+{x}+{y}")

        # Prevent resizing
        self.window.resizable(False, False)

        # Make window modal and always on top
        self.window.transient(parent)
        self.window.lift()
        self.window.attributes('-topmost', True)
        self.window.focus_force()

        # Setup UI first
        self.setup_ui()
        self.load_devices()

        # Now grab after everything is setup and visible
        self.window.after(200, self.grab_window)

    def grab_window(self):
        """Safely grab the window after it's fully visible"""
        try:
            self.window.grab_set()
        except tk.TclError:
            # If grab fails, try again later
            self.window.after(100, self.grab_window)

    def setup_ui(self):
        # Title
        title_label = ctk.CTkLabel(self.window, text="Select Input Device",
                                   font=ctk.CTkFont(size=self.theme["font_size_large"]+6, weight="bold"),
                                   text_color=self.theme["text_accent"])
        title_label.pack(pady=(20, 15))

        # Info label
        info_label = ctk.CTkLabel(self.window, text="Choose a keyboard or mouse device for input capture:",
                                  font=ctk.CTkFont(size=self.theme["font_size_medium"]+2),
                                  text_color=self.theme["text_secondary"])
        info_label.pack(pady=(0, 15))

        # Scrollable frame for devices
        self.scroll_frame = ctk.CTkScrollableFrame(self.window, corner_radius=self.theme["corner_radius"],
                                                   fg_color=self.theme["surface"], border_width=2,
                                                   border_color=self.theme["primary"])
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Buttons frame
        btn_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))

        cancel_btn = ctk.CTkButton(btn_frame, text="Cancel",
                                   command=self.cancel, width=100, height=35,
                                   fg_color=self.theme["border"], hover_color="#444444",
                                   font=ctk.CTkFont(size=self.theme["font_size_medium"]+1),
                                   corner_radius=self.theme["corner_radius"])
        cancel_btn.pack(side="right", padx=(10, 0))

        self.select_btn = ctk.CTkButton(btn_frame, text="Select Device",
                                        command=self.select, width=120, height=35,
                                        fg_color=self.theme["primary"], hover_color=self.theme["primary_hover"],
                                        font=ctk.CTkFont(size=self.theme["font_size_medium"]+1),
                                        corner_radius=self.theme["corner_radius"],
                                        state="disabled")
        self.select_btn.pack(side="right")

    def is_input_device(self, device):
        """Check if device is a keyboard or mouse"""
        try:
            capabilities = device.capabilities()

            # Check for mouse buttons
            if 1 in capabilities:  # EV_KEY
                keys = capabilities[1]
                # Common mouse buttons
                mouse_buttons = [272, 273, 274, 275, 276]  # BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_SIDE, BTN_EXTRA
                if any(btn in keys for btn in mouse_buttons):
                    return True, "MOUSE"

            # Check for keyboard keys
            if 1 in capabilities:  # EV_KEY
                keys = capabilities[1]
                # Common keyboard keys (letters, numbers, space, etc.)
                keyboard_keys = list(range(16, 26)) + list(range(30, 39)) + [57]  # Q-P, A-L, SPACE
                if any(key in keys for key in keyboard_keys):
                    return True, "KEYBOARD"

            return False, "OTHER"
        except:
            return False, "OTHER"

    def load_devices(self):
        try:
            all_devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

            # Filter to only input devices (keyboards and mice)
            input_devices = []
            for device in all_devices:
                is_input, device_type = self.is_input_device(device)
                if is_input:
                    input_devices.append((device, device_type))

            if not input_devices:
                no_devices_label = ctk.CTkLabel(self.scroll_frame,
                                                text="No keyboard or mouse devices found\nMake sure you have access to /dev/input/",
                                                font=ctk.CTkFont(size=self.theme["font_size_medium"]+2),
                                                text_color=self.theme["error"])
                no_devices_label.pack(pady=80)
                return

            self.device_vars = {}
            for i, (device, device_type) in enumerate(input_devices):
                self.create_device_entry(device, device_type)

        except Exception as e:
            error_label = ctk.CTkLabel(self.scroll_frame,
                                       text=f"Error loading devices:\n{str(e)}",
                                       font=ctk.CTkFont(size=self.theme["font_size_medium"]),
                                       text_color=self.theme["error"])
            error_label.pack(pady=60)

    def create_device_entry(self, device, device_type):
        """Create a clickable device entry"""
        device_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=self.theme["corner_radius"],
                                    fg_color=self.theme["surface_variant"], height=70)
        device_frame.pack(fill="x", padx=15, pady=6)
        device_frame.pack_propagate(False)

        # Store device path for this frame
        device_frame.device_path = device.path

        # Radio button (still there but we'll make whole frame clickable)
        var = tk.StringVar()
        self.device_vars[device.path] = var

        radio = ctk.CTkRadioButton(device_frame, text="", variable=var,
                                   value=device.path,
                                   command=lambda p=device.path: self.device_selected(p),
                                   fg_color=self.theme["primary"])
        radio.pack(side="left", padx=(15, 12), pady=20)

        # Device type badge
        type_color = self.theme["success"] if device_type == "KEYBOARD" else self.theme["primary"]
        type_badge = ctk.CTkLabel(device_frame, text=device_type,
                                  font=ctk.CTkFont(size=self.theme["font_size_small"], weight="bold"),
                                  text_color="#000000", fg_color=type_color,
                                  corner_radius=4, width=80)
        type_badge.pack(side="left", padx=(0, 10), pady=25)

        # Device info
        info_frame = ctk.CTkFrame(device_frame, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, pady=12)

        # Device name (larger)
        name_label = ctk.CTkLabel(info_frame, text=f"{device.name}",
                                  font=ctk.CTkFont(size=self.theme["font_size_medium"]+1, weight="bold"),
                                  anchor="w", text_color=self.theme["text_primary"])
        name_label.pack(anchor="w", fill="x")

        # Device path (larger and more visible)
        path_label = ctk.CTkLabel(info_frame, text=f"Path: {device.path}",
                                  font=ctk.CTkFont(size=self.theme["font_size_medium"]),
                                  anchor="w", text_color=self.theme["text_accent"])
        path_label.pack(anchor="w", fill="x")

        # Make the entire frame clickable
        def on_frame_click(event, path=device.path):
            self.device_selected(path)
            # Trigger the radio button
            var.set(path)

        # Bind click events to frame and all its children
        device_frame.bind("<Button-1>", on_frame_click)
        type_badge.bind("<Button-1>", on_frame_click)
        info_frame.bind("<Button-1>", on_frame_click)
        name_label.bind("<Button-1>", on_frame_click)
        path_label.bind("<Button-1>", on_frame_click)

        # Change cursor to hand when hovering
        device_frame.configure(cursor="hand2")
        type_badge.configure(cursor="hand2")
        name_label.configure(cursor="hand2")
        path_label.configure(cursor="hand2")

    def device_selected(self, device_path):
        # Uncheck all other radio buttons
        for path, var in self.device_vars.items():
            if path != device_path:
                var.set("")
            else:
                var.set(device_path)

        self.selected_device = device_path
        self.select_btn.configure(state="normal")

    def select(self):
        self.window.destroy()

    def cancel(self):
        self.selected_device = None
        self.window.destroy()

class AdvancedSettingsTab:
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        self.theme = main_app.theme_manager.current_theme
        self.style_manager = main_app.style_manager

        # Create temp settings with proper fallbacks
        self.temp_settings = self.theme.copy()
        self.ensure_all_keys()

        self.create_settings_ui()

    def ensure_all_keys(self):
        """Ensure all required keys exist in temp_settings with fallback values"""
        defaults = {
            "primary": "#ff3333",
            "primary_hover": "#dd2222",
            "secondary": "#ff4444",
            "background": "#000000",
            "surface": "#111111",
            "surface_variant": "#1a1a1a",
            "surface_dark": "#0a0a0a",
            "text_primary": "#ffffff",
            "text_secondary": "#aaaaaa",
            "text_accent": "#ff3333",
            "success": "#44ff44",
            "success_hover": "#33dd33",
            "warning": "#ffaa44",
            "error": "#ff4444",
            "border": "#333333",
            "corner_radius": 6,
            "border_width": 1,
            "font_size_small": 10,
            "font_size_medium": 12,
            "font_size_large": 14,
            "button_height": 22,
            "spacing": 3,
            "current_style": "Modern"
        }

        # Add any missing keys with defaults
        for key, default_value in defaults.items():
            if key not in self.temp_settings:
                self.temp_settings[key] = default_value

    def create_settings_ui(self):
        # Settings content frame with proper scrolling
        settings_frame = ctk.CTkScrollableFrame(self.parent, corner_radius=self.theme["corner_radius"])
        settings_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Header
        header_label = ctk.CTkLabel(settings_frame, text="ADVANCED SETTINGS",
                                    font=ctk.CTkFont(size=self.theme["font_size_large"]+2, weight="bold"),
                                    text_color=self.theme["text_accent"])
        header_label.pack(pady=(10, 15))

        # Style Selection (New section)
        self.create_style_section(settings_frame)

        # Color Settings
        self.create_color_section(settings_frame)

        # Appearance Settings
        self.create_appearance_section(settings_frame)

        # Preset Themes
        self.create_preset_section(settings_frame)

        # Action buttons
        self.create_action_buttons(settings_frame)

    def create_style_section(self, parent):
        style_frame = ctk.CTkFrame(parent, corner_radius=self.theme["corner_radius"])
        style_frame.pack(fill="x", padx=5, pady=(0, 5))

        style_label = ctk.CTkLabel(style_frame, text="VISUAL STYLE",
                                   font=ctk.CTkFont(size=self.theme["font_size_medium"]+1, weight="bold"),
                                   text_color=self.theme["text_primary"])
        style_label.pack(pady=(5, 3))

        # Style description
        style_desc = ctk.CTkLabel(style_frame, text="Choose the overall visual aesthetic:",
                                  font=ctk.CTkFont(size=self.theme["font_size_small"]+1),
                                  text_color=self.theme["text_secondary"])
        style_desc.pack(pady=(0, 5))

        # Style dropdown
        available_styles = self.style_manager.get_available_styles()
        current_style = self.temp_settings.get("current_style", "Modern")

        self.style_dropdown = ctk.CTkOptionMenu(style_frame,
                                                values=available_styles,
                                                width=250, height=25,
                                                fg_color=self.theme["primary"],
                                                button_color=self.theme["primary_hover"],
                                                button_hover_color=self.theme["primary"],
                                                dropdown_fg_color=self.theme["surface_variant"],
                                                command=self.style_changed,
                                                corner_radius=self.theme["corner_radius"])
        if current_style in available_styles:
            self.style_dropdown.set(current_style)
        self.style_dropdown.pack(pady=(0, 5))

        # Style preview info
        self.create_style_preview(style_frame)

    def create_style_preview(self, parent):
        preview_frame = ctk.CTkFrame(parent, corner_radius=self.theme["corner_radius"]-2,
                                     fg_color=self.theme["surface_variant"])
        preview_frame.pack(fill="x", padx=5, pady=(0, 5))

        preview_label = ctk.CTkLabel(preview_frame, text="Style Info:",
                                     font=ctk.CTkFont(size=self.theme["font_size_small"], weight="bold"),
                                     text_color=self.theme["text_primary"])
        preview_label.pack(pady=(3, 1), anchor="w", padx=5)

        current_style_name = self.temp_settings.get("current_style", "Modern")
        style_info = self.get_style_description(current_style_name)

        self.style_info_label = ctk.CTkLabel(preview_frame, text=style_info,
                                             font=ctk.CTkFont(size=self.theme["font_size_small"]),
                                             text_color=self.theme["text_secondary"],
                                             justify="left")
        self.style_info_label.pack(pady=(0, 3), anchor="w", padx=5)

    def get_style_description(self, style_name):
        descriptions = {
            "Modern": "Clean lines, rounded corners, subtle borders - contemporary design",
            "Futuristic": "Sharp angles, high contrast, neon aesthetics - sci-fi inspired",
            "Classic": "Traditional styling, conservative colors, timeless appeal",
            "Oldschool": "Retro computing, chunky borders, larger fonts - vintage feel",
            "Gothic": "Dark themes, ornate styling, dramatic visual elements",
            "Minimal": "Ultra-clean, minimal borders, compact spacing - less is more"
        }
        return descriptions.get(style_name, "Custom style configuration")

    def style_changed(self, style_name):
        """Update temp settings when style changes"""
        try:
            style_data = self.style_manager.load_style(style_name)

            # Update temp settings with style values
            self.temp_settings.update({
                "corner_radius": style_data["corner_radius_medium"],
                "border_width": style_data["border_width"],
                "spacing": style_data["spacing"],
                "button_height": style_data["button_height"],
                "current_style": style_name
            })

            # Apply font size multiplier
            multiplier = style_data["font_size_multiplier"]
            self.temp_settings.update({
                "font_size_small": int(10 * multiplier),
                "font_size_medium": int(12 * multiplier),
                "font_size_large": int(14 * multiplier)
            })

            # Update style info display
            style_info = self.get_style_description(style_name)
            self.style_info_label.configure(text=style_info)

            self.main_app.log(f"Style preview: {style_name}")

        except Exception as e:
            print(f"Error changing style: {e}")

    def create_color_section(self, parent):
        color_frame = ctk.CTkFrame(parent, corner_radius=self.theme["corner_radius"])
        color_frame.pack(fill="x", padx=5, pady=(0, 5))

        color_label = ctk.CTkLabel(color_frame, text="COLOR CUSTOMIZATION",
                                   font=ctk.CTkFont(size=self.theme["font_size_medium"]+1, weight="bold"),
                                   text_color=self.theme["text_primary"])
        color_label.pack(pady=(5, 3))

        color_settings = [
            ("Primary Color", "primary"),
            ("Primary Hover", "primary_hover"),
            ("Background", "background"),
            ("Surface", "surface"),
            ("Surface Dark", "surface_dark"),
            ("Text Primary", "text_primary"),
            ("Text Secondary", "text_secondary"),
            ("Text Accent", "text_accent"),
            ("Success", "success"),
            ("Error", "error"),
            ("Border", "border")
        ]

        self.color_buttons = {}
        for display_name, key in color_settings:
            self.create_color_picker(color_frame, display_name, key)

    def create_color_picker(self, parent, display_name, key):
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", padx=5, pady=1)

        label = ctk.CTkLabel(row_frame, text=display_name + ":",
                             font=ctk.CTkFont(size=self.theme["font_size_small"]+1),
                             text_color=self.theme["text_primary"],
                             width=120, anchor="w")
        label.pack(side="left", padx=(5, 8))

        # Color preview
        color_preview = ctk.CTkFrame(row_frame, width=25, height=18,
                                     fg_color=self.temp_settings[key],
                                     corner_radius=3)
        color_preview.pack(side="left", padx=(0, 5), pady=2)

        # Color picker button
        color_btn = ctk.CTkButton(row_frame, text="Pick",
                                  command=lambda k=key, p=color_preview: self.pick_color(k, p),
                                  width=45, height=18,
                                  fg_color=self.theme["primary"],
                                  hover_color=self.theme["primary_hover"],
                                  font=ctk.CTkFont(size=self.theme["font_size_small"]),
                                  corner_radius=self.theme["corner_radius"])
        color_btn.pack(side="left", padx=(0, 5))

        # Color entry
        color_entry = ctk.CTkEntry(row_frame, width=70, height=18,
                                   fg_color=self.theme["surface_dark"],
                                   border_color=self.theme["border"],
                                   corner_radius=self.theme["corner_radius"],
                                   font=ctk.CTkFont(size=self.theme["font_size_small"]))
        color_entry.insert(0, self.temp_settings[key])
        color_entry.pack(side="right", padx=(5, 5), pady=2)

        # Bind entry changes
        def on_color_change(event, k=key, p=color_preview, e=color_entry):
            try:
                color = e.get()
                if color.startswith('#') and len(color) == 7:
                    self.temp_settings[k] = color
                    p.configure(fg_color=color)
            except:
                pass

        color_entry.bind('<KeyRelease>', on_color_change)
        self.color_buttons[key] = (color_preview, color_entry)

    def pick_color(self, key, preview):
        color = colorchooser.askcolor(color=self.temp_settings[key], title=f"Pick {key} color")[1]
        if color:
            self.temp_settings[key] = color
            preview.configure(fg_color=color)
            self.color_buttons[key][1].delete(0, tk.END)
            self.color_buttons[key][1].insert(0, color)

    def create_appearance_section(self, parent):
        appearance_frame = ctk.CTkFrame(parent, corner_radius=self.theme["corner_radius"])
        appearance_frame.pack(fill="x", padx=5, pady=(0, 5))

        appearance_label = ctk.CTkLabel(appearance_frame, text="APPEARANCE SETTINGS",
                                        font=ctk.CTkFont(size=self.theme["font_size_medium"]+1, weight="bold"),
                                        text_color=self.theme["text_primary"])
        appearance_label.pack(pady=(5, 3))

        # Corner Radius
        self.create_slider_setting(appearance_frame, "Corner Radius", "corner_radius", 0, 20, self.temp_settings.get("corner_radius", 6))

        # Border Width
        self.create_slider_setting(appearance_frame, "Border Width", "border_width", 0, 5, self.temp_settings.get("border_width", 1))

        # Button Height
        self.create_slider_setting(appearance_frame, "Button Height", "button_height", 15, 40, self.temp_settings.get("button_height", 22))

        # Spacing
        self.create_slider_setting(appearance_frame, "Element Spacing", "spacing", 1, 15, self.temp_settings.get("spacing", 3))

        # Font sizes
        self.create_slider_setting(appearance_frame, "Small Font Size", "font_size_small", 8, 16, self.temp_settings.get("font_size_small", 10))
        self.create_slider_setting(appearance_frame, "Medium Font Size", "font_size_medium", 10, 20, self.temp_settings.get("font_size_medium", 12))
        self.create_slider_setting(appearance_frame, "Large Font Size", "font_size_large", 12, 24, self.temp_settings.get("font_size_large", 14))

    def create_slider_setting(self, parent, display_name, key, min_val, max_val, current_val):
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", padx=5, pady=1)

        label = ctk.CTkLabel(row_frame, text=f"{display_name}:",
                             font=ctk.CTkFont(size=self.theme["font_size_small"]+1),
                             text_color=self.theme["text_primary"],
                             width=120, anchor="w")
        label.pack(side="left", padx=(5, 8))

        value_label = ctk.CTkLabel(row_frame, text=str(current_val),
                                   font=ctk.CTkFont(size=self.theme["font_size_small"]),
                                   text_color=self.theme["text_secondary"],
                                   width=25)
        value_label.pack(side="right", padx=(5, 5))

        def slider_callback(value, k=key, vl=value_label):
            int_val = int(value)
            self.temp_settings[k] = int_val
            vl.configure(text=str(int_val))

        slider = ctk.CTkSlider(row_frame, from_=min_val, to=max_val,
                               number_of_steps=max_val - min_val,
                               command=slider_callback,
                               fg_color=self.theme["surface_dark"],
                               progress_color=self.theme["primary"],
                               button_color=self.theme["primary"],
                               button_hover_color=self.theme["primary_hover"],
                               height=16)
        slider.set(current_val)
        slider.pack(side="right", fill="x", expand=True, padx=(0, 8), pady=2)

    def create_preset_section(self, parent):
        preset_frame = ctk.CTkFrame(parent, corner_radius=self.theme["corner_radius"])
        preset_frame.pack(fill="x", padx=5, pady=(0, 5))

        preset_label = ctk.CTkLabel(preset_frame, text="PRESET THEMES",
                                    font=ctk.CTkFont(size=self.theme["font_size_medium"]+1, weight="bold"),
                                    text_color=self.theme["text_primary"])
        preset_label.pack(pady=(5, 3))

        # Theme dropdown
        themes = self.main_app.theme_manager.get_available_themes()
        theme_names = [theme[0] for theme in themes]

        if theme_names:
            self.theme_dropdown = ctk.CTkOptionMenu(preset_frame,
                                                    values=theme_names,
                                                    width=200, height=25,
                                                    fg_color=self.theme["primary"],
                                                    button_color=self.theme["primary_hover"],
                                                    button_hover_color=self.theme["primary"],
                                                    dropdown_fg_color=self.theme["surface"],
                                                    command=self.load_preset_theme,
                                                    corner_radius=self.theme["corner_radius"])
            self.theme_dropdown.pack(pady=(0, 5))

    def load_preset_theme(self, theme_name):
        themes = self.main_app.theme_manager.get_available_themes()
        for theme_display, theme_file in themes:
            if theme_display == theme_name:
                try:
                    with open(theme_file, 'r') as f:
                        preset_theme = json.load(f)
                    self.temp_settings.update(preset_theme)
                    self.refresh_ui()
                    break
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to load preset: {e}")

    def create_action_buttons(self, parent):
        button_frame = ctk.CTkFrame(parent, fg_color="transparent")
        button_frame.pack(fill="x", padx=5, pady=10)

        reset_btn = ctk.CTkButton(button_frame, text="Reset to Defaults",
                                  command=self.reset_to_defaults,
                                  width=120, height=30,
                                  fg_color=self.theme["border"],
                                  hover_color="#555555",
                                  font=ctk.CTkFont(size=self.theme["font_size_medium"]),
                                  corner_radius=self.theme["corner_radius"])
        reset_btn.pack(side="left")

        apply_btn = ctk.CTkButton(button_frame, text="Apply Settings",
                                  command=self.apply_settings,
                                  width=120, height=30,
                                  fg_color=self.theme["primary"],
                                  hover_color=self.theme["primary_hover"],
                                  font=ctk.CTkFont(size=self.theme["font_size_medium"]),
                                  corner_radius=self.theme["corner_radius"])
        apply_btn.pack(side="right")

    def refresh_ui(self):
        """Refresh UI with new temp settings"""
        for key, (preview, entry) in self.color_buttons.items():
            color = self.temp_settings[key]
            preview.configure(fg_color=color)
            entry.delete(0, tk.END)
            entry.insert(0, color)

    def reset_to_defaults(self):
        # Reset to Modern style with Red Blood theme defaults
        defaults = {
            "primary": "#ff3333",
            "primary_hover": "#dd2222",
            "secondary": "#ff4444",
            "background": "#000000",
            "surface": "#111111",
            "surface_variant": "#1a1a1a",
            "surface_dark": "#0a0a0a",
            "text_primary": "#ffffff",
            "text_secondary": "#aaaaaa",
            "text_accent": "#ff3333",
            "success": "#44ff44",
            "success_hover": "#33dd33",
            "warning": "#ffaa44",
            "error": "#ff4444",
            "border": "#333333",
            "corner_radius": 6,
            "border_width": 1,
            "font_size_small": 10,
            "font_size_medium": 12,
            "font_size_large": 14,
            "button_height": 22,
            "spacing": 3,
            "current_style": "Modern"
        }
        self.temp_settings.update(defaults)
        self.style_dropdown.set("Modern")
        self.refresh_ui()

        # Update style info
        style_info = self.get_style_description("Modern")
        self.style_info_label.configure(text=style_info)

    def apply_settings(self):
        # Apply style first if changed
        selected_style = self.style_dropdown.get()
        current_style = self.main_app.theme_manager.current_theme.get("current_style", "Modern")

        if selected_style != current_style:
            self.style_manager.apply_style(selected_style)

        # Then apply other customizations
        self.main_app.theme_manager.current_theme.update(self.temp_settings)
        if self.main_app.theme_manager.save_settings():
            messagebox.showinfo("Success", "Settings applied!\nRestart the application to see all changes.")
            self.main_app.log(f"Settings updated - Style: {selected_style}")
        else:
            messagebox.showerror("Error", "Failed to save settings")

class ConfigTab:
    def __init__(self, parent, macro_name, main_app):
        self.parent = parent
        self.macro_name = macro_name
        self.main_app = main_app
        self.theme = main_app.theme_manager.current_theme

        # Load macro-specific config
        self.config_file = os.path.expanduser(f"~/macro-manager/configs/{macro_name}.json")
        self.macro_data = self.load_macro_config()
        self.config_entries = {}
        self.create_config_ui()

    def load_macro_config(self):
        """Load config for this specific macro"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading config for {self.macro_name}: {e}")

        # Return default config if not found
        script_path = ""
        if self.macro_name in self.main_app.macros:
            script_path = self.main_app.macros[self.macro_name].get('script_path', '')

        # Force the macro detection to run and print the result
        macro_type = self.main_app.detect_macro_type(script_path)
        print(f"Detected macro type for {self.macro_name}: {macro_type}")

        if macro_type == 'autoclicker':
            return {
                'name': self.macro_name,
                'script_path': script_path,
                'description': f"AutoClicker: {os.path.basename(script_path)}",
                'cps': 25.0,
                'click_duration': 0.001,
                'trigger_button': 'extra',
                'target_button': 'left'
            }
        elif macro_type == 'strafer':
            return {
                'name': self.macro_name,
                'script_path': script_path,
                'description': f"Strafer: {os.path.basename(script_path)}",
                'SPEED_PX_PER_SEC_DEFAULT': 2000.0,
                'MIN_SPEED_PX_PER_SEC': 100.0,
                'MAX_SPEED_PX_PER_SEC': 20000.0,
                'SPEEDUP_MULTIPLIER': 2.0,
                'SLOWDOWN_MULTIPLIER': 0.5,
                'SCROLL_SPEED_STEP': 100.0,
                'LEFT_PHYS_KEY_NAME': 'KEY_A',
                'RIGHT_PHYS_KEY_NAME': 'KEY_D',
                'PAUSE_KEY_NAME': 'KEY_ESC',
                'SPEEDUP_KEY_NAME': 'KEY_LEFTCTRL',
                'SLOWDOWN_KEY_NAME': 'KEY_LEFTSHIFT',
                'STOP_MOUSE_BUTTON': 'BTN_EXTRA',
                'WHEEL_ADJUST_TOGGLE_NAME': 'KEY_F9',
                'SPACE_TIMED_KEY_NAME': 'KEY_SPACE',
                'INVERT_X': 'False',
                'ACCEL_TIME_S': 0.001,
                'DECEL_TIME_S': 0.001,
                'EASING': 'exp_in_out',
                'MIN_FRAME_TIME': 0.0015,
                'MAX_STEP_PX': 12,
                'DEADZONE_VEL_PX_S': 0.5,
                'HUMANIZE_NOISE': 'False',
                'NOISE_PER_STEP_PX': 0.35,
                'START_MOVE_DELAY_S': 0.01,
                'SPACE_MIRROR_TO_GAME': 'True',
                'SPACE_TICK_SECONDS': 1.0,
                'SPACE_ALLOW_INCREASE': 'False',
                'SPACE_RESTART_ON_PRESS': 'True',
                'SPACE_STOP_ON_RELEASE': 'True',
                'VKB_NAME': 'strafer-kb',
                'VMOUSE_NAME': 'strafer-mouse',
                'LOG_LEVEL': 'minimal',
                'LOG_TICKS': 'False',
                'LOG_STAGES': 'True',
                'LOG_RESTARTS': 'True',
                'LOG_SPEEDLINE_INTERVAL_S': 0.25
            }
        else:
            return {
                'name': self.macro_name,
                'script_path': script_path,
                'description': f"Macro: {os.path.basename(script_path)}",
            }

    def save_macro_config(self):
        """Save config for this specific macro"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.macro_data, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving config for {self.macro_name}: {e}")
            return False

    def create_config_ui(self):
        # Config content frame
        config_frame = ctk.CTkFrame(self.parent, corner_radius=self.theme["corner_radius"])
        config_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Header
        header_label = ctk.CTkLabel(config_frame, text=f"Configure: {self.macro_name}",
                                    font=ctk.CTkFont(size=self.theme["font_size_large"], weight="bold"),
                                    text_color=self.theme["text_accent"])
        header_label.pack(pady=(10, 15))

        # Configuration section with proper scrolling
        self.scroll_frame = ctk.CTkScrollableFrame(config_frame, corner_radius=self.theme["corner_radius"])
        self.scroll_frame.pack(fill="both", expand=True, padx=5, pady=(0, 10))

        # Config entries
        self.create_config_entries()

        # Save button
        save_btn = ctk.CTkButton(config_frame, text="Save Configuration",
                                 command=self.save_config,
                                 fg_color=self.theme["primary"], hover_color=self.theme["primary_hover"],
                                 width=150, height=self.theme["button_height"]+5,
                                 font=ctk.CTkFont(size=self.theme["font_size_medium"]),
                                 corner_radius=self.theme["corner_radius"])
        save_btn.pack(pady=(0, 10))

    def create_section_header(self, title):
        """Create a section header in the config UI"""
        header_frame = ctk.CTkFrame(self.scroll_frame, fg_color=self.theme["surface_variant"])
        header_frame.pack(fill="x", padx=5, pady=(10, 3))

        label = ctk.CTkLabel(header_frame, text=title,
                            font=ctk.CTkFont(size=self.theme["font_size_medium"], weight="bold"),
                            text_color=self.theme["text_accent"],
                            anchor="w")
        label.pack(fill="x", padx=8, pady=5)

    def create_config_entries(self):
        script_path = self.macro_data.get('script_path', '')

        # Force re-detect the macro type
        macro_type = self.main_app.detect_macro_type(script_path)
        print(f"Config Tab - detected macro type: {macro_type} for script: {os.path.basename(script_path)}")

        if macro_type == 'autoclicker':
            self.create_autoclicker_config()
        elif macro_type == 'strafer':
            self.create_strafer_config()
        else:
            self.create_generic_config()

    def create_autoclicker_config(self):
        config_fields = [
            ('cps', 'Clicks Per Second', 'number'),
            ('click_duration', 'Click Duration (seconds)', 'number'),
            ('trigger_button', 'Trigger Button', 'dropdown', ['left', 'right', 'middle', 'side', 'extra', 'forward', 'back']),
            ('target_button', 'Target Button', 'dropdown', ['left', 'right', 'middle', 'side', 'extra'])
        ]

        self.create_config_fields(config_fields)

    def create_strafer_config(self):
        # Main movement settings
        movement_fields = [
            ('SPEED_PX_PER_SEC_DEFAULT', 'Base Speed (px/sec)', 'number'),
            ('MIN_SPEED_PX_PER_SEC', 'Min Speed (px/sec)', 'number'),
            ('MAX_SPEED_PX_PER_SEC', 'Max Speed (px/sec)', 'number'),
            ('SPEEDUP_MULTIPLIER', 'Speed Up Multiplier', 'number'),
            ('SLOWDOWN_MULTIPLIER', 'Slow Down Multiplier', 'number'),
            ('INVERT_X', 'Invert X Direction', 'dropdown', ['False', 'True']),
            ('SCROLL_SPEED_STEP', 'Scroll Speed Step', 'number')
        ]

        # Key bindings
        key_fields = [
            ('LEFT_PHYS_KEY_NAME', 'Left Key', 'text'),
            ('RIGHT_PHYS_KEY_NAME', 'Right Key', 'text'),
            ('PAUSE_KEY_NAME', 'Pause Key', 'text'),
            ('SPEEDUP_KEY_NAME', 'Speed Up Key', 'text'),
            ('SLOWDOWN_KEY_NAME', 'Slow Down Key', 'text'),
            ('STOP_MOUSE_BUTTON', 'Stop Mouse Button', 'text'),
            ('WHEEL_ADJUST_TOGGLE_NAME', 'Wheel Toggle Key', 'text'),
            ('SPACE_TIMED_KEY_NAME', 'Space Timing Key', 'text')
        ]

        # Movement behavior
        behavior_fields = [
            ('ACCEL_TIME_S', 'Acceleration Time (s)', 'number'),
            ('DECEL_TIME_S', 'Deceleration Time (s)', 'number'),
            ('EASING', 'Movement Easing', 'dropdown', ['exp_in_out', 'cubic_in_out', 'linear']),
            ('MIN_FRAME_TIME', 'Min Frame Time (s)', 'number'),
            ('MAX_STEP_PX', 'Max Step Size (px)', 'number'),
            ('DEADZONE_VEL_PX_S', 'Deadzone Velocity', 'number'),
            ('START_MOVE_DELAY_S', 'Start Move Delay (s)', 'number')
        ]

        # Space timing settings
        space_fields = [
            ('SPACE_MIRROR_TO_GAME', 'Mirror Space to Game', 'dropdown', ['True', 'False']),
            ('SPACE_TICK_SECONDS', 'Space Tick Interval (s)', 'number'),
            ('SPACE_ALLOW_INCREASE', 'Allow Speed Increase', 'dropdown', ['False', 'True']),
            ('SPACE_RESTART_ON_PRESS', 'Restart on Press', 'dropdown', ['True', 'False']),
            ('SPACE_STOP_ON_RELEASE', 'Stop on Release', 'dropdown', ['True', 'False'])
        ]

        # Humanization
        humanization_fields = [
            ('HUMANIZE_NOISE', 'Add Human-like Noise', 'dropdown', ['False', 'True']),
            ('NOISE_PER_STEP_PX', 'Noise Amount (px)', 'number')
        ]

        # Names for virtual devices
        device_fields = [
            ('VKB_NAME', 'Virtual Keyboard Name', 'text'),
            ('VMOUSE_NAME', 'Virtual Mouse Name', 'text')
        ]

        # Logging options
        log_fields = [
            ('LOG_LEVEL', 'Log Level', 'dropdown', ['minimal', 'verbose', 'none']),
            ('LOG_TICKS', 'Log Ticks', 'dropdown', ['False', 'True']),
            ('LOG_STAGES', 'Log Stages', 'dropdown', ['True', 'False']),
            ('LOG_RESTARTS', 'Log Restarts', 'dropdown', ['True', 'False']),
            ('LOG_SPEEDLINE_INTERVAL_S', 'Speedline Interval (s)', 'number')
        ]

        # Speed schedule section
        self.create_section_header("SPEED SCHEDULE")

        # Create frame for the speed schedule editor
        schedule_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=self.theme["corner_radius"])
        schedule_frame.pack(fill="x", padx=5, pady=self.theme["spacing"])

        # Add label
        schedule_label = ctk.CTkLabel(schedule_frame, text="Speed Schedule (time, speed pairs):",
                                font=ctk.CTkFont(size=self.theme["font_size_medium"]),
                                text_color=self.theme["text_primary"],
                                anchor="w")
        schedule_label.pack(anchor="w", padx=8, pady=(6, 2))

        # Instructions label
        instructions_label = ctk.CTkLabel(schedule_frame, text="One pair per line: time, speed",
                                    font=ctk.CTkFont(size=self.theme["font_size_small"]),
                                    text_color=self.theme["text_secondary"],
                                    anchor="w")
        instructions_label.pack(anchor="w", padx=8, pady=(0, 2))

        # Create text box for editing the schedule
        self.schedule_textbox = ctk.CTkTextbox(schedule_frame,
                                            fg_color=self.theme["surface_dark"],
                                            border_color=self.theme["border"],
                                            corner_radius=self.theme["corner_radius"],
                                            height=120)
        self.schedule_textbox.pack(fill="x", padx=8, pady=(0, 8))

        # Fill the text box with the current schedule
        current_schedule = self.macro_data.get("SPACE_TIMED_SPEED_SCHEDULE", [
            [0.0, 2500.0], [2.0, 2200.0], [4.0, 1800.0], [6.0, 1500.0], [8.0, 1150.0]
        ])

        schedule_text = ""
        for time_val, speed_val in current_schedule:
            schedule_text += f"{time_val}, {speed_val}\n"

        self.schedule_textbox.delete("1.0", "end")
        self.schedule_textbox.insert("1.0", schedule_text.strip())

        # Store the textbox in config_entries with a special key
        self.config_entries["SPACE_TIMED_SPEED_SCHEDULE"] = self.schedule_textbox

        # Create section headers
        self.create_section_header("MOVEMENT SETTINGS")
        self.create_config_fields(movement_fields)

        self.create_section_header("KEY BINDINGS")
        self.create_config_fields(key_fields)

        self.create_section_header("MOVEMENT BEHAVIOR")
        self.create_config_fields(behavior_fields)

        self.create_section_header("SPACE TIMING")
        self.create_config_fields(space_fields)

        self.create_section_header("HUMANIZATION")
        self.create_config_fields(humanization_fields)

        self.create_section_header("VIRTUAL DEVICES")
        self.create_config_fields(device_fields)

        self.create_section_header("LOGGING")
        self.create_config_fields(log_fields)

    def create_generic_config(self):
        for key, value in self.macro_data.items():
            if key in ['name', 'script_path', 'description']:
                continue

            entry_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=self.theme["corner_radius"])
            entry_frame.pack(fill="x", padx=5, pady=self.theme["spacing"])

            label = ctk.CTkLabel(entry_frame, text=f"{key.replace('_', ' ').title()}:",
                                 font=ctk.CTkFont(size=self.theme["font_size_medium"]),
                                 text_color=self.theme["text_primary"],
                                 width=120, anchor="w")
            label.pack(side="left", padx=(8, 5), pady=6)

            self.config_entries[key] = ctk.CTkEntry(entry_frame, width=150,
                                                    fg_color=self.theme["surface_dark"],
                                                    border_color=self.theme["border"],
                                                    corner_radius=self.theme["corner_radius"])
            self.config_entries[key].insert(0, str(value))
            self.config_entries[key].pack(side="right", padx=(5, 8), pady=4)

    def create_config_fields(self, fields):
        for field_def in fields:
            field_name = field_def[0]
            display_name = field_def[1]
            field_type = field_def[2] if len(field_def) > 2 else 'text'
            options = field_def[3] if len(field_def) > 3 else []

            entry_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=self.theme["corner_radius"])
            entry_frame.pack(fill="x", padx=5, pady=self.theme["spacing"])

            label = ctk.CTkLabel(entry_frame, text=f"{display_name}:",
                                 font=ctk.CTkFont(size=self.theme["font_size_medium"]),
                                 text_color=self.theme["text_primary"],
                                 width=120, anchor="w")
            label.pack(side="left", padx=(8, 5), pady=6)

            if field_type == 'dropdown':
                self.config_entries[field_name] = ctk.CTkOptionMenu(entry_frame,
                                                                    values=options,
                                                                    width=150,
                                                                    fg_color=self.theme["primary"],
                                                                    button_color=self.theme["primary_hover"],
                                                                    button_hover_color=self.theme["primary"],
                                                                    corner_radius=self.theme["corner_radius"])
                self.config_entries[field_name].set(str(self.macro_data.get(field_name, options[0])))
            else:
                self.config_entries[field_name] = ctk.CTkEntry(entry_frame, width=150,
                                                               fg_color=self.theme["surface_dark"],
                                                               border_color=self.theme["border"],
                                                               corner_radius=self.theme["corner_radius"])
                self.config_entries[field_name].insert(0, str(self.macro_data.get(field_name, '')))

            self.config_entries[field_name].pack(side="right", padx=(5, 8), pady=4)

def save_config(self):
    try:
        for key, entry in self.config_entries.items():
            if key == "SPACE_TIMED_SPEED_SCHEDULE" and hasattr(entry, 'get'):
                # Handle the schedule text box specially
                schedule_text = entry.get("1.0", "end").strip()
                schedule_array = []

                for line in schedule_text.split('\n'):
                    line = line.strip()
                    if line:
                        try:
                            # Parse "time, speed" format
                            parts = line.split(',')
                            if len(parts) == 2:
                                time_val = float(parts[0].strip())
                                speed_val = float(parts[1].strip())
                                schedule_array.append([time_val, speed_val])
                        except ValueError:
                            # Skip invalid lines
                            self.main_app.log(f"Warning: Skipped invalid schedule line: {line}")

                # Sort the schedule by time
                schedule_array.sort(key=lambda x: x[0])
                self.macro_data[key] = schedule_array
            elif hasattr(entry, 'get'):
                value = entry.get()
                # Try to convert numbers
                number_fields = [
                    'cps', 'click_duration',
                    'SPEED_PX_PER_SEC_DEFAULT', 'MIN_SPEED_PX_PER_SEC', 'MAX_SPEED_PX_PER_SEC',
                    'SPEEDUP_MULTIPLIER', 'SLOWDOWN_MULTIPLIER', 'SCROLL_SPEED_STEP',
                    'ACCEL_TIME_S', 'DECEL_TIME_S', 'MIN_FRAME_TIME',
                    'MAX_STEP_PX', 'DEADZONE_VEL_PX_S', 'NOISE_PER_STEP_PX',
                    'START_MOVE_DELAY_S', 'SPACE_TICK_SECONDS', 'LOG_SPEEDLINE_INTERVAL_S'
                ]

                if key in number_fields and value:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
                self.macro_data[key] = value

        if self.save_macro_config():
            messagebox.showinfo("Success", "Configuration saved!")
            self.main_app.log(f"Configuration for '{self.macro_name}' updated")
        else:
            messagebox.showerror("Error", "Failed to save configuration")

    except Exception as e:
        messagebox.showerror("Error", f"Failed to save configuration: {str(e)}")

class MacroManager:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Macro Manager")
        self.root.geometry("1100x650")

        # Initialize theme and style managers
        self.theme_manager = ThemeManager()
        self.style_manager = StyleManager(self.theme_manager)
        self.theme = self.theme_manager.current_theme

        # Apply theme to root
        self.root.configure(fg_color=self.theme["background"])

        # Make window pop out
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(100, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()

        # Paths
        self.macros_dir = os.path.expanduser("~/macro-manager/macros/")
        self.configs_dir = os.path.expanduser("~/macro-manager/configs/")
        self.main_config_file = os.path.expanduser("~/macro-manager/macros.json")

        # Ensure directories exist
        os.makedirs(self.macros_dir, exist_ok=True)
        os.makedirs(self.configs_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.main_config_file), exist_ok=True)

        # Load macros
        self.macros = self.load_macros()
        self.scan_macros_folder()

        # Running macros tracking
        self.running_macros = {}

        # Setup UI
        self.setup_ui()

        # Setup graceful shutdown
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        signal.signal(signal.SIGINT, self.signal_handler)

        # Debug macro detection
        self.debug_macro_detection()

    def debug_macro_detection(self):
        """Debug helper to check macro detection"""
        for macro_name, macro_data in self.macros.items():
            script_path = macro_data.get('script_path', '')
            macro_type = self.detect_macro_type(script_path)
            self.log(f"Macro: {macro_name}, Type: {macro_type}, Path: {os.path.basename(script_path)}")

    def scan_macros_folder(self):
        """Automatically scan the macros folder for Python files"""
        try:
            python_files = glob.glob(os.path.join(self.macros_dir, "*.py"))

            for script_path in python_files:
                script_name = os.path.splitext(os.path.basename(script_path))[0]

                # Skip if already exists
                if script_name in self.macros:
                    continue

                # Add basic info to macros list
                self.macros[script_name] = {
                    'name': script_name,
                    'script_path': script_path,
                    'description': f"Auto-discovered: {os.path.basename(script_path)}"
                }
                print(f"Auto-discovered macro: {script_name}")

            # Save updated macros list
            if python_files:
                self.save_macros()

        except Exception as e:
            print(f"Error scanning macros folder: {e}")

    def setup_ui(self):
        # Header with title
        header_frame = ctk.CTkFrame(self.root, corner_radius=0, height=35)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)

        title_label = ctk.CTkLabel(header_frame, text="MACRO MANAGER",
                                   font=ctk.CTkFont(size=self.theme["font_size_medium"]+2, weight="bold"),
                                   text_color=self.theme["text_accent"])
        title_label.pack(side="left", pady=8, padx=12)

        # Main content frame
        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=8, pady=8)

        # Left side - Macros (compact and fixed width)
        left_frame = ctk.CTkFrame(main_frame, corner_radius=self.theme.get("corner_radius", 6),
                                  width=300, border_width=self.theme.get("border_width", 1),
                                  border_color=self.theme.get("border", "#333333"))
        left_frame.pack(side="left", fill="y", padx=(0, 4))
        left_frame.pack_propagate(False)

        # Macros header
        macros_label = ctk.CTkLabel(left_frame, text="MACROS",
                                    font=ctk.CTkFont(size=self.theme["font_size_medium"]+1, weight="bold"),
                                    text_color=self.theme["text_accent"])
        macros_label.pack(pady=(8, 5))

        # Macro list (scrollable, compact)
        self.macros_scroll = ctk.CTkScrollableFrame(left_frame, corner_radius=self.theme.get("corner_radius", 6))
        self.macros_scroll.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # Bottom buttons container
        bottom_container = ctk.CTkFrame(left_frame, fg_color="transparent")
        bottom_container.pack(fill="x", padx=6, pady=(0, 6))

        # Add macro button
        add_macro_btn = ctk.CTkButton(bottom_container, text="+ ADD MACRO",
                                      command=self.add_macro,
                                      fg_color=self.theme["primary"],
                                      hover_color=self.theme["primary_hover"],
                                      height=self.theme["button_height"]+3,
                                      font=ctk.CTkFont(size=self.theme["font_size_small"]+2, weight="bold"),
                                      corner_radius=self.theme["corner_radius"])
        add_macro_btn.pack(fill="x", pady=(0, self.theme["spacing"]))

        # Icon buttons row
        icon_frame = ctk.CTkFrame(bottom_container, fg_color="transparent")
        icon_frame.pack(fill="x")

        kill_all_btn = ctk.CTkButton(icon_frame, text="⚠️",
                                     command=self.kill_all_macros,
                                     fg_color=self.theme["error"], hover_color="#cc3333",
                                     width=40, height=self.theme["button_height"]+5,
                                     font=ctk.CTkFont(size=self.theme["font_size_medium"]),
                                     corner_radius=self.theme["corner_radius"])
        kill_all_btn.pack(side="left", padx=(0, self.theme["spacing"]))

        settings_btn = ctk.CTkButton(icon_frame, text="⚙️",
                                     command=self.open_settings,
                                     fg_color=self.theme["border"], hover_color="#555555",
                                     width=40, height=self.theme["button_height"]+5,
                                     font=ctk.CTkFont(size=self.theme["font_size_medium"]),
                                     corner_radius=self.theme["corner_radius"])
        settings_btn.pack(side="left")

        # Right side - Tabbed content
        right_frame = ctk.CTkFrame(main_frame, corner_radius=self.theme.get("corner_radius", 6),
                                   border_width=self.theme.get("border_width", 1),
                                   border_color=self.theme.get("border", "#333333"))
        right_frame.pack(side="right", fill="both", expand=True, padx=(4, 0))

        # Tab system
        self.tabview = ctk.CTkTabview(right_frame, corner_radius=self.theme.get("corner_radius", 6),
                                      segmented_button_selected_color=self.theme.get("primary", "#ff3333"),
                                      segmented_button_selected_hover_color=self.theme.get("primary_hover", "#dd2222"))
        self.tabview.pack(fill="both", expand=True, padx=6, pady=6)

        # Main tab (Logs)
        self.main_tab = self.tabview.add("Logs")
        self.setup_logs_tab()

        # Load existing macros
        self.refresh_macros()
        self.log("Macro Manager started")
        self.log(f"Scanning: {self.macros_dir}")
        self.log(f"Current style: {self.theme.get('current_style', 'Modern')}")

    def setup_logs_tab(self):
        # Logs text area
        self.logs_text = ctk.CTkTextbox(self.main_tab, corner_radius=self.theme.get("corner_radius", 6),
                                        fg_color=self.theme.get("surface_dark", "#0a0a0a"),
                                        text_color=self.theme.get("text_primary", "#ffffff"),
                                        font=ctk.CTkFont(family="monospace", size=self.theme.get("font_size_small", 10)+1),
                                        border_color=self.theme.get("border", "#333333"),
                                        border_width=self.theme.get("border_width", 1))
        self.logs_text.pack(fill="both", expand=True, padx=6, pady=(6, 3))

        # Clear logs button
        clear_logs_btn = ctk.CTkButton(self.main_tab, text="Clear Logs",
                                       command=self.clear_logs,
                                       fg_color=self.theme.get("border", "#333333"), hover_color="#555555",
                                       height=self.theme.get("button_height", 22),
                                       font=ctk.CTkFont(size=self.theme.get("font_size_small", 10)+1),
                                       corner_radius=self.theme.get("corner_radius", 6))
        clear_logs_btn.pack(fill="x", padx=6, pady=(0, 6))

    def refresh_macros(self):
        # Clear existing macro entries
        for widget in self.macros_scroll.winfo_children():
            widget.destroy()

        if not self.macros:
            no_macros_label = ctk.CTkLabel(self.macros_scroll,
                                           text=f"No macros found\n\nPlace Python files in:\n{self.macros_dir}",
                                           font=ctk.CTkFont(size=self.theme["font_size_small"]+2),
                                           text_color=self.theme["text_secondary"])
            no_macros_label.pack(pady=40)
            return

        # Create compact macro entries
        for macro_name, macro_data in self.macros.items():
            self.create_macro_entry(macro_name, macro_data)

    def create_macro_entry(self, macro_name, macro_data):
        # Ultra compact macro frame
        macro_frame = ctk.CTkFrame(self.macros_scroll, corner_radius=self.theme["corner_radius"],
                                   height=50)  # Fixed small height
        macro_frame.pack(fill="x", padx=4, pady=2)
        macro_frame.pack_propagate(False)

        # Status dot (small)
        is_running = macro_name in self.running_macros
        status_color = self.theme["success"] if is_running else self.theme["error"]

        status_dot = ctk.CTkLabel(macro_frame, text="●",
                                  font=ctk.CTkFont(size=self.theme["font_size_small"]+2),
                                  text_color=status_color, width=20)
        status_dot.pack(side="left", padx=(6, 4), pady=6)

        # Macro name (compact)
        name_frame = ctk.CTkFrame(macro_frame, fg_color="transparent")
        name_frame.pack(side="left", fill="both", expand=True, padx=2, pady=6)

        name_label = ctk.CTkLabel(name_frame, text=macro_name,
                                  font=ctk.CTkFont(size=self.theme["font_size_small"]+1, weight="bold"),
                                  anchor="w", text_color=self.theme["text_primary"])
        name_label.pack(anchor="w", fill="x")

        # Compact buttons
        btn_frame = ctk.CTkFrame(macro_frame, fg_color="transparent")
        btn_frame.pack(side="right", padx=4, pady=6)

        # Action button (start/stop)
        if is_running:
            action_btn = ctk.CTkButton(btn_frame, text="STOP",
                                       command=lambda name=macro_name: self.stop_macro(name),
                                       fg_color=self.theme["error"], hover_color="#cc3333",
                                       width=45, height=18,
                                       font=ctk.CTkFont(size=self.theme["font_size_small"], weight="bold"),
                                       corner_radius=self.theme["corner_radius"])
        else:
            action_btn = ctk.CTkButton(btn_frame, text="START",
                                       command=lambda name=macro_name: self.start_macro(name),
                                       fg_color=self.theme["success"], hover_color=self.theme["success_hover"],
                                       text_color="#000000", width=45, height=18,
                                       font=ctk.CTkFont(size=self.theme["font_size_small"], weight="bold"),
                                       corner_radius=self.theme["corner_radius"])
        action_btn.pack(side="right", padx=1)

        # Delete button
        delete_btn = ctk.CTkButton(btn_frame, text="×",
                                   command=lambda name=macro_name: self.delete_macro(name),
                                   fg_color=self.theme["border"], hover_color="#777777",
                                   width=25, height=18,
                                   font=ctk.CTkFont(size=self.theme["font_size_small"]+1, weight="bold"),
                                   corner_radius=self.theme["corner_radius"])
        delete_btn.pack(side="right")

    def kill_all_macros(self):
        """Kill all running macros immediately"""
        if not self.running_macros:
            messagebox.showinfo("Info", "No macros are currently running")
            return

        result = messagebox.askyesno("Confirm Kill All",
                                     f"Terminate {len(self.running_macros)} running macro(s)?")
        if result:
            killed_count = 0
            for macro_name in list(self.running_macros.keys()):
                try:
                    process = self.running_macros[macro_name]
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    del self.running_macros[macro_name]

                    # Close config tab if open
                    tab_name = f"Config: {macro_name}"
                    if tab_name in self.tabview._tab_dict:
                        self.tabview.delete(tab_name)

                    killed_count += 1
                except:
                    pass

            self.refresh_macros()
            self.log(f"Killed {killed_count} macro(s)")

    def open_settings(self):
        if "Settings" not in self.tabview._tab_dict:
            settings_tab = self.tabview.add("Settings")
            AdvancedSettingsTab(settings_tab, self)
        self.tabview.set("Settings")

    def open_config(self, macro_name):
        tab_name = f"Config: {macro_name}"
        if tab_name not in self.tabview._tab_dict:
            config_tab = self.tabview.add(tab_name)
            ConfigTab(config_tab, macro_name, self)
        self.tabview.set(tab_name)

    def detect_macro_type(self, script_path):
        try:
            if not script_path or not os.path.exists(script_path):
                return 'generic'

            # Check the filename first - this should definitely catch "strafer.py"
            basename = os.path.basename(script_path).lower()
            if 'strafe' in basename or 'strafer' in basename:
                print(f"Detected strafer from filename: {basename}")
                return 'strafer'

            with open(script_path, 'r') as f:
                content = f.read().lower()

            # Check for autoclicker indicators
            if 'autoclicker' in content or 'click' in basename:
                return 'autoclicker'

            # Check for strafer indicators - more keywords
            strafer_keywords = ['strafe', 'strafer', 'strafing', 'a/d', 'key_a', 'key_d']
            for keyword in strafer_keywords:
                if keyword in content:
                    print(f"Detected strafer from content keyword: {keyword}")
                    return 'strafer'

        except Exception as e:
            print(f"Error detecting macro type: {e}")

        return 'generic'

    def start_macro(self, macro_name):
        if macro_name in self.running_macros:
            messagebox.showwarning("Warning", f"Macro '{macro_name}' is already running!")
            return

        try:
            macro_data = self.macros[macro_name]
            script_path = macro_data.get('script_path', '')

            if not script_path or not os.path.exists(script_path):
                messagebox.showerror("Error", f"Script not found for macro '{macro_name}'")
                return

            # Show device picker (always centered and on top)
            picker = DevicePicker(self.root, self.theme)
            self.root.wait_window(picker.window)

            if not picker.selected_device:
                self.log(f"Device selection cancelled for '{macro_name}'")
                return

            device_path = picker.selected_device
            self.log(f"Selected device: {device_path}")

            # Load specific macro config
            config_file = os.path.expanduser(f"~/macro-manager/configs/{macro_name}.json")
            macro_config = {}
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r') as f:
                        macro_config = json.load(f)
                except:
                    pass

            # Build command
            cmd = self.build_command(script_path, macro_config, device_path)

            # Start process
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       preexec_fn=os.setsid)

            self.running_macros[macro_name] = process
            self.refresh_macros()
            self.log(f"Started macro: {macro_name}")

            # Automatically open config tab when starting
            self.open_config(macro_name)

            # Monitor process in background
            def monitor_process():
                try:
                    stdout, stderr = process.communicate()
                    if process.returncode != 0:
                        error_msg = stderr.decode() if stderr else "Process exited unexpectedly"
                        self.root.after(0, lambda: self.macro_crashed(macro_name, error_msg))
                    else:
                        self.root.after(0, lambda: self.macro_finished(macro_name))
                except:
                    self.root.after(0, lambda: self.macro_finished(macro_name))

            threading.Thread(target=monitor_process, daemon=True).start()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to start macro '{macro_name}': {str(e)}")

    def build_command(self, script_path, macro_config, device_path):
        cmd = ['python3', script_path]

        if device_path:
            cmd.extend(['--device', device_path])

        # Force detect the macro type and print it
        macro_type = self.detect_macro_type(script_path)
        print(f"Building command for macro type: {macro_type}")

        if macro_type == 'autoclicker':
            if 'cps' in macro_config:
                cmd.extend(['--cps', str(macro_config['cps'])])
            if 'click_duration' in macro_config:
                cmd.extend(['--duration', str(macro_config['click_duration'])])
            if 'trigger_button' in macro_config:
                cmd.extend(['--trigger', str(macro_config['trigger_button'])])
            if 'target_button' in macro_config:
                cmd.extend(['--target', str(macro_config['target_button'])])

        elif macro_type == 'strafer':
            # For strafer, create a temporary config file with all settings
            config_dir = os.path.expanduser("~/macro-manager/configs")
            os.makedirs(config_dir, exist_ok=True)

            # Make sure the config file has the right path and name
            config_file = os.path.join(config_dir, f"{macro_type}_{os.path.basename(script_path).split('.')[0]}_config.json")

            try:
                with open(config_file, 'w') as f:
                    json.dump(macro_config, f, indent=4)
                cmd.extend(['--config', config_file])
                self.log(f"Created config for strafer at: {config_file}")
            except Exception as e:
                self.log(f"Error creating config file for strafer: {e}")

                # Fallback to passing some key parameters directly
                if 'SPEED_PX_PER_SEC_DEFAULT' in macro_config:
                    cmd.extend(['--speed', str(macro_config['SPEED_PX_PER_SEC_DEFAULT'])])
                if 'INVERT_X' in macro_config:
                    cmd.extend(['--invert', str(macro_config['INVERT_X']).lower()])

        return cmd

    def stop_macro(self, macro_name):
        if macro_name not in self.running_macros:
            return

        try:
            process = self.running_macros[macro_name]

            # Graceful shutdown
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                process.wait(timeout=3)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            except Exception:
                process.terminate()
                time.sleep(1)
                if process.poll() is None:
                    process.kill()

            del self.running_macros[macro_name]

            # Close config tab if open
            tab_name = f"Config: {macro_name}"
            if tab_name in self.tabview._tab_dict:
                self.tabview.delete(tab_name)

            self.refresh_macros()
            self.log(f"Stopped macro: {macro_name}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to stop macro: {str(e)}")

    def macro_crashed(self, macro_name, error):
        if macro_name in self.running_macros:
            del self.running_macros[macro_name]

        # Close config tab if open
        tab_name = f"Config: {macro_name}"
        if tab_name in self.tabview._tab_dict:
            self.tabview.delete(tab_name)

        self.refresh_macros()
        self.log(f"Macro '{macro_name}' crashed: {error}")

    def macro_finished(self, macro_name):
        if macro_name in self.running_macros:
            del self.running_macros[macro_name]

        # Close config tab if open
        tab_name = f"Config: {macro_name}"
        if tab_name in self.tabview._tab_dict:
            self.tabview.delete(tab_name)

        self.refresh_macros()
        self.log(f"Macro '{macro_name}' finished")

    def add_macro(self):
        script_path = filedialog.askopenfilename(
            title="Select Macro Script",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")],
            initialdir=self.macros_dir
        )

        if not script_path:
            return

        macro_name = os.path.splitext(os.path.basename(script_path))[0]

        dialog = ctk.CTkInputDialog(title="Macro Name", text="Name for this macro:")
        dialog_result = dialog.get_input()

        if dialog_result:
            macro_name = dialog_result

        if macro_name in self.macros:
            messagebox.showerror("Error", "Macro with this name already exists!")
            return

        self.macros[macro_name] = {
            'name': macro_name,
            'script_path': script_path,
            'description': f"Macro: {os.path.basename(script_path)}"
        }

        self.save_macros()
        self.refresh_macros()
        self.log(f"Added macro: {macro_name}")

    def delete_macro(self, macro_name):
        result = messagebox.askyesno("Confirm Delete", f"Delete macro '{macro_name}'?")
        if result:
            if macro_name in self.running_macros:
                self.stop_macro(macro_name)

            # Close config tab if open
            tab_name = f"Config: {macro_name}"
            if tab_name in self.tabview._tab_dict:
                self.tabview.delete(tab_name)

            # Delete config file
            config_file = os.path.expanduser(f"~/macro-manager/configs/{macro_name}.json")
            try:
                if os.path.exists(config_file):
                    os.remove(config_file)
            except:
                pass

            del self.macros[macro_name]
            self.save_macros()
            self.refresh_macros()
            self.log(f"Deleted macro: {macro_name}")

    def load_macros(self):
        """Load the main macros list"""
        try:
            if os.path.exists(self.main_config_file):
                with open(self.main_config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading macros: {e}")
        return {}

    def save_macros(self):
        """Save the main macros list"""
        try:
            with open(self.main_config_file, 'w') as f:
                json.dump(self.macros, f, indent=4)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save macros: {e}")

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        self.logs_text.insert("end", log_entry)
        self.logs_text.see("end")

    def clear_logs(self):
        self.logs_text.delete("1.0", "end")
        self.log("Logs cleared")

    def on_closing(self):
        """Clean shutdown - stop all running macros"""
        try:
            # Stop all running macros
            for macro_name in list(self.running_macros.keys()):
                self.stop_macro(macro_name)
        except Exception as e:
            print(f"Error during shutdown: {e}")
        finally:
            self.root.quit()
            self.root.destroy()

    def signal_handler(self, sig, frame):
        """Handle system signals"""
        self.on_closing()

    def run(self):
        """Start the application"""
        self.root.mainloop()

if __name__ == "__main__":
    # Check for required dependencies
    try:
        import customtkinter
        import evdev
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install with: pip install customtkinter evdev")
        sys.exit(1)

    # Create and run the application
    try:
        app = MacroManager()
        app.run()
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Application error: {e}")
        sys.exit(1)
