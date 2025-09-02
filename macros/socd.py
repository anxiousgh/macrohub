#!/usr/bin/env python3
# SOCD Cleaner - Compatible with Macro Manager
# Simple SOCD / key-combiner with extra modes

import glob, os, select, sys, time, argparse, json, signal, threading
from collections import defaultdict
from typing import List, Dict, Optional
from evdev import InputDevice, UInput, ecodes as e

class SOCDCleaner:
    def __init__(self, device_path: str = None, config_path: str = None):
        self.config_path = config_path
        self.device_path = device_path
        self.running = True

        # Default config
        self.cfg = {
            "AXES": [
                {"name": "horizontal", "keys": ["a", "d"], "mode": "recent"},
                {"name": "vertical", "keys": ["w", "s"], "mode": "recent"},
                {"name": "vertical2", "keys": ["e", "q"], "mode": "recent"}
            ],
            "GRAB_INPUTS": True,
            "VERBOSE": True,
            "VDEV_NAME": "socd-keyboard",
            "AUTO_DETECT_DEVICES": True,
            "DEVICE_PATH": None,
            # Axis mode options
            "AVAILABLE_MODES": ["recent", "first", "neutral", "priority", "combine", "invert", "sticky", "toggle"]
        }

        # Load config
        self.load_config()
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

        # State variables
        self.axes = []
        self.bykey = defaultdict(list)
        self.devs = []
        self.fd2dev = {}
        self.fds = []
        self.ui = None

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

    def key_to_code(self, k):
        if isinstance(k, int): return k
        s = str(k).strip()
        if s.upper().startswith(("KEY_","BTN_")): return getattr(e, s.upper(), None)
        special = {" ": e.KEY_SPACE, "\t": e.KEY_TAB, "\n": e.KEY_ENTER}
        if s in special: return special[s]
        if len(s)==1:
            if "a"<=s<="z": return getattr(e, "KEY_"+s.upper(), None)
            if "0"<=s<="9": return getattr(e, "KEY_"+("0" if s=="0" else s), None)
        try: return int(s)
        except: return None

    def codes_from_list(self, lst):
        out=[]
        for x in lst:
            c=self.key_to_code(x)
            if c is None: 
                print(f"Unknown key in config: {x}")
                continue
            out.append(c)
        if len(out)<2: 
            print("Warning: Axis needs at least 2 keys.")
            return []
        return out

    def looks_keyboard(self, dev: InputDevice):
        caps = dev.capabilities()
        keys = set(caps.get(e.EV_KEY, []))
        if any(e.KEY_A <= k <= e.KEY_Z for k in keys): return True
        base = {e.KEY_ENTER, e.KEY_SPACE, e.KEY_TAB}
        arrows = {e.KEY_LEFT, e.KEY_RIGHT, e.KEY_UP, e.KEY_DOWN}
        return bool(keys & (base|arrows))

    def list_keyboards(self):
        devs=[]
        if self.device_path:
            # Use specified device
            try:
                d = InputDevice(self.device_path)
                if self.looks_keyboard(d):
                    devs.append(d)
                else:
                    print(f"Warning: {self.device_path} doesn't look like a keyboard")
                    devs.append(d)  # Use it anyway
            except Exception as ex:
                print(f"Error opening specified device {self.device_path}: {ex}")
                return []
        else:
            # Auto-detect keyboards
            for p in sorted(glob.glob("/dev/input/event*"), key=lambda s:int(s.split("event")[1])):
                try:
                    d=InputDevice(p)
                    if self.looks_keyboard(d): 
                        devs.append(d)
                    else: 
                        d.close()
                except: 
                    pass
        return devs

    def start(self):
        try:
            # Setup axes
            for ax in self.cfg["AXES"]:
                name=ax.get("name","axis")
                mode=(ax.get("mode","recent")).lower()
                if mode not in self.cfg["AVAILABLE_MODES"]:
                    print(f"Bad mode for {name}: {mode}, using 'recent'")
                    mode = "recent"
                keys=self.codes_from_list(ax["keys"])
                if not keys:
                    continue
                    
                a=Axis(
                    name, keys, mode,
                    priority_names=ax.get("priority"),
                    swap_delay_ms=ax.get("swap_delay_ms"),
                    timeout_neutral_ms=ax.get("timeout_neutral_ms"),
                    parent=self
                )
                self.axes.append(a)
                for k in keys: 
                    self.bykey[k].append(a)

            # Setup devices
            self.devs=self.list_keyboards()
            if not self.devs: 
                print("No keyboards found. Run with sudo?")
                return False
                
            for d in self.devs:
                try:
                    if self.cfg["GRAB_INPUTS"]: 
                        d.grab()
                except Exception as ex:
                    print(f"warn: grab {d.path} failed: {ex}")
                self.fd2dev[d.fd]=d
            self.fds=list(self.fd2dev.keys())

            # uinput caps = union of all keys + our axis keys
            key_union=set()
            for d in self.devs:
                try: 
                    key_union.update(d.capabilities().get(e.EV_KEY, []))
                except: 
                    pass
            for a in self.axes: 
                key_union.update(a.keys)
            ui_caps={e.EV_KEY: sorted(key_union)}
            self.ui=UInput(ui_caps, name=self.cfg["VDEV_NAME"])

            if self.cfg["VERBOSE"]:
                devs=", ".join(f"{d.path}({d.name})" for d in self.devs)
                print("Listening on:", devs)
                for a in self.axes:
                    names=", ".join(self.code_to_name(k) for k in a.keys)
                    extra=""
                    if a.mode=="priority" and a.priority:
                        extra=f" priority=[{', '.join(self.code_to_name(p) for p in a.priority)}]"
                    if a.swap_delay>0:
                        extra += f" swap_delay={int(a.swap_delay*1000)}ms"
                    if a.timeout_neutral>0:
                        extra += f" timeout_neutral={int(a.timeout_neutral*1000)}ms"
                    print(f"  - {a.name}: [{names}] mode={a.mode}{extra}")

            # Start main loop in separate thread
            self.main_thread = threading.Thread(target=self.loop, daemon=True)
            self.main_thread.start()
            return True

        except Exception as ex:
            print(f"Error starting SOCD cleaner: {ex}")
            return False

    def loop(self):
        try:
            while self.running:
                r,_,_=select.select(self.fds,[],[],0.25)
                for fd in r:
                    if not self.running:
                        break
                    dev=self.fd2dev.get(fd)
                    if not dev:
                        continue
                    try:
                        for ev in dev.read():
                            if not self.running:
                                break
                            if ev.type!=e.EV_KEY:
                                # pass through everything non-key as-is
                                if self.ui:
                                    self.ui.write(ev.type, ev.code, ev.value)
                                    self.ui.syn()
                                continue
                            code,val=ev.code,ev.value  # 0 up / 1 down / 2 repeat
                            if code in self.bykey:
                                if val in (0,1):
                                    for ax in self.bykey[code]:
                                        ax.on_key(code, val==1)
                                        desired=ax.pick()
                                        # emit only changes
                                        for k,want in desired.items():
                                            cur=ax.out[k]
                                            if cur!=want:
                                                ax.out[k]=want
                                                if self.ui:
                                                    self.ui.write(e.EV_KEY, k, 1 if want else 0)
                                        if self.ui:
                                            self.ui.syn()
                                # ignore repeats on axis keys
                            else:
                                # non-axis key: mirror including repeats
                                if self.ui:
                                    self.ui.write(e.EV_KEY, code, val)
                                    self.ui.syn()
                    except Exception as ex:
                        if self.running:
                            print(f"Error reading from {dev.path}: {ex}")
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

    def stop(self):
        self.running = False
        if hasattr(self, 'main_thread') and self.main_thread.is_alive():
            self.main_thread.join(timeout=2)
        self._cleanup()

    def _cleanup(self):
        # release any held axis outputs
        if self.ui:
            for ax in self.axes:
                for k,on in ax.out.items():
                    if on: 
                        self.ui.write(e.EV_KEY, k, 0)
            self.ui.syn()
        
        for d in self.devs:
            try: 
                d.ungrab()
            except: 
                pass
            try: 
                d.close()
            except: 
                pass
        try: 
            if self.ui:
                self.ui.close()
        except: 
            pass
        print("SOCD cleaner stopped")

    def code_to_name(self, code:int):
        for k,v in e.__dict__.items():
            if isinstance(v,int) and v==code and (k.startswith("KEY_") or k.startswith("BTN_")):
                return k
        return str(code)


