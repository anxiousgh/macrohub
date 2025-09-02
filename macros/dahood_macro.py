#!/usr/bin/env python3
# Auto-Scroll Macro - Compatible with Macro Manager
# Auto-detect MB4 (side/back) from any mouse and trigger the scroll macro.

import evdev
from evdev import InputDevice, UInput, ecodes as e
import threading
import time
import sys
import os
import select
import glob
import argparse
import json
import signal
from typing import Dict, List, Optional, Tuple

class DahoodScrollMacro:
    def __init__(self, device_path: str = None, config_path: str = None):
        self.config_path = config_path
        self.device_path = device_path
        self.running = True

        # Default config - will be overridden by loaded config
        self.cfg = {
            # Timing settings - EXACT scroll values and delays from original script
            "SCROLL_UP_DELAY": 0.0032,      # 3.2ms for up scroll
            "SCROLL_DOWN_DELAY": 0.022,     # 22ms for down scroll
            "SCROLL_UP_VALUE": 1,           # Up scroll amount
            "SCROLL_DOWN_VALUE": -1,        # Down scroll amount
            
            # Trigger button
            "TRIGGER_BUTTON": "BTN_SIDE",   # MB4 (side/back button)
            
            # Virtual device name
            "VIRTUAL_MOUSE_NAME": "optimized-scroll-macro",
            
            # Auto-detection settings
            "AUTO_DETECT_DEVICES": True,
            "VERBOSE": True
        }

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

        # Load config
        self.load_config()

        # State variables
        self.is_scrolling = False
        self.scroll_thread = None
        self.current_scroll_value = self.cfg["SCROLL_UP_VALUE"]  # Start with up
        self.next_scroll_time = 0

        # Input/output devices
        self.devices = {}  # fd -> InputDevice mapping
        self.virtual_mouse = None

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

    def start(self):
        try:
            # Create virtual mouse
            try:
                caps = {e.EV_REL: [e.REL_WHEEL]}
                self.virtual_mouse = UInput(caps, name=self.cfg["VIRTUAL_MOUSE_NAME"])
                print("Created virtual mouse device")
            except PermissionError:
                print("Permission denied! Run with: sudo python3 dahood-macro.py")
                return False

            # Open input devices
            self._open_input_devices()
            
            if not self.devices:
                print("No input devices could be opened.")
                return False

            # Get trigger button code
            self.trigger_button_code = getattr(e, self.cfg["TRIGGER_BUTTON"], e.BTN_SIDE)

            print(f"Hold-to-scroll macro ready (EXACT original timing: {self.cfg['SCROLL_UP_DELAY']*1000:.1f}ms up / {self.cfg['SCROLL_DOWN_DELAY']*1000:.1f}ms down)")
            print(f"Hold {self.cfg['TRIGGER_BUTTON']} to activate scrolling")

            # Start scroll worker thread
            if not (self.scroll_thread and self.scroll_thread.is_alive()):
                self.scroll_thread = threading.Thread(target=self._scroll_worker, daemon=True)
                self.scroll_thread.start()

            # Start main input loop
            self.listen()
            return True

        except Exception as ex:
            print(f"Error starting dahood macro: {ex}")
            return False

    def _open_input_devices(self):
        """Open input devices - either specified device or auto-detect"""
        if self.device_path:
            # Use specified device
            try:
                if not os.path.exists(self.device_path):
                    print(f"Device not found: {self.device_path}")
                    return

                device = InputDevice(self.device_path)
                print(f"Using specified device: {device.name} ({self.device_path})")
                
                self.devices[device.fd] = device
            except Exception as ex:
                print(f"Error opening specified device {self.device_path}: {ex}")
                return
        else:
            # Auto-detect devices
            self._auto_detect_devices()

    def _auto_detect_devices(self):
        """Auto-detect and open all relevant input devices"""
        device_paths = sorted(glob.glob('/dev/input/event*'),
                             key=lambda p: int(p.split('event')[1]) if p.split('event')[1].isdigit() else 9999)

        opened = []
        skipped = []
        
        for path in device_paths:
            try:
                dev = InputDevice(path)
                caps = dev.capabilities()
                
                if e.EV_KEY not in caps:
                    skipped.append((path, dev.name, "no EV_KEY"))
                    dev.close()
                    continue

                # Check if it has mouse-like capabilities
                has_mousey = any(code in caps.get(e.EV_KEY, [])
                               for code in (e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_SIDE, e.BTN_EXTRA))
                has_rel = e.EV_REL in caps and any(c in caps[e.EV_REL] for c in (e.REL_X, e.REL_Y, e.REL_WHEEL))

                if not (has_mousey or has_rel):
                    # Still keep it; some devices might report BTN_SIDE anyway
                    pass

                # Don't grab devices to avoid breaking normal mouse usage
                self.devices[dev.fd] = dev
                has_btn_side = self.trigger_button_code in caps.get(e.EV_KEY, [])
                opened.append((path, dev.name, has_btn_side))

            except (PermissionError, OSError):
                continue

        if self.cfg["VERBOSE"]:
            print(f"\nListening to {len(opened)} input devices for {self.cfg['TRIGGER_BUTTON']}:")
            print("=" * 60)
            for path, name, has_btn_side in opened:
                flag = "✅ HAS_TRIGGER" if has_btn_side else "…"
                print(f"{path:18s} | {name[:34]:34s} | {flag}")
            if skipped:
                print("(skipped devices without EV_KEY)")

    def _perform_single_scroll(self):
        """Perform a single scroll action"""
        try:
            self.virtual_mouse.write(e.EV_REL, e.REL_WHEEL, self.current_scroll_value)
            self.virtual_mouse.syn()
        except Exception as error:
            print(f"Scroll error: {error}")

    def _get_current_delay(self) -> float:
        """Get the delay for the current scroll direction"""
        return (self.cfg["SCROLL_UP_DELAY"] if self.current_scroll_value == self.cfg["SCROLL_UP_VALUE"] 
                else self.cfg["SCROLL_DOWN_DELAY"])

    def _toggle_direction(self):
        """Toggle between scroll up and scroll down"""
        self.current_scroll_value = (self.cfg["SCROLL_DOWN_VALUE"]
                                   if self.current_scroll_value == self.cfg["SCROLL_UP_VALUE"]
                                   else self.cfg["SCROLL_UP_VALUE"])

    def _scroll_worker(self):
        """Worker thread that performs the scrolling with exact timing"""
        if self.cfg["VERBOSE"]:
            print("Scroll macro activated (exact timing)")
        
        self.next_scroll_time = time.perf_counter()

        while self.running:
            if not self.is_scrolling:
                time.sleep(0.05)
                self.next_scroll_time = time.perf_counter()
                continue

            current_time = time.perf_counter()
            if current_time >= self.next_scroll_time:
                self._perform_single_scroll()
                delay = self._get_current_delay()
                self._toggle_direction()
                self.next_scroll_time = current_time + delay
            else:
                time.sleep(0.001)

    def start_scrolling(self):
        """Start scrolling"""
        if not self.is_scrolling:
            self.is_scrolling = True
            self.current_scroll_value = self.cfg["SCROLL_UP_VALUE"]

    def stop_scrolling(self):
        """Stop scrolling"""
        self.is_scrolling = False

    def listen(self):
        """Main event loop listening for trigger button"""
        try:
            while self.running:
                if not self.devices:
                    time.sleep(0.2)
                    self._open_input_devices()
                    continue

                fds = list(self.devices.keys())
                try:
                    ready, _, _ = select.select(fds, [], [], 0.02)
                except Exception:
                    # Rebuild device table if something got disconnected
                    self._rebuild_device_table()
                    continue

                for fd in ready:
                    dev = self.devices.get(fd)
                    if not dev:
                        continue
                    try:
                        for event in dev.read():
                            self._handle_event(event)
                    except OSError:
                        # Device was removed; clean it up
                        self._drop_device(fd)
                        continue
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def _handle_event(self, event):
        """Handle input events - only care about the trigger button"""
        if event.type == e.EV_KEY and event.code == self.trigger_button_code:
            if event.value == 1:        # Button press
                if not self.is_scrolling:
                    self.start_scrolling()
            elif event.value == 0:      # Button release
                if self.is_scrolling:
                    self.stop_scrolling()

    def _drop_device(self, fd: int):
        """Remove a device from our tracking"""
        dev = self.devices.pop(fd, None)
        try:
            if dev:
                dev.close()
        except Exception:
            pass

    def _rebuild_device_table(self):
        """Clear dead devices and try reopening"""
        for fd in list(self.devices.keys()):
            try:
                os.fstat(fd)
            except OSError:
                self._drop_device(fd)
        self._auto_detect_devices()

    def stop(self):
        """Stop the macro gracefully"""
        self.running = False
        self.is_scrolling = False

        if hasattr(self, 'scroll_thread') and self.scroll_thread and self.scroll_thread.is_alive():
            self.scroll_thread.join(timeout=2.0)

        self._cleanup_resources()

    def _cleanup_resources(self):
        """Clean up all resources"""
        print("Cleaning up dahood macro resources...")

        for fd, dev in list(self.devices.items()):
            try:
                dev.close()
            except Exception:
                pass
        self.devices.clear()

        if hasattr(self, 'virtual_mouse') and self.virtual_mouse:
            try:
                self.virtual_mouse.close()
            except Exception:
                pass

        print("Dahood macro stopped")

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
        return 'BTN_SIDE'  # Default
    
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
    parser = argparse.ArgumentParser(description='Dahood Auto-Scroll - Compatible with Macro Manager')
    parser.add_argument('--device', '-d', help='Input device path (optional, auto-detects by default)')
    parser.add_argument('--config', '-c', help='Path to config file')
    
    # Optional arguments for compatibility
    parser.add_argument('--up-delay', type=float, help='Up scroll delay in seconds')
    parser.add_argument('--down-delay', type=float, help='Down scroll delay in seconds')
    parser.add_argument('--trigger', help='Trigger button name')

    args = parser.parse_args()

    # Set config path
    config_path = args.config
    if not config_path:
        home = os.path.expanduser("~")
        config_dir = os.path.join(home, "macro-manager", "configs")
        config_path = os.path.join(config_dir, "dahood-macro.json")

    # Create dahood macro instance
    dahood = DahoodScrollMacro(device_path=args.device, config_path=config_path)

    # Apply command line overrides if provided
    if args.up_delay:
        dahood.cfg["SCROLL_UP_DELAY"] = args.up_delay

    if args.down_delay:
        dahood.cfg["SCROLL_DOWN_DELAY"] = args.down_delay

    if args.trigger:
        try:
            button_name = get_button_code(args.trigger)
            dahood.cfg["TRIGGER_BUTTON"] = button_name
        except:
            print(f"Warning: Unknown trigger button '{args.trigger}', using default")

    try:
        if dahood.start():
            # Keep running until interrupted
            while dahood.running:
                time.sleep(0.5)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    finally:
        dahood.stop()

if __name__ == "__main__":
    main()
