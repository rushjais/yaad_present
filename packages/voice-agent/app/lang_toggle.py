"""Language toggle — background stdin listener for manual EN/HI switching.

Press 'h' to flip between English and Hindi. The toggle is the source of
truth for STT language hint and answer-composition path; Groq auto-detect
is kept as a safety net in MemoryContextProcessor.

Works by putting stdin into raw mode (single keypress, no Enter needed).
Gracefully no-ops if stdin is not a tty (piped, redirected, Docker TTY-less).
"""

import logging
import sys
import threading

logger = logging.getLogger(__name__)


class LanguageState:
    """Shared mutable language selection. Thread-safe for CPython (GIL)."""

    def __init__(self, default: str = "en") -> None:
        self._lang = default

    @property
    def lang(self) -> str:
        return self._lang

    def toggle(self) -> str:
        self._lang = "hi" if self._lang == "en" else "en"
        return self._lang


def _listen(state: LanguageState) -> None:
    """Blocking loop: reads one raw char at a time, toggles on 'h'."""
    try:
        import termios
        import tty
    except ImportError:
        logger.warning("lang-toggle: termios/tty not available — toggle disabled")
        return

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == "h":
                lang = state.toggle()
                label = "HINDI" if lang == "hi" else "ENGLISH"
                # \r so the line prints cleanly in raw-mode terminal
                print(f"\r\n>>> LANGUAGE: {label}\r\n", flush=True)
                logger.info("Language toggled → %s", label)
            elif ch in ("\x03", "\x04"):
                # Ctrl-C / Ctrl-D — restore terminal and stop gracefully
                break
    except Exception as e:
        logger.warning("lang-toggle listener error: %s", e)
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass


def start_lang_listener(state: LanguageState) -> None:
    """Start the background keyboard listener.

    Non-blocking: spawns a daemon thread so it dies with the process.
    Skips silently if stdin is not an interactive tty.
    """
    try:
        import termios

        termios.tcgetattr(sys.stdin.fileno())  # raises if not a real tty
    except Exception:
        logger.info("lang-toggle: stdin is not a tty — toggle unavailable (set lang in .env or code)")
        return

    t = threading.Thread(target=_listen, args=(state,), daemon=True, name="lang-toggle")
    t.start()
    logger.info("lang-toggle: press 'h' to switch language (currently: %s)", state.lang.upper())
