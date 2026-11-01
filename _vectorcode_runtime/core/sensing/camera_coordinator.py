"""Module: core/sensing/camera_coordinator.py
Single shared camera-device access point for the API process.

2026-10-25: core/api/routers/camera.py's /camera/ws used to call
cv2.VideoCapture(index) directly, independent of core/sensing/camera.py's
FaceDetector/FatigueMonitor doing the same thing from the autonomous loop
process -- two separate OS processes grabbing one exclusive webcam handle,
so whichever read second failed and killed its own stream. Owner decision:
single shared camera access for everything. This module is now the ONLY
place in VECTOR that calls cv2.VideoCapture; every consumer in this process
(the live /camera/ws stream, the one-shot /camera/snapshot endpoint used by
the loop process's sensing) acquires/releases a reference to the same
device handle instead of opening its own.
"""
import asyncio
import time

from loguru import logger

__all__ = ["CameraCoordinator", "get_camera_coordinator"]


class CameraCoordinator:
    """Ref-counted owner of the one physical cv2.VideoCapture handle.

    acquire() opens the device on the first caller and increments a
    refcount on every later caller; release() decrements and only closes
    the device once the last consumer has released it. All device access
    (open/read/release) is serialized through one asyncio.Lock so a
    snapshot request can never race the live stream's own read.
    """

    def __init__(self) -> None:
        self._cv2 = None
        self._cap = None
        self._index: int | None = None
        self._refcount = 0
        self._lock = asyncio.Lock()
        self._last_frame_at = 0.0

    def _ensure_cv2(self):
        if self._cv2 is None:
            import cv2
            self._cv2 = cv2
        return self._cv2

    async def acquire(self, index: int = 0) -> bool:
        """Register one more consumer; opens the device if it isn't already open.

        A second caller asking for a different index than the one currently
        open still shares the already-open device (the index only matters
        for the very first acquire) -- VECTOR only ever drives one physical
        webcam, so this is a deliberate simplification, not a bug.
        """
        async with self._lock:
            if self._cap is not None:
                self._refcount += 1
                return True
            cv2 = self._ensure_cv2()
            cap = await asyncio.to_thread(cv2.VideoCapture, index)
            if not cap.isOpened():
                await asyncio.to_thread(cap.release)
                return False
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 15)
            self._cap = cap
            self._index = index
            self._refcount = 1
            logger.info(f"[VECTOR][camera] device {index} opened (shared, refcount=1)")
            return True

    async def release(self) -> None:
        """Deregister one consumer; closes the device once refcount hits 0."""
        async with self._lock:
            if self._cap is None:
                return
            self._refcount = max(0, self._refcount - 1)
            if self._refcount == 0:
                cap = self._cap
                self._cap = None
                self._index = None
                await asyncio.to_thread(cap.release)
                logger.info("[VECTOR][camera] device released (shared, refcount=0)")
            else:
                logger.debug(f"[VECTOR][camera] consumer released (refcount={self._refcount})")

    async def read_frame(self):
        """Grab one fresh BGR frame. Returns None if the device isn't open or the read failed."""
        async with self._lock:
            if self._cap is None:
                return None
            ret, frame = await asyncio.to_thread(self._cap.read)
            if not ret:
                return None
            self._last_frame_at = time.time()
            return frame

    @property
    def is_open(self) -> bool:
        return self._cap is not None

    @property
    def refcount(self) -> int:
        return self._refcount


_coordinator: CameraCoordinator | None = None


def get_camera_coordinator() -> CameraCoordinator:
    """Process-wide singleton -- every caller in this process shares the same instance."""
    global _coordinator
    if _coordinator is None:
        _coordinator = CameraCoordinator()
    return _coordinator


if __name__ == "__main__":
    async def _smoke_test() -> bool:
        coord = get_camera_coordinator()
        ok1 = await coord.acquire(0)
        if not ok1:
            print("camera_coordinator.py: no physical camera available, skipping live checks")
            return True
        ok2 = await coord.acquire(0)  # second consumer shares the same handle
        assert coord.refcount == 2, f"expected refcount=2, got {coord.refcount}"
        frame = await coord.read_frame()
        assert frame is not None, "expected a real frame from the shared device"
        await coord.release()
        assert coord.is_open, "device must stay open while one consumer remains"
        await coord.release()
        assert not coord.is_open, "device must close once the last consumer releases"
        return ok1 and ok2

    result = asyncio.run(_smoke_test())
    print("✅ camera_coordinator.py OK" if result else "❌ FAILED")
