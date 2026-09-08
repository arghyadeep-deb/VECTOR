# Phone and Device Control

**Purpose:** Phone/ADB/device control  
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR controls phones via ADB and PCs via pyautogui, enabling automation across devices.

**Key Properties:**
- **ADB control** — Android phone automation
- **PC control** — pyautogui automation
- **Screen capture** — screenshot on both devices
- **Input injection** — tap, swipe, type

**Files:**
- `core/control/phone_controller.py`
- `core/control/pc_controller.py`

**Status:** ✅ IMPLEMENTED, production-reachable

---

## Phone Controller

### ADB Integration

**File:** `core/control/phone_controller.py`  
**Status:** ✅ IMPLEMENTED

```python
class PhoneController:
    """Control Android phone via ADB."""
    
    def __init__(self, device_id: str = None):
        self.device_id = device_id
        self._check_adb()
    
    def _check_adb(self):
        """Check ADB connection."""
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True
        )
        
        if "device" not in result.stdout:
            raise RuntimeError("No ADB device connected")
    
    async def screenshot(self) -> bytes:
        """Take phone screenshot."""
        # Capture on phone
        subprocess.run(["adb", "shell", "screencap", "-p", "/sdcard/screen.png"])
        
        # Pull to PC
        subprocess.run(["adb", "pull", "/sdcard/screen.png", "temp/screen.png"])
        
        # Read
        with open("temp/screen.png", "rb") as f:
            return f.read()
    
    async def tap(self, x: int, y: int):
        """Tap on phone."""
        subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)])
    
    async def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300):
        """Swipe on phone."""
        subprocess.run([
            "adb", "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration)
        ])
    
    async def type_text(self, text: str):
        """Type text on phone."""
        # Escape special characters
        escaped = text.replace(" ", "%s").replace("'", "\\'")
        subprocess.run(["adb", "shell", "input", "text", escaped])
```

---

## PC Controller

### pyautogui Integration

**File:** `core/control/pc_controller.py`  
**Status:** ✅ IMPLEMENTED

```python
class PCController:
    """Control PC via pyautogui."""
    
    async def screenshot(self) -> bytes:
        """Take PC screenshot."""
        screenshot = pyautogui.screenshot()
        
        # Convert to bytes
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        return buffer.getvalue()
    
    async def click(self, x: int, y: int):
        """Click on PC."""
        pyautogui.click(x, y)
    
    async def type_text(self, text: str):
        """Type text on PC."""
        pyautogui.typewrite(text, interval=0.05)
    
    async def press_key(self, key: str):
        """Press key on PC."""
        pyautogui.press(key)
    
    async def hotkey(self, *keys):
        """Press hotkey on PC."""
        pyautogui.hotkey(*keys)
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Phone screenshot | 500ms-2s | ADB transfer |
| Phone tap | 50-100ms | ADB command |
| PC screenshot | 100-500ms | Screen capture |
| PC click | 10-50ms | pyautogui |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `16_TOOL_SYSTEM.md` — Tool system

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
