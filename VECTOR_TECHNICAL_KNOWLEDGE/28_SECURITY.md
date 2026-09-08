# Security

**Purpose:** Threat detection, malware scanning, SSRF protection, prompt injection
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR has multi-layer security: threat detection, malware scanning, SSRF guards, prompt injection scanning, permission gating, and privacy enforcement.

**Key Properties:**
- **ThreatScout** — process/registry/network scanning
- **MalwareHunter** — VirusTotal + MIME + LightGBM
- **SSRF guard** — URL validation before every HTTP call
- **Prompt injection** — boundary scanning
- **Permission gateway** — GREEN/YELLOW/RED tiers
- **Privacy enforcer** — cloud vs local data enforcement

**Files:**
- `districts/security/` (4 agents)
- `core/security/` (guards, scanners)
- `core/loop/permission_gateway.py`

**Status:** ✅ IMPLEMENTED, production-reachable

---

## Security Agents

### ThreatScout

**File:** `districts/security/threat_scout.py`
**Status:** ✅ IMPLEMENTED

```python
class ThreatScout(AgentBase):
    """Threat detection agent."""
    
    async def _execute_task(self, query: str, task_type: str) -> dict:
        if task_type == "scan_processes":
            return await self._scan_processes()
        elif task_type == "scan_registry":
            return await self._scan_registry()
        elif task_type == "scan_network":
            return await self._scan_network()
        else:
            return {"success": False, "error": "Unknown task type"}
    
    async def _scan_processes(self) -> dict:
        """Scan running processes for threats."""
        import psutil
        
        suspicious = []
        
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                name = proc.info['name'].lower()
                
                # Check for known malware patterns
                if any(m in name for m in ["miner", "crypto", "bot"]):
                    suspicious.append({
                        "pid": proc.info['pid'],
                        "name": proc.info['name'],
                        "reason": "suspicious_name"
                    })
                
                # Check for unsigned executables
                exe = proc.info.get('exe', '')
                if exe and not self._is_signed(exe):
                    suspicious.append({
                        "pid": proc.info['pid'],
                        "name": proc.info['name'],
                        "reason": "unsigned_executable"
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        return {
            "success": True,
            "suspicious": suspicious,
            "count": len(suspicious)
        }
    
    async def _scan_registry(self) -> dict:
        """Scan Windows registry for persistence."""
        import winreg
        
        suspicious = []
        
        # Check startup keys
        keys_to_check = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run")
        ]
        
        for hkey, path in keys_to_check:
            try:
                key = winreg.OpenKey(hkey, path)
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        
                        # Check if value points to suspicious location
                        if "temp" in value.lower() or "appdata" in value.lower():
                            suspicious.append({
                                "key": f"{path}\\{name}",
                                "value": value,
                                "reason": "suspicious_startup"
                            })
                        
                        i += 1
                    except OSError:
                        break
                
                winreg.CloseKey(key)
            except OSError:
                pass
        
        return {
            "success": True,
            "suspicious": suspicious
        }
    
    async def _scan_network(self) -> dict:
        """Scan network connections for threats."""
        import psutil
        
        suspicious = []
        
        for conn in psutil.net_connections():
            if conn.status == "ESTABLISHED":
                # Check for known bad IPs
                remote_ip = conn.raddr.ip if conn.raddr else None
                
                if remote_ip and self._is_threat_ip(remote_ip):
                    suspicious.append({
                        "local": f"{conn.laddr.ip}:{conn.laddr.port}",
                        "remote": f"{conn.raddr.ip}:{conn.raddr.port}",
                        "pid": conn.pid,
                        "reason": "threat_ip"
                    })
        
        return {
            "success": True,
            "suspicious": suspicious
        }
```

### MalwareHunter

**File:** `districts/security/malware_hunter.py`
**Status:** ✅ IMPLEMENTED

```python
class MalwareHunter(AgentBase):
    """Malware detection agent."""
    
    async def _execute_task(self, query: str, task_type: str) -> dict:
        if task_type == "scan_file":
            return await self._scan_file(query)
        elif task_type == "scan_directory":
            return await self._scan_directory(query)
        else:
            return {"success": False, "error": "Unknown task type"}
    
    async def _scan_file(self, file_path: str) -> dict:
        """Scan file for malware."""
        from core.control.security.malware_detector import MalwareDetector
        
        detector = MalwareDetector()
        result = await detector.scan(file_path)
        
        return {
            "success": True,
            "file": file_path,
            "malware": result["is_malware"],
            "confidence": result["confidence"],
            "details": result["details"]
        }
    
    async def _scan_directory(self, dir_path: str) -> dict:
        """Scan directory for malware."""
        import os
        
        results = []
        
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                
                try:
                    scan_result = await self._scan_file(file_path)
                    if scan_result["malware"]:
                        results.append(scan_result)
                except Exception:
                    pass
        
        return {
            "success": True,
            "malware_found": results,
            "count": len(results)
        }
```

