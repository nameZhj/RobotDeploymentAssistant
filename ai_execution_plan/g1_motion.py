"""Send original TARGETS|COMMAND lines over Wi-Fi UDP or the CH32 LoRa bridge.

Example: --udp 192.168.31.34 --send DANCE,G1_TIKTOK
Wi-Fi control does not use SSH. Motion commands are sent once.
"""
import argparse
import re
import socket
import sys
import time

from g1_wifi_setup import DEFAULT_SERIAL_PORT
from lora_link import SerialTransport, LinkError


def packet(target, command):
    target = target.strip().upper()
    command = command.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]+(?:,[A-Z0-9_-]+)*", target):
        raise ValueError("Target must be A, A,B or ALL")
    if not command or any(ord(c) < 32 or ord(c) > 126 or c == '|' for c in command):
        raise ValueError("Command must be one printable ASCII line without |")
    if command.split(',', 1)[0] == 'GETDANCELIST':
        raise ValueError("GETDANCELIST radio replies are not supported by this motion bridge")
    result = (target + '|' + command + '\n').encode('ascii')
    if len(result) > 192:
        raise ValueError("Packet exceeds 192 bytes including the newline")
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--port', '--serial-port', default=DEFAULT_SERIAL_PORT)
    mode.add_argument('--udp', metavar='ROBOT_IP', help='Use direct IPv4 UDP over Wi-Fi')
    p.add_argument('--baud', type=int, default=9600)
    p.add_argument('--udp-port', type=int, default=8899, help='Robot UDP port (default 8899)')
    p.add_argument('--source-ip', default='0.0.0.0', help='PC Wi-Fi IPv4 (default: selected by routing)')
    p.add_argument('--source-port', type=int, default=8899, help='PC UDP port (default 8899)')
    p.add_argument('--target', default='A', help='A (default), A,B, or ALL')
    action = p.add_mutually_exclusive_group()
    action.add_argument('--send', help='Send one original command; omit for interactive input')
    action.add_argument('--probe', action='store_true', help='Check UDP reachability without triggering motion')
    p.add_argument('--dry-run', action='store_true', help='Print the packet without opening a connection')
    args = p.parse_args(argv)
    if args.probe and not args.udp:
        p.error('--probe requires --udp')
    if args.probe and (',' in args.target or args.target.strip().upper() == 'ALL'):
        p.error('--probe requires a single robot ID')
    if args.udp and not all(1 <= port <= 65535 for port in (args.udp_port, args.source_port)):
        p.error('UDP ports must be between 1 and 65535')

    transport = None
    udp = None
    last_write = None
    drain_seconds = 0.0
    try:
        # Validate one-shot input before opening the port.
        command = 'PING' if args.probe else args.send
        pending = packet(args.target, command) if command is not None else None
        if not args.dry_run:
            if args.udp:
                udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp.bind((args.source_ip, args.source_port))
                udp.connect((args.udp, args.udp_port))
                udp.settimeout(2.0)
            else:
                transport = SerialTransport.open(args.port, args.baud)
        route = 'UDP {}:{}'.format(args.udp, args.udp_port) if args.udp else args.port
        print('Target={} | {} | q: exit'.format(args.target, 'DRY RUN' if args.dry_run else route))
        if pending is None:
            print('STAND | PASSIVE | GAIT | FORWARD,0.2 | BACKWARD,0.2 | TURN_LEFT,0.2 | STOP | DANCE,<alias>')
        while True:
            if pending is None:
                try:
                    command = input('motion> ').strip()
                except EOFError:
                    break
                if command.lower() in ('q', 'quit', 'exit'):
                    break
                if not command:
                    continue
                try:
                    pending = packet(args.target, command)
                except ValueError as exc:
                    print(str(exc), file=sys.stderr)
                    continue
            if udp and udp.send(pending) != len(pending):
                raise OSError('Incomplete UDP send; command was not retried')
            if transport and transport.write(pending) != len(pending):
                raise OSError('Incomplete serial write; command was not retried')
            if transport:
                last_write = time.monotonic()
                # UART flush only drains the USB serial adapter. The E22 may
                # still be sending RF bytes when Windows closes DTR/RTS.
                # Allow its slowest air rate plus packetization before closing.
                drain_seconds = max(1.5, len(pending) * 8.0 / 300.0 + 0.5)
            if args.probe and udp:
                expected = (args.target.strip().upper() + '|PONG\n').encode('ascii')
                try:
                    response = udp.recv(192)
                except socket.timeout as exc:
                    raise OSError('No PONG within 2 s; check Wi-Fi, the receiver and PC source address/port') from exc
                if response != expected:
                    raise OSError('Unexpected reply to PING: {!r}'.format(response))
                print('Robot {} replied PONG via UDP'.format(args.target.strip().upper()))
            else:
                prefix = 'DRY RUN: ' if args.dry_run else '[{}] Sent (execution unconfirmed): '.format(time.strftime('%H:%M:%S'))
                print(prefix + pending.decode().rstrip())
            if args.send is not None or args.probe:
                break
            pending = None
        return 0
    except (LinkError, OSError, ValueError) as exc:
        print('Motion sender: {}'.format(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nExited. No automatic STOP was transmitted.')
        return 130
    finally:
        if udp:
            udp.close()
        if transport:
            if last_write is not None:
                remaining = last_write + drain_seconds - time.monotonic()
                if remaining > 0:
                    print('Waiting {:.1f}s for radio transmit before releasing the port...'.format(remaining), file=sys.stderr)
                    try:
                        time.sleep(remaining)
                    except KeyboardInterrupt:
                        pass
            transport.close()


if __name__ == '__main__':
    sys.exit(main())
