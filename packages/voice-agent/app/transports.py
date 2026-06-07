"""LiveKit transport factory.

Pipecat 1.3.0 path changes (resolved 2026-06-06):
  pipecat.transports.network.livekit → pipecat.transports.livekit.transport
  pipecat.vad.silero                 → pipecat.audio.vad.silero
  LiveKitParams: vad_enabled/vad_analyzer removed — VAD is now wired via
    VADController in the pipeline (see agent.py).

[CONFIRM] livekit-api token generation: confirmed import path below.
"""

import os

from pipecat.audio.vad.silero import SileroVADAnalyzer  # type: ignore
from pipecat.audio.vad.vad_analyzer import VADParams  # type: ignore
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport  # type: ignore
from livekit.api import AccessToken, VideoGrants  # type: ignore


def create_vad() -> SileroVADAnalyzer:
    return SileroVADAnalyzer(params=VADParams(
        confidence=0.7,
        start_secs=0.1,
        stop_secs=2.0,
        min_volume=0.2,
    ))


def _make_token(room_name: str) -> str:
    return (
        AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
        .with_identity("yaad-agent")
        .with_name("Yaad")
        .with_grants(VideoGrants(room_join=True, room=room_name,
                                  can_publish=True, can_subscribe=True))
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
        ),
    )
