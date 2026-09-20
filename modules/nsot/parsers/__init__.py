"""nsot.parsers — config → host_vars, one module per platform.

A new vendor is a new module here plus a template directory. That is the
multi-vendor story: adding support is a configuration and plugin change, not a
change to the extraction engine.
"""

from modules.nsot.parsers.base import BaseParser, ConfigBlock, split_blocks
from modules.nsot.parsers.cisco_ios import CiscoIosParser
from modules.nsot.parsers.cisco_iosxe import CiscoIosXeParser

#: Settings platform slug → parser class.
REGISTRY = {
    "cisco_ios":   CiscoIosParser,
    "cisco-ios":   CiscoIosParser,
    "cisco_xe":    CiscoIosXeParser,
    "cisco_iosxe": CiscoIosXeParser,
    "cisco-ios-xe": CiscoIosXeParser,
}

DEFAULT_PARSER = CiscoIosParser


def get_parser(platform: str):
    """Return a parser instance for *platform*, defaulting to IOS."""
    cls = REGISTRY.get((platform or "").strip().lower(), DEFAULT_PARSER)
    return cls()


__all__ = ["BaseParser", "ConfigBlock", "split_blocks", "CiscoIosParser",
           "CiscoIosXeParser", "REGISTRY", "get_parser", "DEFAULT_PARSER"]
