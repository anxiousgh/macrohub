#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Smooth Flick Mouse Mover - Compatible with Macro Manager
# - Easing curves incl. exponential
# - Forward overshoot and return overshoot, each with MIN/MAX percentage
# - Percentages can be NEGATIVE to create an undershoot (stop short) before settling
# - Optional settle-back after each overshoot/undershoot
# - Micro-noise + per-trigger distance jitter

import evdev
from evdev import InputDevice, UInput, ecodes as e
import threading
import time
import sys
import os
import select
import glob
import math
import random
import argparse
import json
import signal
from typing import Optional, List
from dataclasses import dataclass

class WallhopMacro:
    def __init__(self, device_path: str = None, config_path: str = None):
        self.config_path = config_path
        self.device_path = device_path
        self.running = True

        # Default config - will be overridden by loaded config
        self.cfg = {
            # Movement settings
            "MOVE_DISTANCE": 950,
            "MOVE_DURATION": 0.08,

            # Forward overshoot
            "OVERSHOOT_ENABLED": True,
            "FORWARD_SETTLE_ENABLED": False,
            "BACK_DURATION": 0.04,
            "FORWARD_OVERSHOOT_MIN_PCT": 0.1,
            "FORWARD_OVERSHOOT_MAX_PCT": 0.65,

            # Return overshoot
            "RETURN_OVERSHOOT_ENABLED": True,
            "RETURN_SETTLE_ENABLED": False,
            "RETURN_BACK_DURATION": 0.2,
            "RETURN_OVERSHOOT_MIN_PCT": -0.15,
            "RETURN_OVERSHOOT_MAX_PCT": 0.15,

            # Easing
            "EASING_FORWARD": "exp_in_out",
            "EASING_BACK": "cubic_in_out",
            "RETURN_EASING_FORWARD": "exp_in_out",
            "RETURN_EASING_BACK": "cubic_in_out",

            # Humanization
            "ENABLE_NOISE": True,
            "NOISE_PER_STEP_PX": 0.8,
            "JITTER_DISTANCE_PCT": 0.12,

            # Safety and performance
            "MAX_ABS_MOVE_PX": 3000,
            "MIN_FRAME_TIME": 0.0015,

            # Trigger button
            "TRIGGER_BUTTON": "BTN_EXTRA",

            # Virtual device names
            "VIRTUAL_MOUSE_NAME": "smooth-flick-mouse-mover"
        }

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

        # Load config
        self.load_config()

        # State variables
        self.is_moving_active = False
        self.move_worker_thread = None
        
        # Input/output devices
        self.mouse_device = None
        self.virtual_mouse = None

        # Easing functions setup
        self.easings = self.setup_easings()

    def signal_handler(self, signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)

    def load_config(self):
        if self.config_path and os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_cfg = json.load(f)
                    self.cfg.update(loaded_cfg)
                print(f"Loaded config from {self.config_path}")
            except Exception as ex:
                print(f"Error loading config: {ex}")

    def save_config(self):
        if self.config_path:
            try:
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.cfg, f, indent=4)
                print(f"Saved config to {self.config_path}")
                return True
            except Exception as ex:
                print(f"Error saving config: {ex}")
        return False

    def setup_easings(self):
        """Setup easing functions"""
        def ease_linear(t: float) -> float:
            return t

        def ease_cubic_out(t: float) -> float:
            inv = 1.0 - t
            return 1.0 - inv * inv * inv

        def ease_cubic_in_out(t: float) -> float:
            if t < 0.5:
                return 4.0 * t * t * t
            u = -2.0 * t + 2.0
            return 1.0 - (u * u * u) / 2.0

        def ease_quint_out(t: float) -> float:
            inv = 1.0 - t
            return 1.0 - inv**5

        def ease_quad_out(t: float) -> float:
            inv = 1.0 - t
            return 1.0 - inv * inv

        def ease_quart_out(t: float) -> float:
            inv = 1.0 - t
            return 1.0 - inv**4

        def ease_sine_in_out(t: float) -> float:
            return 0.5 * (1 - math.cos(math.pi * t))

        def ease_exp_in(t: float) -> float:
            if t <= 0.0:
                return 0.0
            if t >= 1.0:
                return 1.0
            return 2.0**(10.0 * (t - 1.0))

        def ease_exp_out(t: float) -> float:
            if t <= 0.0:
                return 0.0
            if t >= 1.0:
                return 1.0
            return 1.0 - 2.0**(-10.0 * t)

        def ease_exp_in_out(t: float) -> float:
            if t <= 0.0:
                return 0.0
            if t >= 1.0:
                return 1.0
            if t < 0.5:
                return 0.5 * (2.0**(20.0 * t - 10.0))
            return 1.0 - 0.5 * (2.0**(-20.0 * t + 10.0))

        return {
            "linear": ease_linear,
            "cubic_out": ease_cubic_out,
            "cubic_in_out": ease_cubic_in_out,
            "quint_out": ease_quint_out,
            "quad_out": ease_quad_out,
            "quart_out": ease_quart_out,
            "sine_in_out": ease_sine_in_out,
            "exp_in": ease_exp_in,
            "exp_out": ease_exp_out,
            "exp_in_out": ease_exp_in_out,
        }

    def clamp(self, v, lo, hi):
        return max(lo, min(hi, v))

    def rand_pct_in_range(self, lo: float, hi: float) -> float:
        if lo > hi:
            lo, hi = hi, lo
        return random.uniform(lo, hi)

    def start(self):
        try:
            # Open mouse device
            if not self.device_path or not os.path.exists(self.device_path):
                print(f"Device not found: {self.device_path}")
                return False

            self.mouse_device = InputDevice(self.device_path)
            print(f"Opened device: {self.mouse_device.name}")

            # Create virtual mouse
            try:
                mouse_capabilities = {
                    e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_SIDE, e.BTN_EXTRA],
                    e.EV_REL: [e.REL_X, e.REL_Y]
                }
                self.virtual_mouse = UInput(mouse_capabilities, name=self.cfg["VIRTUAL_MOUSE_NAME"])
                print("Created virtual mouse device")
            except PermissionError:
                print("Permission denied! Run with: sudo python3 wallhop.py")
                return False

            # Get trigger button code
            self.trigger_button_code = getattr(e, self.cfg["TRIGGER_BUTTON"], e.BTN_EXTRA)

            print(f"Wallhop ready! Distance: {self.cfg['MOVE_DISTANCE']}px, Duration: {self.cfg['MOVE_DURATION']*1000:.0f}ms")
            print(f"Trigger: {self.cfg['TRIGGER_BUTTON']}")

            # Start moving worker thread
            if not (self.move_worker_thread and self.move_worker_thread.is_alive()):
                self.move_worker_thread = threading.Thread(target=self._moving_worker, daemon=True)
                self.move_worker_thread.start()

            # Start main input loop
            self.listen_for_input()
            return True

        except Exception as ex:
            print(f"Error starting wallhop: {ex}")
            return False

    def _move_smooth_rel(self, total_x: float, total_y: float, duration_s: float, easing_name: str, noise_per_step: float):
        """Move mouse smoothly with relative positioning"""
        if duration_s <= 0:
            dx = int(round(total_x))
            dy = int(round(total_y))
            if dx or dy:
                self._rel(dx, dy)
            return

        total_x = self.clamp(total_x, -self.cfg["MAX_ABS_MOVE_PX"], self.cfg["MAX_ABS_MOVE_PX"])
        total_y = self.clamp(total_y, -self.cfg["MAX_ABS_MOVE_PX"], self.cfg["MAX_ABS_MOVE_PX"])

        easing = self.easings.get(easing_name, self.easings["cubic_out"])

        start = time.perf_counter()
        end = start + duration_s

        moved_x = 0.0
        moved_y = 0.0

        while True:
            now = time.perf_counter()
            if now >= end:
                break
            t = (now - start) / duration_s
            t = self.clamp(t, 0.0, 1.0)

            eased = easing(t)
            target_x = total_x * eased
            target_y = total_y * eased

            delta_x = target_x - moved_x
            delta_y = target_y - moved_y

            if noise_per_step > 0 and self.cfg["ENABLE_NOISE"]:
                delta_x += random.uniform(-noise_per_step, noise_per_step)
                delta_y += random.uniform(-noise_per_step, noise_per_step)

            step_x = int(round(delta_x))
            step_y = int(round(delta_y))

            if step_x != 0 or step_y != 0:
                moved_x += step_x
                moved_y += step_y
                self._rel(step_x, step_y)

            time.sleep(self.cfg["MIN_FRAME_TIME"])

        # Final correction
        fix_x = int(round(total_x - moved_x))
        fix_y = int(round(total_y - moved_y))
        if fix_x or fix_y:
            self._rel(fix_x, fix_y)

    def _rel(self, dx: int, dy: int):
        """Send relative mouse movement"""
        if dx:
            self.virtual_mouse.write(e.EV_REL, e.REL_X, dx)
        if dy:
            self.virtual_mouse.write(e.EV_REL, e.REL_Y, dy)
        self.virtual_mouse.syn()

    def _perform_single_move(self):
        """Perform one flick with min/max over- and undershoot"""
        try:
            # Per-trigger jitter of distance
            base_dist = float(self.cfg["MOVE_DISTANCE"])
            if self.cfg["JITTER_DISTANCE_PCT"] > 0:
                base_dist *= 1.0 + random.uniform(-self.cfg["JITTER_DISTANCE_PCT"], self.cfg["JITTER_DISTANCE_PCT"])
            base_dist = self.clamp(base_dist, -self.cfg["MAX_ABS_MOVE_PX"], self.cfg["MAX_ABS_MOVE_PX"])

            sign = 1.0 if base_dist >= 0 else -1.0
            current_pos = 0.0  # track where we are along X

            # --- Forward phase: move to forward target with over/undershoot ---
            fwd_pct = 0.0
            if self.cfg["OVERSHOOT_ENABLED"]:
                fwd_pct = self.rand_pct_in_range(self.cfg["FORWARD_OVERSHOOT_MIN_PCT"],
                                                 self.cfg["FORWARD_OVERSHOOT_MAX_PCT"])

            forward_target = base_dist if (not self.cfg["OVERSHOOT_ENABLED"] or fwd_pct == 0.0) else base_dist * (1.0 + fwd_pct)

            self._move_smooth_rel(
                total_x=forward_target - current_pos,
                total_y=0.0,
                duration_s=self.cfg["MOVE_DURATION"],
                easing_name=self.cfg["EASING_FORWARD"],
                noise_per_step=self.cfg["NOISE_PER_STEP_PX"]
            )
            current_pos = forward_target

            # optional settle-back to +base_dist after forward over/undershoot
            if self.cfg["OVERSHOOT_ENABLED"] and fwd_pct != 0.0 and self.cfg["FORWARD_SETTLE_ENABLED"] and self.cfg["BACK_DURATION"] > 0:
                settle_dx = base_dist - current_pos
                if abs(settle_dx) > 0.0:
                    self._move_smooth_rel(
                        total_x=settle_dx,
                        total_y=0.0,
                        duration_s=self.cfg["BACK_DURATION"],
                        easing_name=self.cfg["EASING_BACK"],
                        noise_per_step=self.cfg["NOISE_PER_STEP_PX"]
                    )
                    current_pos = base_dist

            # --- Return phase: back toward origin with over/undershoot ---
            ret_pct = 0.0
            if self.cfg["RETURN_OVERSHOOT_ENABLED"]:
                ret_pct = self.rand_pct_in_range(self.cfg["RETURN_OVERSHOOT_MIN_PCT"],
                                                 self.cfg["RETURN_OVERSHOOT_MAX_PCT"])

            if self.cfg["RETURN_OVERSHOOT_ENABLED"] and ret_pct != 0.0:
                if ret_pct > 0.0:
                    # overshoot to the opposite side of origin
                    pass_target = -sign * abs(base_dist) * ret_pct
                else:
                    # undershoot: stop short of origin, on the same side as current sign
                    pass_target = sign * abs(base_dist) * (-ret_pct)

                self._move_smooth_rel(
                    total_x=pass_target - current_pos,
                    total_y=0.0,
                    duration_s=self.cfg["MOVE_DURATION"],
                    easing_name=self.cfg["RETURN_EASING_FORWARD"],
                    noise_per_step=self.cfg["NOISE_PER_STEP_PX"]
                )
                current_pos = pass_target

                # optional settle to 0 after return over/undershoot
                if self.cfg["RETURN_SETTLE_ENABLED"] and self.cfg["RETURN_BACK_DURATION"] > 0:
                    settle_dx = 0.0 - current_pos
                    if abs(settle_dx) > 0.0:
                        self._move_smooth_rel(
                            total_x=settle_dx,
                            total_y=0.0,
                            duration_s=self.cfg["RETURN_BACK_DURATION"],
                            easing_name=self.cfg["RETURN_EASING_BACK"],
                            noise_per_step=self.cfg["NOISE_PER_STEP_PX"]
                        )
                        current_pos = 0.0
            else:
                # straight return to origin from wherever we are
                self._move_smooth_rel(
                    total_x=0.0 - current_pos,
                    total_y=0.0,
                    duration_s=self.cfg["MOVE_DURATION"],
                    easing_name=self.cfg["EASING_FORWARD"],
                    noise_per_step=self.cfg["NOISE_PER_STEP_PX"]
                )
                current_pos = 0.0

        except Exception as error:
            print(f"Failed to perform move: {error}")
            raise

    def _moving_worker(self):
        """Worker thread that performs the actual movements"""
        print(f"Movement worker started (dist: {self.cfg['MOVE_DISTANCE']}px)")
        
        while self.running:
            if not self.is_moving_active:
                time.sleep(0.02)
                continue
            
            self._perform_single_move()
            self.is_moving_active = False
            time.sleep(0.05)

    def start_moving(self):
        """Start a movement sequence"""
        self.is_moving_active = True

    def listen_for_input(self):
        """Listen for mouse input events"""
        try:
            while self.running:
                ready_devices, _, _ = select.select([self.mouse_device.fd], [], [], 0.02)
                if ready_devices:
                    try:
                        for event in self.mouse_device.read():
                            self._handle_mouse_event(event)
                    except OSError:
                        continue
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

    def _handle_mouse_event(self, event):
        """Handle mouse input events"""
        if event.type == e.EV_KEY and event.code == self.trigger_button_code:
            if event.value == 1:  # Button press
                if not self.is_moving_active:
                    self.start_moving()

    def stop(self):
        """Stop the wallhop macro"""
        self.running = False
        
        if hasattr(self, 'move_worker_thread') and self.move_worker_thread and self.move_worker_thread.is_alive():
            self.move_worker_thread.join(timeout=2)
        
        self._cleanup()

    def _cleanup(self):
        """Clean up resources"""
        print("Cleaning up wallhop resources...")
        
        if hasattr(self, 'mouse_device') and self.mouse_device:
            try:
                self.mouse_device.close()
            except:
                pass
        
        if hasattr(self, 'virtual_mouse') and self.virtual_mouse:
            try:
                self.virtual_mouse.close()
            except:
                pass
        
        print("Wallhop stopped")

