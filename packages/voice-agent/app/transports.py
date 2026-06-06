"""LiveKit transport factory with VAD.

[CONFIRM] at sponsor table:
- Exact LiveKit SDK import for token generation (livekit-api vs livekit-server-sdk)
- LiveKitParams field names (may differ between pipecat versions)
- Whether SileroVADAnalyzer needs explicit model download
"""

import os

# [CONFIRM] pipecat import paths
from pipecat.transports.network.livekit import LiveKitTransport, LiveKitParams  # type: ignore
from pipecat.vad.silero import SileroVADAnalyzer  # type: ignore

# [CONFIRM] livekit-api import path — install: pip install livekit-api
from livekit.api import AccessToken, VideoGrants  # type: ignore


def _make_token(room_name: str) -> str:
    # [CONFIRM] exact livekit-api token-builder API
    return (
        AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
        .with_identity("yaad-agent")
        .with_name("Yaad")
        .with_grants(VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )


def create_transport(room_name: str) -> LiveKitTransport:
    token = _make_token(room_name)
    return LiveKitTransport(
        url=os.environ["LIVEKIT_URL"],
        token=token,
        room_name=room_name,
        params=LiveKitParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),  # [CONFIRM] constructor args if any
        ),
    )
