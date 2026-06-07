"""Sounddevice-based local audio transport for pipecat 1.3.0.

Uses sounddevice (already installed, arm64-native) instead of pyaudio, which
has an architecture conflict on this machine (x86_64 portaudio vs arm64 Python).

Matches the pipecat BaseTransport/.input()/.output() interface so it can be
dropped into the pipeline in place of LiveKitTransport.

Sample rates:
  input  16 kHz — matches Groq STT expectation
  output 32 kHz — matches MiniMax TTS output
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import sounddevice as sd

from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, StartFrame  # type: ignore
from pipecat.transports.base_input import BaseInputTransport  # type: ignore
from pipecat.transports.base_output import BaseOutputTransport  # type: ignore
from pipecat.transports.base_transport import BaseTransport, TransportParams  # type: ignore

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 32000
CHUNK_MS = 20  # 20ms chunks — matches pipecat convention


class SounddeviceParams(TransportParams):
    pass


class SounddeviceInputTransport(BaseInputTransport):
    def __init__(self, params: SounddeviceParams) -> None:
        super().__init__(params)
        self._stream: sd.InputStream | None = None

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        rate = INPUT_SAMPLE_RATE
        blocksize = int(rate * CHUNK_MS / 1000)
        loop = asyncio.get_event_loop()

        def _cb(indata: np.ndarray, frames: int, time, status) -> None:
            pcm = (indata[:, 0] * 32767).astype(np.int16).tobytes()
            audio_frame = InputAudioRawFrame(audio=pcm, sample_rate=rate, num_channels=1)
            asyncio.run_coroutine_threadsafe(self.push_audio_frame(audio_frame), loop)

        self._stream = sd.InputStream(
            samplerate=rate,
            channels=1,
            dtype="float32",
            blocksize=blocksize,
            callback=_cb,
        )
        self._stream.start()
        await self.set_transport_ready(frame)

    async def cleanup(self) -> None:
        await super().cleanup()
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class SounddeviceOutputTransport(BaseOutputTransport):
    def __init__(self, params: SounddeviceParams) -> None:
        super().__init__(params)
        self._stream: sd.OutputStream | None = None
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        self._stream = sd.OutputStream(
            samplerate=OUTPUT_SAMPLE_RATE,
            channels=1,
            dtype="int16",
        )
        self._stream.start()
        await self.set_transport_ready(frame)

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
        if not self._stream:
            return False
        audio = np.frombuffer(frame.audio, dtype=np.int16)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._stream.write, audio)
        return True

    async def cleanup(self) -> None:
        await super().cleanup()
        self._executor.shutdown(wait=False)
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class LocalAudioTransport(BaseTransport):
    """Drop-in replacement for LiveKitTransport using local mic + speakers."""

    def __init__(self) -> None:
        super().__init__()
        params = SounddeviceParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        )
        self._input = SounddeviceInputTransport(params)
        self._output = SounddeviceOutputTransport(params)

    def input(self) -> SounddeviceInputTransport:
        return self._input

    def output(self) -> SounddeviceOutputTransport:
        return self._output
