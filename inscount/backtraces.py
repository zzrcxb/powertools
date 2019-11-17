import re
import sys

try:
    import gdb  # pylint: disable=import-error
except ImportError:
    print('This is a GDB Python script that cannot be directly invoked.', file=sys.stderr)
    exit(1)


def brk_parser(fd) -> list:
    brks = []
    for line in fd:
        pc, cnt = line.strip().split()
        brks.append((int(pc, base=16), int(cnt)))
    return brks


def simpt_parser(fd) -> list:
    simpts = []
    for line in fd:
        sid, cnt = line.strip().split()
        simpts.append((int(sid), int(cnt)))
    return simpts


def get_bt(pc):
    gdb.execute(f'b * {pc:#x}')
    gdb.execute(f'r')
    res = gdb.execute(f'bt', to_string=True)
    print(res, file=sys.stderr)
    bt = []
    pattern = r'\#([0-9]+) +(0x[0-9a-fA-F]+)'
    for entries in re.findall(pattern, res):
        stack_depth, pc = int(entries[0]), int(entries[1], base=16)
        bt.append((stack_depth, pc))
    bt = [pc for _, pc in sorted(bt, key=lambda x: x[0], reverse=True)]
    return bt


if __name__ == "__main__":
    brk_path = 'out.brk'
    simpt_path = 'results.simpts'
    output = 'backtrace.out'

    with open(brk_path) as brk_in, open(simpt_path) as simpt_in:
        brks = brk_parser(brk_in)
        simpts = simpt_parser(simpt_in)

    pcs = {brks[sid - 1][0] for sid, _ in simpts if sid > 0}

    traces = {pc: get_bt(pc) for pc in pcs}

    with open(output, 'w') as out:
        simpts = sorted(simpts, key=lambda x: x[1])
        for s_cnt, simpt_id in simpts:
            if s_cnt == 0:
                out.write(f'{simpt_id} {s_cnt} 0 0\n')
            else:
                pc, cnt = brks[s_cnt - 1]
                trace = traces[pc]
                out.write('{} {} {:#x} {} {}\n'.format(simpt_id, s_cnt, pc, cnt, ' '.join(map(lambda s: f'{s:#x}', trace))))
