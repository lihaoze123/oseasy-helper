"""The public CLI. Video and local control are independent commands."""
import argparse
import ipaddress
import sys

from . import control, video


def ipv4(value):
    try:
        return str(ipaddress.IPv4Address(value))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected an IPv4 address") from error


def port(value):
    try:
        number = int(value)
        if 1 <= number <= 65535:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Port must be 1..65535")


def parser():
    root = argparse.ArgumentParser(
        prog="oseasy-helper", description="Receive classroom video; manage the local student service.")
    commands = root.add_subparsers(dest="command", required=True)
    live = commands.add_parser("video", help="Expose a local MPEG-TS URL (Ctrl+C stops)",
        description="Reassemble UDP H.264 and serve http://127.0.0.1:17778/live.ts. "
                    "Your player decodes the video. No window or FFmpeg dependency.")
    live.add_argument("--teacher", type=ipv4, required=True,
                      help="Teacher's source IPv4; multicast group is derived automatically")
    live.add_argument("--local", type=ipv4, required=True, help="IPv4 address of your classroom-facing adapter")
    live.add_argument("--udp-port", type=port, default=7778, help="Destination UDP port (default: 7778)")
    live.add_argument("--http-port", type=port, default=17778, help="Local playback port (default: 17778)")
    manage = commands.add_parser("control", help="Windows: status/start/stop of the local student",
        description="Manage MMPC and student processes. stop disconnects the original student; "
                    "it does NOT keep it online with all input control blocked. No driver or startup changes.")
    manage.add_argument("action", choices=("status", "start", "stop"),
                        help="status is read-only; start/stop require an administrator terminal")
    return root


def main(argv=None):
    root = parser()
    args = root.parse_args(argv)
    try:
        if args.command == "video":
            for name in ("teacher", "local"):
                address = ipaddress.IPv4Address(getattr(args, name))
                if address.is_unspecified or address.is_multicast or address.is_reserved:
                    raise ValueError(f"--{name} must be a unicast interface address")
            video.receive(args)
        else:
            control.run(args.action)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
