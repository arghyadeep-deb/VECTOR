"""Short malware-name fragments must match whole tokens only (live HUD 2026-09-25: 'WMIRegistrationService.exe'
contains 'rat' and pushed the threat level to HIGH)."""
from __future__ import annotations

import pytest

from core.control.security.threat_detector import _name_is_suspicious


@pytest.mark.parametrize("name", [
    "wmiregistrationservice.exe", "determiner.exe", "operator.exe", "generator.exe", "administrator.exe",
    "python.exe", "explorer.exe",
])
def test_ordinary_names_containing_a_short_fragment_are_not_flagged(name):
    assert _name_is_suspicious(name) is None


@pytest.mark.parametrize("name,frag", [
    ("rat.exe", "rat"), ("some-rat-client.exe", "rat"), ("xmrig.exe", "xmrig"), ("my_cryptominer.bin", "cryptominer"),
    ("miner.exe", "miner"), ("mimikatz.exe", "mimikatz"), ("ncat-netcat.exe", "netcat"),
])
def test_real_malware_names_are_still_flagged(name, frag):
    assert _name_is_suspicious(name) == frag