### Malware Detector

**File:** `core/control/security/malware_detector.py`
**Status:** ✅ IMPLEMENTED

```python
class MalwareDetector:
    """3-layer malware detection."""
    
    async def scan(self, file_path: str) -> dict:
        """Scan file with 3 layers."""
        
        # Layer 1: VirusTotal API
        vt_result = await self._check_virustotal(file_path)
        if vt_result["detected"]:
            return {
                "is_malware": True,
                "confidence": 1.0,
                "details": vt_result
            }
        
        # Layer 2: MIME type check
        mime_result = self._check_mime(file_path)
        if mime_result["suspicious"]:
            return {
                "is_malware": True,
                "confidence": 0.8,
                "details": mime_result
            }
        
        # Layer 3: LightGBM model
        model_result = await self._check_model(file_path)
        
        return {
            "is_malware": model_result["is_malware"],
            "confidence": model_result["confidence"],
            "details": model_result
        }
    
    async def _check_virustotal(self, file_path: str) -> dict:
        """Check VirusTotal API."""
        import hashlib
        import httpx
        from core.config import CONFIG
        
        # Calculate hash
        with open(file_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        # Query VT
        try:
            response = await httpx.get(
                f"https://www.virustotal.com/api/v3/files/{file_hash}",
                headers={"x-apikey": CONFIG["virustotal_key"]},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                detected = data["data"]["attributes"]["last_analysis_stats"]["malicious"] > 0
                return {"detected": detected, "hash": file_hash}
        except Exception:
            pass
        
        return {"detected": False}
    
    def _check_mime(self, file_path: str) -> dict:
        """Check MIME type."""
        import mimetypes
        
        mime_type, _ = mimetypes.guess_type(file_path)
        
        suspicious_mimes = [
            "application/x-executable",
            "application/x-dosexec",
            "application/x-sharedlib"
        ]
        
        return {
            "suspicious": mime_type in suspicious_mimes,
            "mime_type": mime_type
        }
    
    async def _check_model(self, file_path: str) -> dict:
        """Check with LightGBM model."""
        # Load model
        try:
            import lightgbm as lgb
            
            model = lgb.Booster(model_file="models/malware_detector.lgb")
            
            # Extract features
            features = self._extract_features(file_path)
            
            # Predict
            prediction = model.predict([features])[0]
            
            return {
                "is_malware": prediction > 0.5,
                "confidence": prediction
            }
        except Exception:
            return {"is_malware": False, "confidence": 0.0}
```

---

## SSRF Guard

### URL Validation

**File:** `core/inference/provider_client.py`
**Status:** ✅ IMPLEMENTED

```python
def _ssrf_check(url: str):
    """Check URL for SSRF attacks."""
    from urllib.parse import urlparse
    
    parsed = urlparse(url)
    hostname = parsed.hostname
    
    # Block private IPs
    if hostname in ["localhost", "127.0.0.1", "0.0.0.0"]:
        raise ValueError("SSRF: localhost blocked")
    
    if hostname.startswith("10.") or hostname.startswith("192.168."):
        raise ValueError("SSRF: private IP blocked")
    
    if hostname.startswith("172."):
        # Check 172.16.0.0 - 172.31.255.255
        parts = hostname.split(".")
        if len(parts) >= 2:
            second = int(parts[1])
            if 16 <= second <= 31:
                raise ValueError("SSRF: private IP blocked")
    
    # Block metadata endpoints
    if hostname in ["169.254.169.254", "metadata.google.internal"]:
        raise ValueError("SSRF: metadata endpoint blocked")
```

---

## Prompt Injection Scanner

### Boundary Protection

**File:** `core/security/prompt_injection.py`
**Status:** ✅ IMPLEMENTED

```python
def scan_text(text: str) -> dict:
    """Scan text for prompt injection."""
    
    # Patterns
    patterns = [
        r"ignore previous instructions",
        r"you are now",
        r"system prompt",
        r"assistant:",
        r"new role"
    ]
    
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return {
                "risk": "CRITICAL",
                "pattern": pattern
            }
    
    return {"risk": "LOW"}
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Process scan | 100ms-1s | Process count |
| Network scan | 50-500ms | Connection count |
| VirusTotal check | 1-5s | API latency |
| Malware model | 10-100ms | Model inference |
| SSRF check | <1ms | URL parsing |
| Prompt injection scan | <1ms | Regex matching |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `09_GOVERNOR_AND_PERMISSIONS.md` — Permission gateway
- `28_SECURITY.md` — this document
- `18_PHONE_AND_DEVICE.md` — Phone control

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
