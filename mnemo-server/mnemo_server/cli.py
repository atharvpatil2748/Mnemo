"""Explicit Mnemo setup commands."""

import argparse
from pathlib import Path

from .tokenizer_provisioning import provision_tokenizer


def main() -> int:
    """Run the Mnemo installation/deployment command line."""
    parser = argparse.ArgumentParser(prog="mnemo")
    commands = parser.add_subparsers(dest="command", required=True)
    provision = commands.add_parser(
        "provision-tokenizer", help="install the canonical tokenizer asset"
    )
    provision.add_argument("--from-file", type=Path, help="import an independently obtained asset")
    provision.add_argument("--data-root", type=Path, help="override local data root")
    arguments = parser.parse_args()
    if arguments.command == "provision-tokenizer":
        path = provision_tokenizer(source=arguments.from_file, data_root=arguments.data_root)
        print(path)
        return 0
    parser.error("unsupported command")
    return 2
