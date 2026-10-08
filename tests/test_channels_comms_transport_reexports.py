"""Regression tests for the OD-6 channels/comms transport reconciliation."""

from __future__ import annotations

import subprocess
import sys
from textwrap import dedent

import pytest


TRANSPORT_PAIRS = (
    ("bluebubbles", "bluebubbles", "BlueBubblesChannel"),
    ("discord", "discord_channel", "DiscordChannel"),
    ("gmail", "gmail", "GmailChannel"),
    ("google_chat", "google_chat", "GoogleChatChannel"),
    ("irc", "irc_channel", "IRCChannel"),
    ("line", "line_channel", "LineChannel"),
    ("mastodon", "mastodon_channel", "MastodonChannel"),
    ("matrix", "matrix_channel", "MatrixChannel"),
    ("messenger", "messenger_channel", "MessengerChannel"),
    ("nostr", "nostr_channel", "NostrChannel"),
    ("reddit", "reddit_channel", "RedditChannel"),
    ("rocketchat", "rocketchat_channel", "RocketChatChannel"),
    ("sendblue", "sendblue", "SendBlueChannel"),
    ("signal", "signal_channel", "SignalChannel"),
    ("teams", "teams", "TeamsChannel"),
    ("twilio", "twilio_sms", "TwilioSMSChannel"),
    ("twitch", "twitch_channel", "TwitchChannel"),
    ("twitter", "twitter_channel", "TwitterChannel"),
    ("viber", "viber_channel", "ViberChannel"),
    ("webchat", "webchat", "WebChatChannel"),
    ("whatsapp_baileys", "whatsapp_baileys", "WhatsAppBaileysChannel"),
    ("xmpp", "xmpp_channel", "XMPPChannel"),
    ("zulip", "zulip_channel", "ZulipChannel"),
)


@pytest.mark.parametrize("import_order", ("channels_first", "comms_first"))
@pytest.mark.parametrize("registry_key,module_name,class_name", TRANSPORT_PAIRS)
def test_comms_transport_is_channels_reexport_without_duplicate_registration(
    registry_key: str,
    module_name: str,
    class_name: str,
    import_order: str,
) -> None:
    """Both import orders must resolve one class and one registry entry."""
    first, second = (
        ("channels", "comms")
        if import_order == "channels_first"
        else ("comms", "channels")
    )
    script = dedent(
        f"""
        import importlib

        from vectorcode.src.core.registry import ChannelRegistry

        first = importlib.import_module("vectorcode.src.{{first}}.{module_name}")
        second = importlib.import_module("vectorcode.src.{{second}}.{module_name}")
        channels = importlib.import_module("vectorcode.src.channels.{module_name}")
        comms = importlib.import_module("vectorcode.src.comms.{module_name}")
        channels_class = getattr(channels, "{class_name}")
        comms_class = getattr(comms, "{class_name}")

        assert channels_class is comms_class
        assert ChannelRegistry.get("{registry_key}") is channels_class
        assert getattr(first, "{class_name}") is getattr(second, "{class_name}")
        """
    ).format(first=first, second=second)

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
