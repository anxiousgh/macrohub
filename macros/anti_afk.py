#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Anti-AFK - compatible with Macro Manager GUI
# Commands:
#   K: toggle anti-afk (configurable)
#   Sends periodic clicks to prevent disconnection

import os, sys, json, time, threading, select, signal, glob, argparse, errno, fcntl
from typing import Optional, Dict, List, Tuple, Any
from evdev import InputDevice, UInput, ecodes as e

def _set_nonblocking(dev: InputDevice, enable: bool = True):
    try:
        if hasattr(dev, "set_nonblocking"): 
            dev.set_nonblocking(enable)
            return
    except: 
        pass
    try:
        flags = fcntl.fcntl(dev.fd, fcntl.F_GETFL)
        fcntl.fcntl(dev.fd, fcntl.F_SETFL, (flags | os.O_NONBLOCK) if enable else (flags & ~os.O_NONBLOCK))
    except Exception as ex:
        print(f"⚠️ could not set nonblocking on {getattr(dev,'path','?')}: {ex}")

class AntiAfkMacro:
    def __init__(self, device_path: str = None, config_path=None):
        self.config_path = config_path
        self.device_path = device_path
        self.running = True

        # Default config - will be overridden by loaded config
        self.cfg = {
            "CLICKS_PER_SECOND": 0.5,  # Once every 2 seconds by default (slow anti-afk)
            "CLICK_DURATION_SECONDS": 0.001,
            "TRIGGER_KEY_NAME": "KEY_K",
            "TARGET_BUTTON": "BTN_LEFT",
            "VERBOSE": False,
            "VMOUSE_NAME": "anti-afk-mouse",
            "VKB_NAME": "anti-afk-kb",
            "LOG_LEVEL": "minimal",
            "LOG_CLICKS": True,
            "LOG_TOGGLES": True,
            "MIN_FRAME_TIME": 0.01,
            "START_DELAY_S": 0.5,
            "AUTO_DETECT_DEVICES": True
        }

        # State variables
        self.is_clicking_active = False
        self.click_worker_thread = None
        self.move_delay_until = 0.0

        # Input/output devices
        self.input_devices = []
        self.vkb = None
        self.vmouse = None
        self.move_thread = None

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

        # Load config
        self.load_config()

        # Key codes
        self.trigger_key = getattr(e, self.cfg["TRIGGER_KEY_NAME"])
        self.target_button = getattr(e, self.cfg["TARGET_BUTTON"])

        # Calculate click interval
        self.click_interval = 1.0 / max(0.01, float(self.cfg["CLICKS_PER_SECOND"]))

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

                    device_info = {
                        'path': path,
                        'name': device.name,
                        'device': device,
                        'has_mouse': has_mouse,
                        'has_keyboard': has_keyboard
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
                            except Exception as ex:
                                print(f"Could not add device {dev_info['path']}: {ex}")
            else:
                # Auto-detect and use all relevant devices
                available_devices = self.find_input_devices()
                if not available_devices:
                    print("No suitable input devices found.")
                    return False

                # Add devices that have keyboard or mouse capabilities
                for dev_info in available_devices:
                    if dev_info['has_keyboard'] or dev_info['has_mouse']:
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

            # Create virtual keyboard with needed keys
            key_union = set([self.trigger_key])
            
            # Add ALL keyboard keys for passthrough
            for key_code in range(1, 248):  # All standard keyboard keys
                key_union.add(key_code)

            self.vkb = UInput({e.EV_KEY: sorted(key_union)}, name=self.cfg["VKB_NAME"])

            # Create virtual mouse
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
        if lvl == "minimal" and kind not in ("click", "toggle", "notice", "warn", "error"):
            return
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _perform_single_click(self):
        """Perform a single click to prevent disconnect"""
        try:
            # Press down
            self.vmouse.write(e.EV_KEY, self.target_button, 1)
            self.vmouse.syn()

            # Hold for exact duration
            time.sleep(float(self.cfg["CLICK_DURATION_SECONDS"]))

            # Release
            self.vmouse.write(e.EV_KEY, self.target_button, 0)
            self.vmouse.syn()

            if self.cfg.get("LOG_CLICKS", True):
                self.log("💡 Anti-AFK click sent", "click")

        except Exception as error:
            self.log(f"❌ Failed to perform anti-AFK click: {error}", "error")

    def _clicking_worker(self):
        """Worker that performs anti-AFK clicks"""
        self.log(f"🔄 Anti-AFK worker started (clicking every {self.click_interval:.1f} seconds)", "notice")

        next_click_time = time.perf_counter()

        while self.running:
            if not self.is_clicking_active:
                time.sleep(0.1)
                next_click_time = time.perf_counter()
                continue

            current_time = time.perf_counter()

            if current_time >= next_click_time:
                # Perform anti-AFK click
                self._perform_single_click()
                next_click_time = current_time + self.click_interval
            else:
                # Sleep until next click needed
                time.sleep(min(0.1, next_click_time - current_time))

    def start_clicking(self):
        """Start the anti-AFK clicking"""
        if not self.is_clicking_active:
            self.is_clicking_active = True
            if self.cfg.get("LOG_TOGGLES", True):
                self.log("🟢 Anti-AFK ACTIVATED", "toggle")

        if not (self.click_worker_thread and self.click_worker_thread.is_alive()):
            self.click_worker_thread = threading.Thread(
                target=self._clicking_worker,
                name="AntiAfkWorker",
                daemon=True
            )
            self.click_worker_thread.start()

    def stop_clicking(self):
        """Stop the anti-AFK clicking"""
        if self.is_clicking_active:
            self.is_clicking_active = False
            if self.cfg.get("LOG_TOGGLES", True):
                self.log("🔴 Anti-AFK DEACTIVATED", "toggle")

    def toggle_clicking(self):
        """Toggle anti-AFK on/off"""
        if self.is_clicking_active:
            self.stop_clicking()
        else:
            self.start_clicking()

    def _handle_event(self, ev):
        # Pass through non-key events
        if ev.type != e.EV_KEY and ev.type != e.EV_REL:
            # Pass through other events
            self.vmouse.write(ev.type, ev.code, ev.value)
            self.vmouse.syn()
            return

        # Handle mouse events
        if ev.type == e.EV_REL:
            # Pass through mouse movement
            self.vmouse.write(ev.type, ev.code, ev.value)
            self.vmouse.syn()
            return

        # Handle EV_KEY events
        if ev.type != e.EV_KEY:
            return

        code, val = ev.code, ev.value

        # Handle trigger key
        if code == self.trigger_key:
            if val == 1:  # Key press (ignore key release)
                self.toggle_clicking()
            # Pass through trigger key
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
        """Main event loop"""
        last = time.perf_counter()
        
        print(f"🎮 Anti-AFK running with {len(self.input_devices)} input devices")
        for i, dev in enumerate(self.input_devices):
            print(f"  {i+1}. {dev.name} ({dev.path})")
        self.log(f"Click interval: {self.click_interval:.1f} seconds", "notice")
        self.log(f"Trigger key: {self.cfg['TRIGGER_KEY_NAME']}", "notice")
        self.log(f"Target button: {self.cfg['TARGET_BUTTON']}", "notice")

        while self.running:
            now = time.perf_counter()
            dt = now - last

            if dt < self.cfg["MIN_FRAME_TIME"]:
                time.sleep(self.cfg["MIN_FRAME_TIME"] - dt)
                continue

            last = now

            if now < self.move_delay_until:
                continue

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

    def start(self):
        if not self.open_devices():
            return False

        self.running = True
        self.move_delay_until = time.perf_counter() + self.cfg["START_DELAY_S"]
        
        # Start the clicking worker
        self.start_clicking()
        
        self.move_thread = threading.Thread(target=self._move_loop, daemon=True)
        self.move_thread.start()
        return True

    def stop(self):
        self.running = False
        self.is_clicking_active = False
        
        if hasattr(self, 'move_thread') and self.move_thread.is_alive():
            self.move_thread.join(timeout=2)

        if self.click_worker_thread and self.click_worker_thread.is_alive():
            self.click_worker_thread.join(timeout=2)

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

        print("Anti-AFK stopped")
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
        return e.BTN_LEFT  # Default

    button_name = button_name.lower().strip()
    if button_name in button_map:
        return button_map[button_name]

    # Try to parse as integer
    try:
        return int(button_name)
    except ValueError:
        # Try as KEY_X or BTN_X
        try:
            if button_name.startswith('key_'):
                return getattr(e, button_name.upper())
            elif not button_name.startswith('btn_'):
                return getattr(e, f"BTN_{button_name.upper()}")
            else:
                return getattr(e, button_name.upper())
        except AttributeError:
            raise ValueError(f"Unknown button: {button_name}")

def get_key_code(key_name: str) -> int:
    """Convert key name to evdev code"""
    if not key_name:
        return e.KEY_K  # Default

    key_name = key_name.upper().strip()
    try:
        if not key_name.startswith('KEY_'):
            key_name = f"KEY_{key_name}"
        return getattr(e, key_name)
    except AttributeError:
        # Try without KEY_ prefix
        try:
            return getattr(e, key_name.replace('KEY_', ''))
        except AttributeError:
            raise ValueError(f"Unknown key: {key_name}")

def main():
    parser = argparse.ArgumentParser(description='Anti-AFK - Compatible with Macro Manager')
    parser.add_argument('--device', '-d', help='Input device path (e.g., /dev/input/event2)')
    parser.add_argument('--config', '-c', help='Path to config file')

    # Optional arguments for compatibility
    parser.add_argument('--cps', type=float, help='Clicks per second')
    parser.add_argument('--duration', type=float, help='Click duration in seconds')
    parser.add_argument('--trigger', help='Trigger key name (e.g., k, space)')
    parser.add_argument('--target', help='Target button name (e.g., left, right)')

    args = parser.parse_args()

    # Set config path
    config_path = args.config
    if not config_path:
        home = os.path.expanduser("~")
        config_dir = os.path.join(home, "macro-manager", "configs")
        config_path = os.path.join(config_dir, "anti-afk.json")

    # Handle device selection - always use auto-detection unless device is specified
    device_path = args.device
    if not device_path:
        print("Welcome to Anti-AFK")
        print("Auto-detecting input devices...")
        device_path = None  # Will trigger auto-detection

    # Create anti-afk instance
    anti_afk = AntiAfkMacro(device_path=device_path, config_path=config_path)

    # Apply command line overrides if provided
    if args.cps:
        anti_afk.cfg["CLICKS_PER_SECOND"] = args.cps
        anti_afk.click_interval = 1.0 / max(0.01, args.cps)

    if args.duration:
        anti_afk.cfg["CLICK_DURATION_SECONDS"] = args.duration

    if args.trigger:
        try:
            key_code = get_key_code(args.trigger)
            anti_afk.cfg["TRIGGER_KEY_NAME"] = f"KEY_{args.trigger.upper()}"
            anti_afk.trigger_key = key_code
        except:
            print(f"Warning: Unknown trigger key '{args.trigger}', using default")

    if args.target:
        try:
            button_code = get_button_code(args.target)
            anti_afk.cfg["TARGET_BUTTON"] = f"BTN_{args.target.upper()}" if not args.target.upper().startswith('BTN_') else args.target.upper()
            anti_afk.target_button = button_code
        except:
            print(f"Warning: Unknown target button '{args.target}', using default")

    try:
        if anti_afk.start():
            # Keep running until interrupted
            while anti_afk.running:
                time.sleep(0.5)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    finally:
        anti_afk.stop()

if __name__ == "__main__":
    main()
