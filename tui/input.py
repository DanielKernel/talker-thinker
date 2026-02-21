"""
Prompt Toolkit based input handler for Talker-Thinker

Provides Chinese-friendly input with:
- Proper UTF-8 character deletion (one backspace = one Chinese character)
- Command history browsing (up/down arrows)
- Auto-suggestion from history
- File-based history persistence
"""

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
        self.history_file = history_file
        self._key_bindings = create_key_bindings()
        self._history = FileHistory(history_file)

    def get_input(self, session_id: str = None) -> str:
        """
        Get user input with TUI support

        Args:
            session_id: Optional session ID (not used for input, but kept for API compatibility)

        Returns:
            User input string
        """
        import time

        now = time.time()
        timestamp = time.strftime("%H:%M:%S", time.localtime(now))
        ms = int((now % 1) * 1000)
        timestamp_formatted = f"{timestamp}.{ms:03d}"

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
            return ""
        except KeyboardInterrupt:
            # Handle Ctrl+C
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

    def get_input(self, session_id: str = None) -> str:
        """Get user input using native input()"""
        import time
        loop = None
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

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


# Import asyncio for fallback
import asyncio


def get_input_handler(use_prompt_toolkit: bool = True) -> TalkerInput | FallbackInput:
    """
    Factory function to get appropriate input handler

    Args:
        use_prompt_toolkit: Whether to try using prompt_toolkit

    Returns:
        Appropriate input handler instance
    """
    if use_prompt_toolkit:
        try:
            return TalkerInput()
        except ImportError:
            pass
    return FallbackInput()
