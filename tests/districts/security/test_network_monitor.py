import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import json
from unittest.mock import MagicMock, patch

import pytest

from districts.security.network_monitor import NetworkMonitor, _parse_netstat, BlocklistEntry


@pytest.fixture
def monitor(tmp_path):
    bl = tmp_path / "ip_blocklist.txt"
    bl.write_text("10.0.0.1:test_entry\n", encoding="utf-8")
    m = NetworkMonitor()
    m._blocklist_path = bl
    m._load_blocklist()
    return m


class TestParseNetstat:
    def test_parses_netstat_output(self):
        output = (
            "  Proto  Local Address          Foreign Address        State\n"
            "  TCP    127.0.0.1:8080         0.0.0.0:0              LISTENING\n"
            "  TCP    192.168.1.10:54321     93.184.216.34:443      ESTABLISHED\n"
        )
        conns = _parse_netstat(output)
        assert len(conns) == 2
        assert conns[0]["proto"] == "TCP"
        assert conns[0]["local"] == "127.0.0.1:8080"
        assert conns[1]["foreign"] == "93.184.216.34:443"

    def test_empty_output(self):
        assert _parse_netstat("") == []

    def test_skips_header_lines(self):
        output = "Active Connections\n  Proto  Local\n  TCP    1.2.3.4:80     5.6.7.8:443     ESTABLISHED\n"
        assert len(_parse_netstat(output)) == 1


class TestScanConnections:
    @patch("districts.security.network_monitor.subprocess.run")
    def test_scan_returns_list(self, mock_run, monitor):
        mock_run.return_value = MagicMock(stdout="  TCP    1.2.3.4:80     5.6.7.8:443     ESTABLISHED\n")
        conns = monitor.scan_connections()
        assert isinstance(conns, list)
        assert len(conns) >= 1

    @patch("districts.security.network_monitor.subprocess.run")
    def test_scan_suspicious_port_scoring(self, mock_run, monitor):
        mock_run.return_value = MagicMock(stdout="  TCP    1.2.3.4:52311     10.0.0.5:4444     ESTABLISHED\n")
        conns = monitor.scan_connections()
        high_score = [c for c in conns if c.get("suspicious_score", 0) > 0.5]
        assert len(high_score) >= 1

    @patch("districts.security.network_monitor.subprocess.run")
    def test_scan_timeout(self, mock_run, monitor):
        mock_run.side_effect = TimeoutError
        assert monitor.scan_connections() == []


class TestBlocklist:
    def test_load_blocklist(self, monitor):
        assert len(monitor._blocklist) == 1
        assert monitor._blocklist[0].ip == "10.0.0.1"

    def test_is_blocklisted(self, monitor):
        assert monitor._is_blocklisted("10.0.0.1")
        assert not monitor._is_blocklisted("1.2.3.4")

    def test_check_blocklist_no_matches(self, monitor):
        monitor._connection_history = [{"foreign": "8.8.8.8:53"}]
        assert monitor.check_blocklist() == []


class TestPortScanDetection:
    def test_detect_no_scan(self, monitor):
        monitor._connection_history = [{"foreign": "8.8.8.8:443"}]
        threats = monitor.detect_port_scan()
        assert isinstance(threats, list)

    def test_connection_rate_tracking(self, monitor):
        monitor._rate_tracker["10.0.0.1"] = [100.0, 101.0, 102.0]
        monitor._connection_history = [{"foreign": "10.0.0.1:80"}]
        threats = monitor.detect_port_scan()
        assert isinstance(threats, list)


class TestTrackConnectionRate:
    def test_empty_state(self, monitor):
        monitor._connection_history = []
        rates = monitor.track_connection_rate()
        assert rates["total_connections"] == 0
        assert rates["total_unique_ips"] == 0

    def test_top_talkers(self, monitor):
        monitor._connection_history = [
            {"foreign": "1.1.1.1:80"}, {"foreign": "1.1.1.1:443"},
            {"foreign": "8.8.8.8:53"},
        ]
        rates = monitor.track_connection_rate()
        assert len(rates["top_talkers"]) == 2
        assert rates["top_talkers"][0]["ip"] == "1.1.1.1"


class TestGenerateReport:
    @patch("districts.security.network_monitor.subprocess.run")
    def test_report_structure(self, mock_run, monitor):
        mock_run.return_value = MagicMock(stdout="  TCP    1.2.3.4:80     5.6.7.8:443     ESTABLISHED\n")
        report = monitor.generate_report()
        for key in ("total_connections", "port_scan_threats", "blocklist_matches", "timestamp"):
            assert key in report
