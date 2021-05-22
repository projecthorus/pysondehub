import json
import sondehub
import argparse
import os
import sys
import time

unbuffered = os.fdopen(sys.stdout.fileno(), "wb", 0)


def on_message(message):
    unbuffered.write(json.dumps(message).encode())
    unbuffered.write("\n".encode())


def main():

    parser = argparse.ArgumentParser(description="Sondehub CLI")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--serial",
        dest="sondes",
        default=["#"],
        nargs="*",
        help="Filter to sonde serial",
        type=str,
        action="append",
    )
    group.add_argument(
        "--download",
        dest="download",
        default=[],
        nargs="*",
        help="Sondes to download from open data",
        type=str,
        action="append",
    )
    args = parser.parse_args()
    if (args.download):
        serials = [item for sublist in args.download for item in sublist]
        for serial in serials:
            for frame in sondehub.download(serial=serial):
                on_message(frame)
        return
    if (
        len(args.sondes) > 1
    ):  # we need to drop the default value if the user specifies specific sondes
        args.sondes = args.sondes[1:]
    sondes = [item for sublist in args.sondes for item in sublist]
    test = sondehub.Stream(on_message=on_message, sondes=sondes, auto_start_loop=False)
    test.loop_forever()


if __name__ == "__main__":
    main()
