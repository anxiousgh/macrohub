#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Auto Strafer - compatible with Macro Manager GUI
# Commands:
#   A/D: strafe left/right (SOCD = last pressed)
#   ESC: pause (release held)
#   CTRL: boost   | SHIFT: slow
#   BTN_EXTRA: freeze mouse motion
#   F9: toggle wheel-adjust (scroll to change base speed)
#   SPACE: timed ramp (equal steps per tick between schedule points)

import os, sys, json, time, math, select, threading, random, argparse, errno, fcntl, signal, glob
from typing import Optional, Dict, List, Tuple, Any
from evdev import InputDevice, UInput, ecodes as e

# ---------- utils
def clamp(v, lo, hi): return lo if v < lo else hi if v > hi else v
def sgn(x): return -1 if x < 0 else (1 if x > 0 else 0)
def ease_linear(t: float) -> float: return t
def ease_cubic_in_out(t: float) -> float: return 4*t*t*t if t < 0.5 else 1 - ((-2*t + 2) ** 3) / 2
def ease_exp_in_out(t: float):
    if t <= 0: return 0.0
    if t >= 1: return 1.0
    return 0.5 * (2 ** (20 * t - 10)) if t < 0.5 else 1 - 0.5 * (2 ** (-20 * t + 10))
EASINGS = {"linear": ease_linear, "cubic_in_out": ease_cubic_in_out, "exp_in_out": ease_exp_in_out}

def _set_nonblocking(dev: InputDevice, enable: bool = True):
    try:
        if hasattr(dev, "set_nonblocking"): dev.set_nonblocking(enable); return
    except: pass
    try:
        flags = fcntl.fcntl(dev.fd, fcntl.F_GETFL)
        fcntl.fcntl(dev.fd, fcntl.F_SETFL, (flags | os.O_NONBLOCK) if enable else (flags & ~os.O_NONBLOCK))
    except Exception as ex:
        print(f"⚠️ could not set nonblocking on {getattr(dev,'path','?')}: {ex}")