# ---- axis engine with extra modes ----
class Axis:
    def __init__(self, name, keys, mode, priority_names=None, swap_delay_ms=None, timeout_neutral_ms=None, parent=None):
        self.parent = parent
        self.name=name
        self.keys=keys
        self.mode=mode  # "recent" | "first" | "neutral" | "priority" | "combine" | "invert" | "sticky" | "toggle"
        self.down={k:False for k in keys}
        self.out ={k:False for k in keys}
        self.last=None
        self.t0={k:0.0 for k in keys}
        self.priority = self._resolve_priority(priority_names) if priority_names else []
        self.swap_delay = (swap_delay_ms or 0)/1000.0
        self.last_switch_time = 0.0
        self.timeout_neutral = (timeout_neutral_ms or 0)/1000.0
        self.conflict_start = 0.0
        # toggle state (exclusive)
        self.toggle_active: Optional[int] = None

    def _resolve_priority(self, names):
        resolved = []
        for n in names:
            c = self.parent.key_to_code(n) if not isinstance(n, int) else n
            if c is None:
                print(f"Unknown key in priority for {self.name}: {n}")
                continue
            resolved.append(c)
        return resolved

    def on_key(self, code, is_down):
        if code not in self.down:
            return False

        # toggle mode: act on DOWN edges only
        if self.mode == "toggle":
            if is_down:
                if self.toggle_active == code:
                    # toggle off
                    self.toggle_active = None
                else:
                    # set this key, turn others off
                    self.toggle_active = code
                # outputs are derived in pick()
            # ignore ups entirely
            return True

        # normal modes
        self.down[code]=is_down
        now=time.monotonic()
        if is_down:
            self.last=code
            if self.t0[code]==0.0: self.t0[code]=now
        else:
            self.t0[code]=0.0

        # conflict window tracking for timeout_neutral
        if self._pressed_count() >= 2:
            if self.conflict_start == 0.0:
                self.conflict_start = now
        else:
            self.conflict_start = 0.0

        return True

    def _pressed(self):
        return [k for k,v in self.down.items() if v]

    def _pressed_count(self):
        return sum(1 for v in self.down.values() if v)

    def _debounce_ok(self):
        if self.swap_delay <= 0: return True
        now = time.monotonic()
        return (now - self.last_switch_time) >= self.swap_delay

    def _note_switch(self):
        self.last_switch_time = time.monotonic()

    def _timeout_neutral_active(self):
        if self.timeout_neutral <= 0: return False
        if self._pressed_count() < 2: return False
        return (time.monotonic() - self.conflict_start) >= self.timeout_neutral

    def pick(self) -> Dict[int,bool]:
        # combine: mirror all pressed
        if self.mode == "combine":
            pressed = set(self._pressed())
            return {k: (k in pressed) for k in self.keys}

        # toggle: exclusive toggle
        if self.mode == "toggle":
            return {k: (k == self.toggle_active) for k in self.keys}

        pressed = self._pressed()

        # neutral or timeout-neutral
        if self.mode == "neutral" or self._timeout_neutral_active():
            return {k: False for k in self.keys} if len(pressed)>=2 else {k:(k in pressed) for k in self.keys}

        if len(pressed) <= 1:
            # simple mirror
            return {k:(k in pressed) for k in self.keys}

        # sticky: keep current winner until all released
        if self.mode == "sticky":
            current_winner = next((k for k,on in self.out.items() if on), None)
            if current_winner is not None:
                # keep it until nobody is pressed
                if any(self.down.values()):
                    return {k:(k==current_winner) for k in self.keys}
            # if nothing held, fall through to "recent" selection for first time
            # choose using last pressed, but honor debounce
            if not self._debounce_ok():
                return {k:(k==current_winner) for k in self.keys} if current_winner else {k:False for k in self.keys}
            chosen = self.last if self.last in pressed else max(pressed, key=lambda k:self.t0.get(k,0.0))
            self._note_switch()
            return {k:(k==chosen) for k in self.keys}

        # first: earliest currently-held wins
        if self.mode == "first":
            chosen = min(pressed, key=lambda k:self.t0.get(k, 1e9))
            return {k:(k==chosen) for k in self.keys}

        # invert: when 2+ pressed, last loses (so earliest wins)
        if self.mode == "invert":
            if not self._debounce_ok():
                return self.out.copy()
            chosen = min(pressed, key=lambda k:self.t0.get(k, 1e9))
            # only mark switch time if winner changes
            if not self.out.get(chosen, False): self._note_switch()
            return {k:(k==chosen) for k in self.keys}

        # priority
        if self.mode == "priority":
            if not self._debounce_ok():
                return self.out.copy()
            for k in self.priority:
                if k in pressed:
                    if not self.out.get(k, False): self._note_switch()
                    return {x:(x==k) for x in self.keys}
            # fallback to recent
            chosen = self.last if self.last in pressed else max(pressed, key=lambda k:self.t0.get(k,0.0))
            if not self.out.get(chosen, False): self._note_switch()
            return {k:(k==chosen) for k in self.keys}

        # recent (default): last pressed wins
        if not self._debounce_ok():
            return self.out.copy()
        chosen = self.last if self.last in pressed else max(pressed, key=lambda k:self.t0.get(k,0.0))
        if not self.out.get(chosen, False): self._note_switch()
        return {k:(k==chosen) for k in self.keys}


def main():
    parser = argparse.ArgumentParser(description='SOCD Cleaner - Compatible with Macro Manager')
    parser.add_argument('--device', '-d', help='Input device path (optional, auto-detects by default)')
    parser.add_argument('--config', '-c', help='Path to config file')

    args = parser.parse_args()

    # Set config path
    config_path = args.config
    if not config_path:
        home = os.path.expanduser("~")
        config_dir = os.path.join(home, "macro-manager", "configs")
        config_path = os.path.join(config_dir, "socd.json")

    # Create SOCD cleaner instance
    socd = SOCDCleaner(device_path=args.device, config_path=config_path)

    try:
        if socd.start():
            # Keep running until interrupted
            while socd.running:
                time.sleep(0.5)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    finally:
        socd.stop()

if __name__ == "__main__":
    main()
