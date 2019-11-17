#! /usr/bin/env python3

import subprocess

from pathlib import Path

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('infile', type=str, help='input executable')
    parser.add_argument('-c', '--libc', type=str, help='path to glibc function black list', default=str(Path(__file__).parent / 'libc.symbols'))
    parser.add_argument('-o', '--output', type=str, help='path to the output file', default='white.list')
    parser.add_argument('-d', '--cwd', type=str, help='current work directory', default='.')
    args = parser.parse_args()

    infile = args.cwd / Path(args.infile)
    blacklist_file = args.cwd / Path(args.libc)
    whitelist_file = args.cwd / Path(args.output)

    with blacklist_file.open() as f:
        blacklist = {l.strip() for l in f}

    with whitelist_file.open('w') as f:
        p = subprocess.Popen(['nm', str(infile)], stdout=subprocess.PIPE)
        stdout_b, _ = p.communicate()
        stdout = stdout_b.decode('utf8')
        for line in stdout.split('\n'):
            splitted = line.split()
            if len(splitted) == 3 and splitted[1].lower() == 't' and splitted[2] not in blacklist:
                pc = int(splitted[0], base=16)
                f.write('{:#x}\n'.format(pc))