def get_button_code(button_name: str) -> str:
    """Convert button name to evdev constant name"""
    button_map = {
        'left': 'BTN_LEFT',
        'right': 'BTN_RIGHT',
        'middle': 'BTN_MIDDLE',
        'side': 'BTN_SIDE',
        'extra': 'BTN_EXTRA',
        'forward': 'BTN_FORWARD',
        'back': 'BTN_BACK',
    }
    
    if not button_name:
        return 'BTN_EXTRA'  # Default
    
    button_name = button_name.lower().strip()
    if button_name in button_map:
        return button_map[button_name]
    
    # Try to parse as integer or return as-is if it looks like BTN_X
    try:
        int(button_name)
        return button_name  # It's a number
    except ValueError:
        if button_name.startswith('btn_'):
            return button_name.upper()
        else:
            return f"BTN_{button_name.upper()}"

def main():
    parser = argparse.ArgumentParser(description='Wallhop (Smooth Flick) - Compatible with Macro Manager')
    parser.add_argument('--device', '-d', help='Input device path (e.g., /dev/input/event2)')
    parser.add_argument('--config', '-c', help='Path to config file')
    
    # Optional arguments for compatibility
    parser.add_argument('--distance', type=int, help='Movement distance in pixels')
    parser.add_argument('--duration', type=float, help='Movement duration in seconds')  
    parser.add_argument('--trigger', help='Trigger button name')

    args = parser.parse_args()

    # Set config path
    config_path = args.config
    if not config_path:
        home = os.path.expanduser("~")
        config_dir = os.path.join(home, "macro-manager", "configs")
        config_path = os.path.join(config_dir, "wallhop.json")

    # Handle device selection
    if not args.device:
        print("Error: Device path is required")
        print("Use --device /dev/input/eventX")
        sys.exit(1)

    # Create wallhop instance
    wallhop = WallhopMacro(device_path=args.device, config_path=config_path)

    # Apply command line overrides if provided
    if args.distance:
        wallhop.cfg["MOVE_DISTANCE"] = args.distance

    if args.duration:
        wallhop.cfg["MOVE_DURATION"] = args.duration

    if args.trigger:
        try:
            button_name = get_button_code(args.trigger)
            wallhop.cfg["TRIGGER_BUTTON"] = button_name
        except:
            print(f"Warning: Unknown trigger button '{args.trigger}', using default")

    try:
        if wallhop.start():
            # Keep running until interrupted
            while wallhop.running:
                time.sleep(0.5)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    finally:
        wallhop.stop()

if __name__ == "__main__":
    main()
