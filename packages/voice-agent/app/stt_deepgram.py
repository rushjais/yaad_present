"""Deepgram STT service configuration.

[CONFIRM] at sponsor table:
- Exact pipecat import path (varies by version)
- 'multi' language code for multilingual detection
- Whether detect_language=True works with nova-2-general or needs nova-2-multi
"""

import os

# [CONFIRM] import path — pipecat version may differ
from pipecat.services.deepgram import DeepgramSTTService  # type: ignore


def create_stt() -> DeepgramSTTService:
    return DeepgramSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        live_options={
            # [CONFIRM] 'multi' enables multilingual + language detection in Deepgram Nova-2
            "language": "multi",
            "detect_language": True,
            "model": "nova-2-general",
            "encoding": "linear16",
            "sample_rate": 16000,
            "channels": 1,
            "smart_format": True,
            "punctuate": True,
        },
    )
