"""
babel.messages
~~~~~~~~~~~~~~

Support for ``gettext`` message catalogs.

:copyright: (c) 2013-2026 by the Babel Team.
:license: BSD, see LICENSE for more details.
"""

from babel.messages.catalog import (
    Catalog,
    Message,
    TranslationError,
)
from babel.messages.icu import (
    ICUMessage,
    MessageFormatError,
    compile_message,
    format_message,
)

__all__ = [
    "Catalog",
    "ICUMessage",
    "Message",
    "MessageFormatError",
    "TranslationError",
    "compile_message",
    "format_message",
]
