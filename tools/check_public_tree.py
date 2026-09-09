"""Check publishable Git files; never print detected sensitive values."""
import ipaddress
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BLOCKED_SUFFIXES = {'.exe', '.dll', '.pdb', '.obj', '.lnk', '.iso', '.dmp', '.pcap',
                    '.pcapng', '.tsv', '.h264', '.ts', '.mp4', '.mkv', '.png', '.jpg', '.log', '.zip'}
PRIVATE_NETS = [ipaddress.ip_network(n) for n in
                ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10', '198.18.0.0/15')]
PATTERNS = [
    ('absolute user profile path', re.compile(r'[A-Za-z]:[\\/]+Users[\\/]+[^\s\"\'<>]+', re.I)),
    ('hardware address', re.compile(r'(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])')),
    ('machine or interface GUID', re.compile(r'(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b')),
    ('private key', re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ('credential-like token', re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,})\b')),
]


def inspect(name, data):
    problems = []
    path = Path(name)
    if path.suffix.lower() in BLOCKED_SUFFIXES or path.name == 'settings.json':
        problems.append((name, 'private/generated file type'))
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return problems + [(name, 'non-UTF8 or binary content')]
    for label, pattern in PATTERNS:
        if pattern.search(text):
            problems.append((name, label))
    for match in re.finditer(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])', text):
        try:
            value = ipaddress.ip_address(match.group())
        except ValueError:
            continue
        # Literal network ranges in this checker describe what to reject, not endpoints.
        if name.replace('\\', '/') == 'tools/check_public_tree.py':
            continue
        if any(value in network for network in PRIVATE_NETS):
            problems.append((name, 'non-public local network address'))
            break
    return problems


def main():
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT)
    names = sorted(set(n.decode('utf-8') for n in names.split(b'\0') if n))
    if not names:
        raise SystemExit('No publishable Git files found.')
    errors = []
    for name in names:
        errors.extend(inspect(name, (ROOT / name).read_bytes()))
    # Also inspect staged blobs so a clean worktree cannot hide a stale staged secret.
    staged = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT)
    for name in [n.decode('utf-8') for n in staged.split(b'\0') if n]:
        blob = subprocess.check_output(['git', 'show', ':' + name], cwd=ROOT)
        errors.extend(inspect(name, blob))
    for name, label in sorted(set(errors)):
        print(f'FAIL {name}: {label}')
    if errors:
        return 1
    print(f'PASS: {len(names)} publishable files and staged blobs checked. Manual review is still required.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
