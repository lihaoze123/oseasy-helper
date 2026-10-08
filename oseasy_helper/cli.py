"""The public CLI. Video, integrated client and local control commands."""
import argparse
import ipaddress
import sys

from . import client, control, video


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


def positive_seconds(value):
    try:
        number = float(value)
        if 0.1 <= number <= 300:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError('Expected seconds in 0.1..300')


def mac_address(value):
    import re
    value = value.replace('-', ':').upper()
    if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', value):
        raise argparse.ArgumentTypeError('Expected a six-byte MAC address')
    return value


def parser():
    root = argparse.ArgumentParser(
        prog="oseasy-helper", description="Receive classroom video/files; manage the local student service.")
    commands = root.add_subparsers(dest="command", required=True)
    live = commands.add_parser("video", help="Expose a local MPEG-TS URL (Ctrl+C stops)",
        description="Reassemble UDP H.264 and serve http://127.0.0.1:17778/live.ts. "
                    "Your player decodes the video. No window or FFmpeg dependency.")
    live.add_argument("--teacher", type=ipv4, required=True,
                      help="Teacher's source IPv4; multicast group is derived automatically")
    live.add_argument("--local", type=ipv4, required=True, help="IPv4 address of your classroom-facing adapter")
    live.add_argument("--udp-port", type=port, default=7778, help="Destination UDP port (default: 7778)")
    live.add_argument("--http-port", type=port, default=17778, help="Local playback port (default: 17778)")
    for command in ('student', 'client'):
        login = commands.add_parser(command, help=("Login, video and files in one process" if command == 'student'
                                                   else "Login and file receiver"),
            description="Receive classroom broadcasts/files with management reconnection. "
                        "Default thumbnails are a fixed MOCK test image; teacher online status requires field validation.")
        login.add_argument("--teacher", type=ipv4, required=True)
        login.add_argument("--local", type=ipv4, required=True)
        login.add_argument("--port", type=port, default=9003)
        login.add_argument("--receive-dir", default="received",
                       help="Receiving directory (default: received)")
        login.add_argument("--node-port", type=port, default=8555)
        login.add_argument("--data-port", type=port, default=9100)
        login.add_argument("--mock-thumbnail", action=argparse.BooleanOptionalAction, default=True,
                           help="Reply with a fixed MOCK test image (default: enabled)")
        login.add_argument('--video', dest='with_video', action=argparse.BooleanOptionalAction,
                           default=(command == 'student'), help='Serve video at a local playback URL')
        login.add_argument('--udp-port', type=port, default=7778)
        login.add_argument('--http-port', type=port, default=17778)
        login.add_argument('--reconnect-delay', type=positive_seconds, default=5,
                           help='Delay between management/node retries (default: 5 seconds)')
        login.add_argument('--management-idle-timeout', type=positive_seconds, default=60,
                           help='Reconnect after this many seconds with no management data (default: 60)')
        login.add_argument('--once', action='store_true', help='Exit after management disconnect/failure')
        login.add_argument('--name', help='Student computer name (default: local hostname)')
        login.add_argument('--user', help='Student user name (default: local username)')
        login.add_argument('--mac', type=mac_address, help='Adapter MAC identity (default: discover from --local)')
    manage = commands.add_parser("control", help="Windows: inspect, suspend or stop the local student",
        description="Suspend/resume the main student processes, or start/stop MMPC. "
                    "Suspension may eventually time out the teacher connection. No driver or startup changes.")
    manage.add_argument("action", choices=("status", "suspend", "resume", "start", "stop"),
                        help="status is read-only; other actions require an administrator terminal")
    return root


def main(argv=None):
    root = parser()
    args = root.parse_args(argv)
    try:
        if args.command in ("video", "client", "student"):
            for name in ("teacher", "local"):
                address = ipaddress.IPv4Address(getattr(args, name))
                if address.is_unspecified or address.is_multicast or address.is_reserved:
                    raise ValueError(f"--{name} must be a unicast interface address")
            if args.command in ("client", "student"):
                client.run(args)
            else:
                video.receive(args)
        else:
            control.run(args.action)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
