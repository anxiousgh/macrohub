#!/usr/bin/env python3
import os
import sys
import time
import threading
import select
import signal
import argparse
from evdev import InputDevice, UInput, ecodes as e
from typing import Optional

class AutoClicker:
    def __init__(self, device_path: str, cps: float = 25.0, click_duration: float = 0.001, 
                 trigger_button: int = e.BTN_EXTRA, target_button: int = e.BTN_LEFT):
        self.device_path = device_path
        self.cps = cps
        self.click_duration = click_duration
        self.trigger_button = trigger_button
        self.target_button = target_button
        self.interval = 1.0 / cps
        
        self.running = True
        self.active = threading.Event()
        self.click_thread: Optional[threading.Thread] = None
        self.mouse: Optional[InputDevice] = None
        self.ui: Optional[UInput] = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)
    
    def click_loop(self):
        """Main clicking loop that runs in separate thread"""
        print(f"Auto-click thread started at {self.cps} CPS")
        next_time = time.perf_counter()
        
        while self.running:
            if not self.active.is_set():
                time.sleep(0.05)
                next_time = time.perf_counter()
                continue
                
            now = time.perf_counter()
            if now >= next_time:
                try:
                    self.ui.write(e.EV_KEY, self.target_button, 1)
                    self.ui.syn()
                    time.sleep(self.click_duration)
                    self.ui.write(e.EV_KEY, self.target_button, 0)
                    self.ui.syn()
                    next_time = now + self.interval
                except Exception as ex:
                    print(f"Click error: {ex}")
                    break
            else:
                time.sleep(0.001)
        
        print("Click thread stopped")
    
    def start(self):
        """Initialize and start the autoclicker"""
        try:
            # Open input device
            if not os.path.exists(self.device_path):
                raise Exception(f"Device not found: {self.device_path}")
            
            self.mouse = InputDevice(self.device_path)
            print(f"Opened device: {self.mouse.name}")
            
            # Create virtual output device
            self.ui = UInput({e.EV_KEY: [self.target_button]}, name='autoclicker-macro')
            print("Created virtual output device")
            
            # Start clicking thread
            self.click_thread = threading.Thread(target=self.click_loop, daemon=True)
            self.click_thread.start()
            
            print(f"AutoClicker ready! Hold trigger button (code {self.trigger_button}) to auto-click")
            print(f"Target button: {self.target_button} at {self.cps} CPS")
            
            # Main event loop
            self.run_event_loop()
            
        except PermissionError:
            print("Permission denied. You may need to add your user to the 'input' group:")
            print("sudo usermod -a -G input $USER")
            print("Then log out and back in.")
            sys.exit(1)
        except Exception as ex:
            print(f"Error starting autoclicker: {ex}")
            sys.exit(1)
    
    def run_event_loop(self):
        """Main event loop listening for trigger button"""
        try:
            while self.running:
                r, _, _ = select.select([self.mouse.fd], [], [], 0.1)
                if r and self.running:
                    try:
                        for event in self.mouse.read():
                            if event.type == e.EV_KEY and event.code == self.trigger_button:
                                if event.value == 1:  # Button pressed
                                    self.active.set()
                                    print("Auto-clicking activated")
                                elif event.value == 0:  # Button released
                                    self.active.clear()
                                    print("Auto-clicking deactivated")
                    except OSError:
                        # Device disconnected
                        print("Input device disconnected")
                        break
        except KeyboardInterrupt:
            pass
    
    def stop(self):
        """Stop the autoclicker gracefully"""
        print("Stopping autoclicker...")
        self.running = False
        self.active.clear()
        
        if self.click_thread and self.click_thread.is_alive():
            self.click_thread.join(timeout=2)
        
        if self.ui:
            self.ui.close()
            self.ui = None
        
        if self.mouse:
            self.mouse.close()
            self.mouse = None
        
        print("Autoclicker stopped")

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
    
    button_name = button_name.lower().strip()
    if button_name in button_map:
        return button_map[button_name]
    
    # Try to parse as integer
    try:
        return int(button_name)
    except ValueError:
        raise ValueError(f"Unknown button: {button_name}")

def main():
    parser = argparse.ArgumentParser(description='AutoClicker - Hold trigger button to auto-click')
    parser.add_argument('--device', '-d', required=True, 
                       help='Input device path (e.g., /dev/input/event2)')
    parser.add_argument('--cps', '-c', type=float, default=25.0,
                       help='Clicks per second (default: 25.0)')
    parser.add_argument('--duration', type=float, default=0.001,
                       help='Click duration in seconds (default: 0.001)')
    parser.add_argument('--trigger', '-t', default='extra',
                       help='Trigger button (default: extra)')
    parser.add_argument('--target', default='left',
                       help='Target button to click (default: left)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    
    args = parser.parse_args()
    
    if not args.verbose:
        # Suppress some output for GUI mode
        pass
    
    try:
        trigger_code = get_button_code(args.trigger)
        target_code = get_button_code(args.target)
        
        clicker = AutoClicker(
            device_path=args.device,
            cps=args.cps,
            click_duration=args.duration,
            trigger_button=trigger_code,
            target_button=target_code
        )
        
        clicker.start()
        
    except KeyboardInterrupt:
        print("\nShutdown requested")
    except Exception as ex:
        print(f"Error: {ex}")
        sys.exit(1)

if __name__ == '__main__':
    main()
