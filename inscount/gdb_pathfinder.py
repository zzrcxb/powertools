#! /usr/bin/env python3

from pathlib import Path
from collections import defaultdict


def bbv_parser(fd) -> list:
    trace = []
    for line in fd:
        record = defaultdict(lambda: 0)
        for bb in line.strip().split():
            bbid, cnt = list(map(int, bb.split(':')[1:]))
            record[bbid] += cnt
        trace.append(record)
    return trace


def brk_parser(fd) -> list:
    brks = []
    for line in fd:
        pc, cnt = line.strip().split()
        brks.append((int(pc, base=16), int(cnt)))
    return brks


def bbid_parser(fd) -> dict:
    id_map = {}
    for line in fd:
        bbid, pc = line.strip().split()
        id_map[int(bbid)] = int(pc, base=16)
    return id_map


def simpt_parser(fd) -> list:
    simpts = []
    for line in fd:
        sid, cnt = line.strip().split()
        simpts.append((int(sid), int(cnt)))
    return simpts


def gdb_sequence_gen(bbv: list, brk: list, bbid_map: dict, simpts: list, max_num: int) -> list:
    breaks_so_far = defaultdict(lambda: 0)

    def accumulate(start, end):
        # includes end!!!
        res = defaultdict(lambda: 0)
        for index in range(start, end + 1):
            for k, v in bbv[index]:
                res[k] += v
        return res


    def search_path(start, end, pc, is_last=False):
        acc_res = accumulate(start, end)
        if is_last:
            assert(pc in acc_res)
            # cnd = breaks_so_far[pc] -
            return [f'b * {pc:#x}', '#ignore {}', 'c']


    cmds = ['b main', 'r']
    simpts = sorted(simpts)
    start_slice = 0
    for pt in simpts:
        slice_id = pt - 1
        if slice_id == -1:  # simpt wants the first
            cmds.append('#ckpt')
            continue
        else:
            cmds.extend(search_path(start_slice, slice_id, *brk[slice_id]))
            start_slice = slice_id + 1






if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('bbv', type=str, help='path to bbv')
    parser.add_argument('brk', type=str, help='path to glibc function black list', default=str(Path(__file__).parent / 'libc.symbols'))
    parser.add_argument('bbid', type=str, help='path to the output file', default='white.list')
    parser.add_argument('-d', '--cwd', type=str, help='current work directory', default='.')
    parser.add_argument('-m', '--max-num', type=int, help='maximum number of breakpoints', default=10)
    args = parser.parse_args()

    # load data
    bbv_path = Path(args.cwd) / args.bbv
    brk_path = Path(args.cwd) / args.brk
    bbid_path = Path(args.cwd) / args.bbid

    with bbv_path.open() as bbv_in, brk_path.open() as brk_in, bbid_path.open() as bbid_in:
        bbv = bbv_parser(bbv_in)
        brk = brk_parser(brk_in)
        bbid = bbid_parser(brk_in)



