@echo off
cd /d "%~dp0"
echo ==== UPLOADER GATE + CONTENT REGRESSION %date% %time% ==== > uploader_gate_test.log
python -m pytest tests/districts/test_content_publish_gate.py tests/test_content_district_run_wiring.py tests/backend/test_audit_followups.py -v --tb=short >> uploader_gate_test.log 2>&1
echo EXITCODE=%ERRORLEVEL% >> uploader_gate_test.log
echo DONE_MARKER >> uploader_gate_test.log
