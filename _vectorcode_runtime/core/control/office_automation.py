"""Real Microsoft Office (Word/Excel) automation via COM — owner capability
sweep, 2026-10-25.

Owner asked to "complete COM automation" but never named a specific app/
task despite being asked twice (which app/task for COM automation? ->
no answer; Office vs Google Docs? -> confirmed real Office is installed).
Scoped to Word (write/read), Excel (read/write cell), and PowerPoint
(create a deck) — the generically useful cases. Outlook is not built
(not installed on this machine) unless/until there's a concrete need.

Uses win32com.client to drive the real, already-installed desktop apps
(Microsoft Office Home 2024 — confirmed via the actual executables and
Windows' own installed-programs registry, not assumed). Each call launches
its own invisible Office instance, does the one operation, saves, and
quits — no lingering process, no visible window popping up on the
owner's screen.
"""
import sys
import os
from pathlib import Path

from loguru import logger

__all__ = ["OfficeController"]


class OfficeController:
    def __init__(self):
        from core.loop.permission_gateway import PermissionGateway
        self._gateway = PermissionGateway()

    def _verify_control_token(self, token, *allowed_action_types) -> bool:
        for a in allowed_action_types:
            if self._gateway.verify_control(token, a):
                return True
        return False

    # ------------------------------------------------------------------
    # Word
    # ------------------------------------------------------------------

    def word_write(self, text: str, path: str = "", *, control_token: str | None = None) -> dict:
        """Create a new Word document containing `text` and save it.
        Defaults to ~/Documents/VECTOR docs/<short title>.docx when no
        path is given, rather than guessing a filename from the content."""
        if not self._verify_control_token(control_token, "word_write"):
            logger.warning("[VECTOR][office] word_write blocked — no valid control token")
            return {"ok": False, "error": "word_write requires a gateway control token"}
        if sys.platform != "win32":
            return {"ok": False, "error": "word_write is Windows-only"}
        try:
            import win32com.client as win32
            import pythoncom
            pythoncom.CoInitialize()
            try:
                word = win32.Dispatch("Word.Application")
                word.Visible = False
                doc = word.Documents.Add()
                doc.Content.Text = text
                if not path:
                    out_dir = Path.home() / "Documents" / "VECTOR docs"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    import time as _time
                    path = str(out_dir / f"vector_doc_{int(_time.time())}.docx")
                else:
                    path = str(Path(os.path.expandvars(path)).expanduser().resolve())
                doc.SaveAs(path)
                doc.Close()
                word.Quit()
                logger.info(f"[VECTOR][office] Word doc written -> {path}")
                return {"ok": True, "path": path}
            finally:
                # 2026-10-25: deliberately NOT uninitializing COM here --
                # see wmi_info.py's hardware_info() docstring for the full
                # root-cause writeup (repeated teardown/rebuild on the
                # server's one shared long-lived thread was producing real
                # COM errors downstream in other COM calls on that thread).
                pass
        except Exception as e:
            logger.error(f"[VECTOR][office] word_write error: {e}")
            return {"ok": False, "error": str(e)}

    def word_read(self, path: str, *, control_token: str | None = None) -> dict:
        """Read the full text content of an existing Word document."""
        if not self._verify_control_token(control_token, "word_read"):
            logger.warning("[VECTOR][office] word_read blocked — no valid control token")
            return {"text": "", "error": "word_read requires a gateway control token"}
        if sys.platform != "win32":
            return {"text": "", "error": "word_read is Windows-only"}
        resolved = Path(os.path.expandvars(path)).expanduser().resolve()
        if not resolved.exists():
            return {"text": "", "error": f"file does not exist: {resolved}"}
        try:
            import win32com.client as win32
            import pythoncom
            pythoncom.CoInitialize()
            try:
                word = win32.Dispatch("Word.Application")
                word.Visible = False
                doc = word.Documents.Open(str(resolved), ReadOnly=True)
                text = doc.Content.Text
                doc.Close(False)
                word.Quit()
                logger.info(f"[VECTOR][office] Word doc read <- {resolved}")
                return {"text": text}
            finally:
                # 2026-10-25: deliberately NOT uninitializing COM here --
                # see wmi_info.py's hardware_info() docstring for the full
                # root-cause writeup (repeated teardown/rebuild on the
                # server's one shared long-lived thread was producing real
                # COM errors downstream in other COM calls on that thread).
                pass
        except Exception as e:
            logger.error(f"[VECTOR][office] word_read error: {e}")
            return {"text": "", "error": str(e)}

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------

    def excel_read_cell(self, path: str, cell: str, sheet: str = "",
                         *, control_token: str | None = None) -> dict:
        """Read one cell's value (e.g. cell='B3') from an Excel workbook."""
        if not self._verify_control_token(control_token, "excel_read_cell"):
            logger.warning("[VECTOR][office] excel_read_cell blocked — no valid control token")
            return {"value": None, "error": "excel_read_cell requires a gateway control token"}
        if sys.platform != "win32":
            return {"value": None, "error": "excel_read_cell is Windows-only"}
        resolved = Path(os.path.expandvars(path)).expanduser().resolve()
        if not resolved.exists():
            return {"value": None, "error": f"file does not exist: {resolved}"}
        try:
            import win32com.client as win32
            import pythoncom
            pythoncom.CoInitialize()
            try:
                excel = win32.Dispatch("Excel.Application")
                excel.Visible = False
                wb = excel.Workbooks.Open(str(resolved), ReadOnly=True)
                ws = wb.Sheets(sheet) if sheet else wb.Sheets(1)
                value = ws.Range(cell).Value
                wb.Close(False)
                excel.Quit()
                logger.info(f"[VECTOR][office] Excel cell read {cell} <- {resolved}")
                return {"value": value}
            finally:
                # 2026-10-25: deliberately NOT uninitializing COM here --
                # see wmi_info.py's hardware_info() docstring for the full
                # root-cause writeup (repeated teardown/rebuild on the
                # server's one shared long-lived thread was producing real
                # COM errors downstream in other COM calls on that thread).
                pass
        except Exception as e:
            logger.error(f"[VECTOR][office] excel_read_cell error: {e}")
            return {"value": None, "error": str(e)}

    def excel_write_cell(self, path: str, cell: str, value, sheet: str = "",
                          *, control_token: str | None = None) -> dict:
        """Write one cell's value in an Excel workbook and save. Creates a
        new workbook at `path` if it doesn't exist yet."""
        if not self._verify_control_token(control_token, "excel_write_cell"):
            logger.warning("[VECTOR][office] excel_write_cell blocked — no valid control token")
            return {"ok": False, "error": "excel_write_cell requires a gateway control token"}
        if sys.platform != "win32":
            return {"ok": False, "error": "excel_write_cell is Windows-only"}
        resolved = Path(os.path.expandvars(path)).expanduser().resolve()
        try:
            import win32com.client as win32
            import pythoncom
            pythoncom.CoInitialize()
            try:
                excel = win32.Dispatch("Excel.Application")
                excel.Visible = False
                if resolved.exists():
                    wb = excel.Workbooks.Open(str(resolved))
                else:
                    resolved.parent.mkdir(parents=True, exist_ok=True)
                    wb = excel.Workbooks.Add()
                ws = wb.Sheets(sheet) if sheet else wb.Sheets(1)
                ws.Range(cell).Value = value
                wb.SaveAs(str(resolved)) if not resolved.exists() else wb.Save()
                wb.Close()
                excel.Quit()
                logger.info(f"[VECTOR][office] Excel cell written {cell} -> {resolved}")
                return {"ok": True, "path": str(resolved)}
            finally:
                # 2026-10-25: deliberately NOT uninitializing COM here --
                # see wmi_info.py's hardware_info() docstring for the full
                # root-cause writeup (repeated teardown/rebuild on the
                # server's one shared long-lived thread was producing real
                # COM errors downstream in other COM calls on that thread).
                pass
        except Exception as e:
            logger.error(f"[VECTOR][office] excel_write_cell error: {e}")
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # PowerPoint
    # ------------------------------------------------------------------

    def powerpoint_create(self, title: str, slides: list[str], path: str = "",
                           *, control_token: str | None = None) -> dict:
        """Create a presentation: one title slide, then one bullet-text
        slide per entry in `slides`. Saves to ~/Documents/VECTOR docs/ by
        default, same convention as word_write."""
        if not self._verify_control_token(control_token, "powerpoint_create"):
            logger.warning("[VECTOR][office] powerpoint_create blocked — no valid control token")
            return {"ok": False, "error": "powerpoint_create requires a gateway control token"}
        if sys.platform != "win32":
            return {"ok": False, "error": "powerpoint_create is Windows-only"}
        try:
            import win32com.client as win32
            import pythoncom
            pythoncom.CoInitialize()
            try:
                ppt = win32.Dispatch("PowerPoint.Application")
                deck = ppt.Presentations.Add(WithWindow=False)
                # ppLayoutTitle = 1
                title_slide = deck.Slides.Add(1, 1)
                title_slide.Shapes.Title.TextFrame.TextRange.Text = title or "(untitled)"
                for i, content in enumerate(slides or [], start=2):
                    # ppLayoutText = 2 (title + body placeholder)
                    slide = deck.Slides.Add(i, 2)
                    slide.Shapes.Title.TextFrame.TextRange.Text = f"Slide {i - 1}"
                    slide.Shapes.Placeholders(2).TextFrame.TextRange.Text = str(content)
                if not path:
                    out_dir = Path.home() / "Documents" / "VECTOR docs"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    import time as _time
                    path = str(out_dir / f"vector_deck_{int(_time.time())}.pptx")
                else:
                    path = str(Path(os.path.expandvars(path)).expanduser().resolve())
                deck.SaveAs(path)
                deck.Close()
                ppt.Quit()
                logger.info(f"[VECTOR][office] PowerPoint deck written -> {path}")
                return {"ok": True, "path": path, "slide_count": 1 + len(slides or [])}
            finally:
                # 2026-10-25: deliberately NOT uninitializing COM here --
                # see wmi_info.py's hardware_info() docstring for the full
                # root-cause writeup (repeated teardown/rebuild on the
                # server's one shared long-lived thread was producing real
                # COM errors downstream in other COM calls on that thread).
                pass
        except Exception as e:
            logger.error(f"[VECTOR][office] powerpoint_create error: {e}")
            return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    # Real test, no mocks — requires Word/Excel installed (confirmed present).
    ctrl = OfficeController()
    tok = ctrl._gateway.grant_control("word_write", uses=1, ttl=60)
    result = ctrl.word_write("VECTOR office_automation.py self-test.", control_token=tok)
    ok = result.get("ok") and Path(result.get("path", "")).exists()
    print("✅ office_automation OK" if ok else f"❌ FAILED: {result}")
    if ok:
        Path(result["path"]).unlink(missing_ok=True)
