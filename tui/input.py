"""
Prompt Toolkit based input handler for Talker-Thinker

Provides Chinese-friendly input with:
- Proper UTF-8 character deletion (one backspace = one Chinese character)
- Command history browsing (up/down arrows)
- Auto-suggestion from history
- File-based history persistence
"""

import os
import asyncio
from pathlib import Path
from typing import Optional

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style


# Custom style for Talker-Thinker
TALKER_STYLE = Style.from_dict({
    'prompt': 'ansicyan bold',
    'timestamp': 'ansigreen',
    'history': 'ansigray',
})


def create_key_bindings():
    """Create custom key bindings"""
    kb = KeyBindings()

    @kb.add('c-c')
    def _(event):
        """Handle Ctrl+C"""
        # Don't interrupt on Ctrl+C, just insert newline or ignore
        pass

    return kb


def get_logger():
    """Lazy logger import to avoid circular dependency"""
    from monitoring.logging import get_logger as _get_logger
    return _get_logger("tui.input")


class TalkerInput:
    """
    Chinese-friendly input handler using prompt_toolkit

    Features:
    - Proper UTF-8 backspace handling
    - History persistence
    - Auto-suggestion
    - Clean timestamp display
    """

    def __init__(self, history_file: str = "~/.talker-thinker-history"):
        """
        Initialize the input handler

        Args:
            history_file: Path to store command history
        """
        # Expand ~ to actual home directory path
        self.history_file = os.path.expanduser(history_file)
        self._key_bindings = create_key_bindings()

        # Ensure parent directory exists
        history_path = Path(self.history_file)
        history_path.parent.mkdir(parents=True, exist_ok=True)

        self._history = FileHistory(self.history_file)

        # Output event for synchronizing input prompt display
        self._output_event: Optional[asyncio.Event] = None

    def set_output_event(self, event: asyncio.Event) -> None:
        """
        Set the output event for synchronizing input prompt display

        Args:
            event: asyncio.Event that is set when output is complete
        """
        self._output_event = event

    def get_input(self, session_id: str = None) -> str:
        """
        Get user input with TUI support

        Args:
            session_id: Optional session ID (not used for input, but kept for API compatibility)

        Returns:
            User input string
        """
        import time

        logger = get_logger()
        now = time.time()
        timestamp = time.strftime("%H:%M:%S", time.localtime(now))
        ms = int((now % 1) * 1000)
        timestamp_formatted = f"{timestamp}.{ms:03d}"

        # Wait for output to complete before showing input prompt
        # This prevents the input prompt from appearing during Talker output
        if self._output_event:
            wait_start = time.time()
            while not self._output_event.is_set():
                # Timeout after 5 seconds to prevent infinite wait
                if time.time() - wait_start > 5.0:
                    logger.debug("Output event timeout, showing input prompt anyway")
                    break
                time.sleep(0.05)
            # Clear the event for next round
            # Note: The event will be set again when the next output starts

        try:
            user_input = prompt(
                message=[
                    ('class:timestamp', f'[{timestamp_formatted}]'),
                    ('class:prompt', ' 你：'),
                ],
                history=self._history,
                auto_suggest=AutoSuggestFromHistory(),
                key_bindings=self._key_bindings,
                style=TALKER_STYLE,
                multiline=False,
                wrap_lines=True,
                refresh_interval=0.1,
            )
            return user_input.strip()

        except EOFError:
            # Handle Ctrl+D
            logger.debug("Input EOFError")
            return ""
        except KeyboardInterrupt:
            # Handle Ctrl+C
            logger.debug("Input KeyboardInterrupt")
            return ""
        except Exception as e:
            logger.error(f"Input error: {e}", exc_info=True)
            return ""

    def print_status(self, message: str):
        """Print a status message"""
        print(f"\n[Talker] {message}")

    def print_response(self, response: str):
        """Print system response"""
        print(response, end="", flush=True)


# Fallback for environments where prompt_toolkit is not available
class FallbackInput:
    """Simple fallback input handler using native input()"""

    def __init__(self, history_file: str = None):
        pass

    def set_output_event(self, event: asyncio.Event) -> None:
        """Set the output event for synchronizing input prompt display"""
        self._output_event = event

    def get_input(self, session_id: str = None) -> str:
        """Get user input using native input()"""
        import time
        loop = None
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Wait for output to complete before showing input prompt
        if hasattr(self, '_output_event') and self._output_event:
            wait_start = time.time()
            while not self._output_event.is_set():
                if time.time() - wait_start > 5.0:
                    break
                time.sleep(0.05)

        now = time.time()
        timestamp = time.strftime("%H:%M:%S", time.localtime(now))
        ms = int((now % 1) * 1000)
        print(f"\n[{timestamp}.{ms:03d}] 你：", end="", flush=True)

        try:
            line = input()
            return line.strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    def print_status(self, message: str):
        """Print a status message"""
        print(f"\n[Talker] {message}")

    def print_response(self, response: str):
        """Print system response"""
        print(response, end="", flush=True)


def get_input_handler(use_prompt_toolkit: bool = True) -> TalkerInput | FallbackInput:
    """
    Factory function to get appropriate input handler

    Args:
        use_prompt_toolkit: Whether to try using prompt_toolkit

    Returns:
        Appropriate input handler instance
    """
    logger = get_logger()
    if use_prompt_toolkit:
        try:
            return TalkerInput()
        except ImportError as e:
            logger.warning(f"Failed to import prompt_toolkit: {e}, using fallback")
        except Exception as e:
            logger.error(f"Failed to create TalkerInput: {e}, using fallback", exc_info=True)
    return FallbackInput()