class StraferMacro:
    def __init__(self, device_path: str = None, config_path=None):
        self.config_path = config_path
        self.device_path = device_path
        self.running = True

        # Default config - will be overridden by loaded config
        self.cfg = {
            "LEFT_PHYS_KEY_NAME": "KEY_A",
            "RIGHT_PHYS_KEY_NAME": "KEY_D",
            "PAUSE_KEY_NAME": "KEY_ESC",
            "SPEEDUP_KEY_NAME": "KEY_LEFTCTRL",
            "SLOWDOWN_KEY_NAME": "KEY_LEFTSHIFT",
            "STOP_MOUSE_BUTTON": "BTN_EXTRA",
            "WHEEL_ADJUST_TOGGLE_NAME": "KEY_F9",
            "SPACE_TIMED_KEY_NAME": "KEY_SPACE",
            "SCROLL_SPEED_STEP": 100.0,
            "MIN_SPEED_PX_PER_SEC": 100.0,
            "MAX_SPEED_PX_PER_SEC": 20000.0,
            "SPEED_PX_PER_SEC_DEFAULT": 2000.0,
            "SPEEDUP_MULTIPLIER": 2.0,
            "SLOWDOWN_MULTIPLIER": 0.5,
            "INVERT_X": False,
            "ACCEL_TIME_S": 0.001,
            "DECEL_TIME_S": 0.001,
            "EASING": "exp_in_out",
            "MIN_FRAME_TIME": 0.0015,
            "MAX_STEP_PX": 12,
            "DEADZONE_VEL_PX_S": 0.5,
            "HUMANIZE_NOISE": False,
            "NOISE_PER_STEP_PX": 0.35,
            "START_MOVE_DELAY_S": 0.01,
            "VERBOSE": False,
            "VKB_NAME": "strafer-kb",
            "VMOUSE_NAME": "strafer-mouse",
            "SPACE_MIRROR_TO_GAME": True,
            "SPACE_TIMED_SPEED_SCHEDULE": [[0.0, 2500.0], [2.0, 2200.0], [4.0, 1800.0], [6.0, 1500.0], [8.0, 1150.0]],
            "SPACE_TICK_SECONDS": 1.0,
            "SPACE_ALLOW_INCREASE": False,
            "SPACE_RESTART_ON_PRESS": True,
            "SPACE_STOP_ON_RELEASE": True,
            "LOG_LEVEL": "minimal",
            "LOG_TICKS": False,
            "LOG_STAGES": True,
            "LOG_RESTARTS": True,
            "LOG_SPEEDLINE_INTERVAL_S": 0.25,
            "AUTO_DETECT_DEVICES": True
        }

        # State variables
        self.mode = None
        self.held_key_code = None
        self.vel = 0.0
        self.speedup = False
        self.slowdown = False
        self.move_delay_until = 0.0
        self.mouse_paused = False
        self.wheel_adjust_mode = True
        self.a_down = False
        self.d_down = False
        self.last_pressed = None

        # Space timing variables
        self.space_down = False
        self.space_press_t = 0.0
        self.space_original_speed = 0.0  # Store original speed before space ramp
        self.seg_idx = -1
        self.seg_start_t = 0.0
        self.seg_end_t = 0.0
        self.seg_start_speed = 0.0
        self.seg_target = None
        self.seg_ticks_total = 0
        self.seg_tick_idx = 0
        self.next_tick_time = 0.0
        self._last_speedline = 0.0

        # Input/output devices - now supporting multiple input devices
        self.input_devices = []
        self.vkb = None
        self.vmouse = None
        self.move_thread = None

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

        # Load config
        self.load_config()

        # Set current speed from config
        self.current_speed = float(self.cfg["SPEED_PX_PER_SEC_DEFAULT"])

        # Set up the space schedule
        self.space_sched = sorted([(float(t), float(v)) for (t, v) in self.cfg["SPACE_TIMED_SPEED_SCHEDULE"]], key=lambda x: x[0])
        self.space_tick_s = float(self.cfg["SPACE_TICK_SECONDS"])
        self.space_allow_up = bool(self.cfg["SPACE_ALLOW_INCREASE"])

        # Key/button codes
        self.key_left = getattr(e, self.cfg["LEFT_PHYS_KEY_NAME"])
        self.key_right = getattr(e, self.cfg["RIGHT_PHYS_KEY_NAME"])
        self.key_pause = getattr(e, self.cfg["PAUSE_KEY_NAME"]) if self.cfg.get("PAUSE_KEY_NAME") else None
        self.key_speed = getattr(e, self.cfg["SPEEDUP_KEY_NAME"]) if self.cfg.get("SPEEDUP_KEY_NAME") else None
        self.key_slow = getattr(e, self.cfg["SLOWDOWN_KEY_NAME"]) if self.cfg.get("SLOWDOWN_KEY_NAME") else None
        self.key_wheel_t = getattr(e, self.cfg["WHEEL_ADJUST_TOGGLE_NAME"]) if self.cfg.get("WHEEL_ADJUST_TOGGLE_NAME") else None
        self.space_key = getattr(e, self.cfg["SPACE_TIMED_KEY_NAME"])
        self.stop_btn = getattr(e, self.cfg["STOP_MOUSE_BUTTON"])

        # Easing function
        self.ease = EASINGS.get(self.cfg["EASING"], ease_exp_in_out)

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

    def find_input_devices(self):
        """Find and return available input devices"""
        devices = []
        for path in sorted(glob.glob('/dev/input/event*')):
            try:
                device = InputDevice(path)
                caps = device.capabilities()

                if e.EV_KEY in caps:
                    keys = caps[e.EV_KEY]
                    has_mouse = any(btn in keys for btn in [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_SIDE, e.BTN_EXTRA])
                    has_keyboard = any(key in keys for key in range(e.KEY_A, e.KEY_Z+1))
                    has_wheel = e.EV_REL in caps and (e.REL_WHEEL in caps[e.EV_REL] or
                                                     (hasattr(e, "REL_WHEEL_HI_RES") and e.REL_WHEEL_HI_RES in caps[e.EV_REL]))

                    device_info = {
                        'path': path,
                        'name': device.name,
                        'device': device,
                        'has_mouse': has_mouse,
                        'has_keyboard': has_keyboard,
                        'has_wheel': has_wheel
                    }
                    devices.append(device_info)
                else:
                    device.close()
            except Exception as ex:
                print(f"Error checking device {path}: {ex}")

        return devices

    def open_devices(self):
        """Open input devices - either specified device or auto-detect"""
        try:
            if self.device_path:
                # Use specified device
                if not os.path.exists(self.device_path):
                    print(f"Device not found: {self.device_path}")
                    return False

                device = InputDevice(self.device_path)
                try:
                    device.grab()
                    print(f"Using specified device: {device.name} ({self.device_path})")
                except OSError as ex:
                    if ex.errno in (errno.EACCES, errno.EPERM):
                        print(f"Permission denied grabbing device {self.device_path}")
                        return False
                    print(f"⚠️ Grab failed on {self.device_path}: {ex}")

                _set_nonblocking(device, True)
                self.input_devices.append(device)

                # If auto-detect is enabled, also find additional devices for missing capabilities
                if self.cfg.get("AUTO_DETECT_DEVICES", True):
                    available_devices = self.find_input_devices()
                    device_caps = device.capabilities()

                    has_keyboard = e.EV_KEY in device_caps and any(key in device_caps[e.EV_KEY] for key in range(e.KEY_A, e.KEY_Z+1))
                    has_mouse = e.EV_KEY in device_caps and any(btn in device_caps[e.EV_KEY] for btn in [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE])
                    has_wheel = e.EV_REL in device_caps and (e.REL_WHEEL in device_caps[e.EV_REL] or
                                                           (hasattr(e, "REL_WHEEL_HI_RES") and e.REL_WHEEL_HI_RES in device_caps[e.EV_REL]))

                    # Add additional devices for missing capabilities
                    for dev_info in available_devices:
                        if dev_info['path'] == self.device_path:
                            continue  # Skip the already-added device

                        should_add = False
                        if not has_keyboard and dev_info['has_keyboard']:
                            should_add = True
                            print(f"Adding keyboard device: {dev_info['name']} ({dev_info['path']})")
                        elif not has_mouse and dev_info['has_mouse']:
                            should_add = True
                            print(f"Adding mouse device: {dev_info['name']} ({dev_info['path']})")
                        elif not has_wheel and dev_info['has_wheel']:
                            should_add = True
                            print(f"Adding wheel device: {dev_info['name']} ({dev_info['path']})")

                        if should_add:
                            try:
                                additional_dev = InputDevice(dev_info['path'])
                                try:
                                    additional_dev.grab()
                                except OSError as ex:
                                    print(f"⚠️ Could not grab {dev_info['path']}: {ex}")
                                _set_nonblocking(additional_dev, True)
                                self.input_devices.append(additional_dev)
                                print(f"Adding device: {dev_info['name']} ({dev_info['path']})")
                                # Update capabilities flags
                                if dev_info['has_keyboard']:
                                    has_keyboard = True
                                if dev_info['has_mouse']:
                                    has_mouse = True
                                if dev_info['has_wheel']:
                                    has_wheel = True
                            except Exception as ex:
                                print(f"Could not add device {dev_info['path']}: {ex}")
            else:
                # Auto-detect and use all relevant devices
                available_devices = self.find_input_devices()
                if not available_devices:
                    print("No suitable input devices found.")
                    return False

                # Add devices that have keyboard, mouse, or wheel capabilities
                for dev_info in available_devices:
                    if dev_info['has_keyboard'] or dev_info['has_mouse'] or dev_info['has_wheel']:
                        try:
                            device = dev_info['device']
                            try:
                                device.grab()
                            except OSError as ex:
                                print(f"⚠️ Could not grab {dev_info['path']}: {ex}")
                            _set_nonblocking(device, True)
                            self.input_devices.append(device)
                            print(f"Using device: {device.name} ({dev_info['path']})")
                        except Exception as ex:
                            print(f"Could not add device {dev_info['path']}: {ex}")

            if not self.input_devices:
                print("No input devices could be opened.")
                return False

            # Create virtual keyboard with all needed keys
            key_union = set([
                e.KEY_A, e.KEY_D, self.space_key,
                self.key_left, self.key_right
            ])

            for maybe in (self.key_pause, self.key_speed, self.key_slow, self.key_wheel_t):
                if maybe:
                    key_union.add(maybe)

            # Add ALL keyboard keys for passthrough (like socd.py does)
            for key_code in range(1, 248):  # All standard keyboard keys
                key_union.add(key_code)

            self.vkb = UInput({e.EV_KEY: sorted(key_union)}, name=self.cfg["VKB_NAME"])

            # Create virtual mouse with all capabilities
            self.vmouse = UInput({
                e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_SIDE, e.BTN_EXTRA, e.BTN_FORWARD, e.BTN_BACK],
                e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_HWHEEL]
            }, name=self.cfg["VMOUSE_NAME"])

            return True

        except Exception as ex:
            print(f"Error opening devices: {ex}")
            return False

    def log(self, msg, kind="info"):
        lvl = (self.cfg.get("LOG_LEVEL") or "minimal").lower()
        if lvl == "none":
            return
        if lvl == "minimal" and kind not in ("restart", "stage", "notice", "warn", "error"):
            return
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def tick(self, msg):
        if not self.cfg.get("LOG_TICKS", False):
            return
        if (self.cfg.get("LOG_LEVEL") or "minimal").lower() == "none":
            return
        self.log(msg, "tick")

    def speedline(self, current_speed):
        interval = float(self.cfg.get("LOG_SPEEDLINE_INTERVAL_S", 0.25))
        now = time.perf_counter()
        if interval > 0 and (now - self._last_speedline) < interval:
            return
        self._last_speedline = now
        sys.stdout.write(f"\r⚡ Base Speed = {current_speed:.0f}px/s   ")
        sys.stdout.flush()

    # --- virtual helpers
    def _vk_down(self, code):
        self.vkb.write(e.EV_KEY, code, 1)
        self.vkb.syn()

    def _vk_up(self, code):
        self.vkb.write(e.EV_KEY, code, 0)
        self.vkb.syn()

    def _emit_rel_x(self, dx: int):
        if dx:
            self.vmouse.write(e.EV_REL, e.REL_X, -dx if self.cfg["INVERT_X"] else dx)
            self.vmouse.syn()

    def _press_and_hold(self, code: int):
        if self.held_key_code == code:
            return
        if self.held_key_code is not None:
            self._vk_up(self.held_key_code)
        self._vk_down(code)
        self.held_key_code = code
        self.move_delay_until = time.perf_counter() + self.cfg["START_MOVE_DELAY_S"]

    def _release_hold(self):
        if self.held_key_code is not None:
            self._vk_up(self.held_key_code)
            self.held_key_code = None

    # --- mode (FIXED DIRECTION MAPPING)
    def _resolve_mode(self):
        if self.a_down and self.d_down:
            return 'left' if self.last_pressed == 'A' else 'right'  # A->left, D->right
        if self.a_down:
            return 'left'   # A key moves LEFT
        if self.d_down:
            return 'right'  # D key moves RIGHT
        return None

    def _apply_mode(self, new_mode):
        if new_mode == self.mode:
            return
        self.mode = new_mode
        if new_mode == 'left':
            self._press_and_hold(e.KEY_A)  # Moving left, hold A
        elif new_mode == 'right':
            self._press_and_hold(e.KEY_D)  # Moving right, hold D
        else:
            self._release_hold()
            self.vel = 0.0

    # --- wheel adjust
    def _stop_motion_only(self, paused: bool):
        self.mouse_paused = paused
        if paused:
            self.vel = 0.0

    def _toggle_wheel_adjust(self):
        self.wheel_adjust_mode = not self.wheel_adjust_mode
        if self.cfg.get("LOG_RESTARTS", True):
            self.log(f"Wheel-adjust: {'ON' if self.wheel_adjust_mode else 'OFF'}", "notice")
        self.speedline(self.current_speed)

    def _bump_speed(self, steps: int):
        if steps == 0:
            return
        old_speed = self.current_speed
        self.current_speed = clamp(
            self.current_speed + steps * self.cfg["SCROLL_SPEED_STEP"],
            self.cfg["MIN_SPEED_PX_PER_SEC"],
            self.cfg["MAX_SPEED_PX_PER_SEC"]
        )

        # If space is not active, update the original speed so it doesn't get overwritten on next space release
        if not self.space_down:
            self.space_original_speed = self.current_speed

        if self.cfg.get("LOG_LEVEL", "minimal").lower() in ("verbose", "debug"):
            self.log(f"Speed changed: {old_speed:.0f} -> {self.current_speed:.0f} (steps: {steps})", "info")
        self.speedline(self.current_speed)

    # --- SPACE ramp
    def _space_reset(self):
        self.seg_idx = -1
        self.seg_start_t = 0.0
        self.seg_end_t = 0.0
        self.seg_start_speed = 0.0
        self.seg_target = None
        self.seg_ticks_total = 0
        self.seg_tick_idx = 0
        self.next_tick_time = 0.0

    def _space_start(self):
        if not self.space_sched:
            return
        now = time.perf_counter()
        self.space_press_t = now
        self.space_down = True

        # Save the original speed before starting the ramp
        if not hasattr(self, 'space_original_speed') or self.space_original_speed == 0.0:
            self.space_original_speed = float(self.current_speed)

        self._space_reset()

        t0, s0 = self.space_sched[0]
        if t0 <= 1e-6:
            tgt = s0 if (self.space_allow_up or s0 <= self.current_speed) else self.current_speed
            self.current_speed = clamp(tgt, self.cfg["MIN_SPEED_PX_PER_SEC"], self.cfg["MAX_SPEED_PX_PER_SEC"])
            self.seg_idx = 0
        else:
            self.seg_idx = -1

        if self.cfg.get("LOG_RESTARTS", True):
            self.log(f"🔽 SPACE ramp restarted (original speed: {self.space_original_speed:.0f})", "restart")

        self._space_prepare_segment(now)
        self.speedline(self.current_speed)

    def _space_stop(self):
        if self.space_down and self.cfg.get("LOG_RESTARTS", True):
            self.log(f"ℹ️ SPACE ramp stopped, restoring speed to {self.space_original_speed:.0f}", "restart")

        self.space_down = False

        # Restore the original speed
        if hasattr(self, 'space_original_speed') and self.space_original_speed > 0.0:
            self.current_speed = clamp(self.space_original_speed, self.cfg["MIN_SPEED_PX_PER_SEC"], self.cfg["MAX_SPEED_PX_PER_SEC"])
            self.speedline(self.current_speed)
            self.space_original_speed = 0.0  # Reset for next time

        self._space_reset()

    def _space_prepare_segment(self, now: float):
        next_ix = self.seg_idx + 1
        if next_ix >= len(self.space_sched):
            self.seg_target = None
            return

        stage_rel_t, stage_target = self.space_sched[next_ix]
        stage_abs_start = self.space_press_t + stage_rel_t

        if now < stage_abs_start:
            self.seg_start_t = self.seg_end_t = stage_abs_start
            self.seg_target = ("__WAIT__", stage_abs_start)
            self.next_tick_time = stage_abs_start
            return

        if next_ix + 1 < len(self.space_sched):
            next_rel_t, _ = self.space_sched[next_ix + 1]
            segment_end = self.space_press_t + next_rel_t
        else:
            segment_end = now + self.space_tick_s

        if not self.space_allow_up and stage_target > self.current_speed:
            self.seg_idx = next_ix
            return self._space_prepare_segment(now)

        self.seg_idx = next_ix
        self.seg_start_t = stage_abs_start
        self.seg_end_t = segment_end
        self.seg_start_speed = float(self.current_speed)
        self.seg_target = float(stage_target)

        total_dur = max(0.0, self.seg_end_t - self.seg_start_t)
        self.seg_ticks_total = max(1, int(math.floor(total_dur / max(self.space_tick_s, 1e-6))))

        if now <= self.seg_start_t:
            self.seg_tick_idx = 0
            self.next_tick_time = self.seg_start_t + self.space_tick_s
        else:
            elapsed = now - self.seg_start_t
            already = int(math.floor(elapsed / max(self.space_tick_s, 1e-6)))
            self.seg_tick_idx = min(already, self.seg_ticks_total)
            self.next_tick_time = self.seg_start_t + (self.seg_tick_idx + 1) * self.space_tick_s

        if self.cfg.get("LOG_STAGES", True):
            self.log(f"▶️ Stage {self.seg_idx}: target={self.seg_target:.0f}, ticks={self.seg_ticks_total}", "stage")

        if not self.space_allow_up and self.seg_start_speed <= self.seg_target + 1e-9:
            if self.cfg.get("LOG_STAGES", True):
                self.log("   (at/below target, skipping)", "stage")
            return self._space_prepare_segment(now)

    def _space_tick(self, now: float):
        if not self.space_down:
            return

        if isinstance(self.seg_target, tuple) and self.seg_target and self.seg_target[0] == "__WAIT__":
            if now >= self.seg_target[1]:
                self._space_prepare_segment(now)
            return

        if self.seg_target is None and (self.seg_idx + 1) < len(self.space_sched):
            self._space_prepare_segment(now)
            return

        while (self.seg_target is not None and not isinstance(self.seg_target, tuple)
               and self.seg_tick_idx < self.seg_ticks_total and now >= self.next_tick_time):

            start = self.seg_start_speed
            target = self.seg_target

            if not self.space_allow_up:
                total_drop = max(0.0, start - target)
                step = total_drop / self.seg_ticks_total
                new_speed = start - step * (self.seg_tick_idx + 1)
                if new_speed < target:
                    new_speed = target
            else:
                total_delta = (target - start)
                step = total_delta / self.seg_ticks_total
                new_speed = start + step * (self.seg_tick_idx + 1)
                if self.seg_tick_idx + 1 == self.seg_ticks_total:
                    new_speed = target

            self.current_speed = clamp(new_speed, self.cfg["MIN_SPEED_PX_PER_SEC"], self.cfg["MAX_SPEED_PX_PER_SEC"])
            self.speedline(self.current_speed)

            if self.cfg.get("LOG_TICKS", False):
                self.tick(f"tick {self.seg_tick_idx + 1}/{self.seg_ticks_total}: {self.current_speed:.0f}")

            self.seg_tick_idx += 1
            self.next_tick_time += self.space_tick_s

        if self.seg_target is not None and not isinstance(self.seg_target, tuple) and self.seg_tick_idx >= self.seg_ticks_total:
            self.current_speed = clamp(float(self.seg_target), self.cfg["MIN_SPEED_PX_PER_SEC"], self.cfg["MAX_SPEED_PX_PER_SEC"])
            self.speedline(self.current_speed)

            if self.cfg.get("LOG_STAGES", True):
                self.log(f"   stage reached: {self.current_speed:.0f}", "stage")

            self._space_prepare_segment(now)

    def _handle_event(self, ev):
        # Pass through non-key events as-is (like socd.py does)
        if ev.type != e.EV_KEY and ev.type != e.EV_REL:
            # Pass through other events
            self.vmouse.write(ev.type, ev.code, ev.value)
            self.vmouse.syn()
            return

        # Handle mouse wheel events
        if ev.type == e.EV_REL and self.wheel_adjust_mode:
            if ev.code == e.REL_WHEEL:
                steps = int(ev.value)
                if steps != 0:
                    self._bump_speed(steps)
                    return  # Don't pass through wheel events when in adjust mode
            elif hasattr(e, "REL_WHEEL_HI_RES") and ev.code == e.REL_WHEEL_HI_RES:
                raw = int(ev.value)
                if raw != 0:
                    self._bump_speed(sgn(raw) * max(1, abs(raw) // 120))
                    return  # Don't pass through wheel events when in adjust mode
            # Pass through other mouse events
            self.vmouse.write(ev.type, ev.code, ev.value)
            self.vmouse.syn()
            return
        elif ev.type == e.EV_REL:
            # Pass through mouse movement when not in wheel adjust mode
            self.vmouse.write(ev.type, ev.code, ev.value)
            self.vmouse.syn()
            return

        # Handle EV_KEY events
        if ev.type != e.EV_KEY:
            return

        code, val = ev.code, ev.value

        # Special mouse button handling
        if code == self.stop_btn:
            if val == 1:
                self._stop_motion_only(True)
            elif val == 0:
                self._stop_motion_only(False)
            # Don't pass through the stop button
            return

        # Handle managed keys - return early to prevent passthrough
        if self.key_wheel_t and code == self.key_wheel_t:
            if val == 1:
                self._toggle_wheel_adjust()
            # Pass through F9 key
            self.vkb.write(e.EV_KEY, code, val)
            self.vkb.syn()
            return

        if code == self.space_key:
            if val in (1, 2):
                if self.cfg["SPACE_RESTART_ON_PRESS"] or not self.space_down:
                    self._space_start()
            elif val == 0 and self.cfg["SPACE_STOP_ON_RELEASE"]:
                self._space_stop()

            if self.cfg["SPACE_MIRROR_TO_GAME"]:
                self.vkb.write(e.EV_KEY, self.space_key, val)
                self.vkb.syn()
            return

        if code == self.key_left:  # A key
            if val == 1:
                self.a_down = True
                self.last_pressed = 'A'
            elif val == 0:
                self.a_down = False
            self._apply_mode(self._resolve_mode())
            # Don't pass through A/D keys - they're transformed to movement
            return

        if code == self.key_right:  # D key
            if val == 1:
                self.d_down = True
                self.last_pressed = 'D'
            elif val == 0:
                self.d_down = False
            self._apply_mode(self._resolve_mode())
            # Don't pass through A/D keys - they're transformed to movement
            return

        if self.key_pause and code == self.key_pause:
            if val == 1:
                self.a_down = False
                self.d_down = False
                self.last_pressed = None
                self._apply_mode(None)
            # Pass through ESC key
            self.vkb.write(e.EV_KEY, self.key_pause, val)
            self.vkb.syn()
            return

        if self.key_speed and code == self.key_speed:
            self.speedup = (val in (1, 2))
            # Pass through CTRL key
            self.vkb.write(e.EV_KEY, code, val)
            self.vkb.syn()
            return

        if self.key_slow and code == self.key_slow:
            self.slowdown = (val in (1, 2))
            # Pass through SHIFT key
            self.vkb.write(e.EV_KEY, code, val)
            self.vkb.syn()
            return

        # FALLBACK: Pass through any unhandled keys/buttons
        # Mouse buttons go to vmouse, keyboard keys go to vkb
        if code >= e.BTN_MISC and code <= e.BTN_GEAR_UP:  # Mouse button range
            self.vmouse.write(e.EV_KEY, code, val)
            self.vmouse.syn()
        else:
            # Keyboard keys
            self.vkb.write(e.EV_KEY, code, val)
            self.vkb.syn()

    def _move_loop(self):
        last = time.perf_counter()
        carry = 0.0

        print(f"🎮 Strafer running with {len(self.input_devices)} input devices")
        for i, dev in enumerate(self.input_devices):
            print(f"  {i+1}. {dev.name} ({dev.path})")
        self.log(f"Base speed: {self.current_speed:.0f}px/s", "notice")
        self.log(f"Wheel adjust: {'ON' if self.wheel_adjust_mode else 'OFF'}", "notice")

        while self.running:
            now = time.perf_counter()
            dt = now - last

            if dt < self.cfg["MIN_FRAME_TIME"]:
                time.sleep(self.cfg["MIN_FRAME_TIME"] - dt)
                continue

            last = now
            dt = max(dt, self.cfg["MIN_FRAME_TIME"])

            # Process inputs from all devices
            for device in self.input_devices:
                try:
                    ev = device.read_one()
                    while ev:
                        self._handle_event(ev)
                        ev = device.read_one()
                except Exception as ex:
                    if self.running:
                        print(f"Error reading events from {device.path}: {ex}")

            # Space timing updates
            self._space_tick(now)

            if now < self.move_delay_until:
                continue

            if self.mouse_paused:
                self.vel = 0.0
                continue

            # MOVEMENT CALCULATION (FIXED DIRECTIONS)
            desired = 0.0
            if self.mode == 'left':
                desired = +self.current_speed  # Left = negative
            elif self.mode == 'right':
                desired = -self.current_speed  # Right = positive

            if desired != 0.0:
                if self.speedup:
                    desired *= self.cfg["SPEEDUP_MULTIPLIER"]
                if self.slowdown:
                    desired *= self.cfg["SLOWDOWN_MULTIPLIER"]

            tc = self.cfg["ACCEL_TIME_S"] if abs(desired) > abs(self.vel) else self.cfg["DECEL_TIME_S"]
            alpha = 1 - math.exp(-dt / max(tc, 1e-4))
            alpha = EASINGS.get(self.cfg["EASING"], ease_exp_in_out)(alpha)
            self.vel += (desired - self.vel) * alpha

            if desired == 0 and abs(self.vel) <= self.cfg["DEADZONE_VEL_PX_S"]:
                self.vel = 0.0
                carry = 0.0
                continue

            delta = self.vel * dt + carry
            if self.cfg["HUMANIZE_NOISE"] and self.cfg["NOISE_PER_STEP_PX"] > 0 and desired != 0.0:
                delta += random.uniform(-self.cfg["NOISE_PER_STEP_PX"], self.cfg["NOISE_PER_STEP_PX"])

            delta = clamp(delta, -int(self.cfg["MAX_STEP_PX"]), int(self.cfg["MAX_STEP_PX"]))
            step = int(round(delta))
            carry = delta - step

            if step:
                self._emit_rel_x(step)

    def start(self):
        if not self.open_devices():
            return False

        self.running = True
        self.move_thread = threading.Thread(target=self._move_loop, daemon=True)
        self.move_thread.start()
        return True

    def stop(self):
        self.running = False
        if hasattr(self, 'move_thread') and self.move_thread.is_alive():
            self.move_thread.join(timeout=2)

        # Clean up and release resources
        for device in self.input_devices:
            try:
                device.ungrab()
            except:
                pass
            try:
                device.close()
            except:
                pass

        if hasattr(self, 'vkb'):
            try:
                self.vkb.close()
            except:
                pass

        if hasattr(self, 'vmouse'):
            try:
                self.vmouse.close()
            except:
                pass

        print("Strafer stopped")
        return True

def get_button_code(button_name: str) -> int:
    """Convert button name to evdev code"""
    button_map = {
        'left': e.BTN_LEFT,
        'right': e.BTN_RIGHT,
        'middle': e.BTN_MIDDLE,
        'side': e.BTN_SIDE,
        'extra': e.BTN_EXTRA,
        'forward': e.BTN_FORWARD,
        'back': e.BTN_BACK,
    }

    if not button_name:
        return e.BTN_EXTRA  # Default

    button_name = button_name.lower().strip()
    if button_name in button_map:
        return button_map[button_name]

    # Try to parse as integer
    try:
        return int(button_name)
    except ValueError:
        # Try as KEY_X
        try:
            if button_name.startswith('key_'):
                return getattr(e, button_name.upper())
            elif not button_name.startswith('btn_'):
                return getattr(e, f"KEY_{button_name.upper()}")
            else:
                return getattr(e, button_name.upper())
        except AttributeError:
            raise ValueError(f"Unknown button: {button_name}")

def main():
    parser = argparse.ArgumentParser(description='Auto Strafer - Compatible with Macro Manager')
    parser.add_argument('--device', '-d', help='Input device path (e.g., /dev/input/event2)')
    parser.add_argument('--config', '-c', help='Path to config file')

    # Optional arguments for autoclicker compatibility
    parser.add_argument('--cps', type=float, help='Base speed multiplier')
    parser.add_argument('--duration', type=float, help='Alternative for decel_time')
    parser.add_argument('--trigger', help='Trigger button name')
    parser.add_argument('--target', help='Target button name')

    args = parser.parse_args()

    # Set config path
    config_path = args.config
    if not config_path:
        home = os.path.expanduser("~")
        config_dir = os.path.join(home, "macro-manager", "configs")
        config_path = os.path.join(config_dir, "strafer.json")

    # Handle device selection - always use auto-detection unless device is specified
    device_path = args.device
    if not device_path:
        print("Welcome to Auto Strafer")
        print("Auto-detecting input devices...")
        device_path = None  # Will trigger auto-detection

    # Create strafer instance
    strafer = StraferMacro(device_path=device_path, config_path=config_path)

    # Apply command line overrides if provided
    if args.cps:
        strafer.cfg["SPEED_PX_PER_SEC_DEFAULT"] = args.cps * 100  # Scale factor

    if args.duration:
        strafer.cfg["DECEL_TIME_S"] = args.duration

    if args.trigger:
        try:
            button_code = get_button_code(args.trigger)
            strafer.cfg["STOP_MOUSE_BUTTON"] = args.trigger.upper() if args.trigger.startswith('BTN_') else f"BTN_{args.trigger.upper()}"
        except:
            print(f"Warning: Unknown trigger button '{args.trigger}', using default")

    if args.target:
        try:
            button_code = get_button_code(args.target)
            strafer.cfg["LEFT_PHYS_KEY_NAME"] = args.target.upper() if args.target.startswith('KEY_') else f"KEY_{args.target.upper()}"
        except:
            print(f"Warning: Unknown target button '{args.target}', using default")

    try:
        if strafer.start():
            # Keep running until interrupted
            while strafer.running:
                time.sleep(0.5)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    finally:
        strafer.stop()

if __name__ == "__main__":
    main()
