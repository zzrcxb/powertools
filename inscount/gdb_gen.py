#! /usr/bin/env python3

import sys

from pathlib import Path
from collections import defaultdict, namedtuple
from math import inf

WayPoint = namedtuple('WayPoint', 'slice_num pc rel_cnt abs_cnt ctx')
SimPoint = namedtuple('SimPoint', 'simpt_id slice_num ctx')


class PathFinder:
    def __init__(self, bbv_path, brk_path, bbid_path, interval, args):
        with bbid_path.open() as f:
            self.bbid = PathFinder.bbid_parser(f)
        with bbv_path.open() as f:
            self.bbv = self.bbv_parser(f)
        with brk_path.open() as f:
            self.brk = PathFinder.brk_parser(f)

        self.interval = interval
        self.ctx_cache = {-1: defaultdict(lambda: 0)}
        if args.tradition:
            self.waypoints = self.gen_waypoints()

    def gen_waypoints(self):
        waypoints = []
        for start_index in range(0, len(self.bbv), self.interval):
            end_index = start_index + self.interval - 1  # include end_index
            if end_index >= len(self.bbv):
                end_index = len(self.bbv) - 1
            if len(waypoints) == 0:
                ctx = self.get_ctx(-1)
            else:
                last_wp = waypoints[-1]
                ctx = last_wp.ctx
            # search for the "shortest path"
            way_index = None
            min_cnt = inf
            for i in range(start_index, end_index + 1):
                brk_pc, brk_cnt = self.brk[i]
                diff = brk_cnt - ctx.get(brk_pc, 0)
                if diff < min_cnt and diff > 0:
                    way_index = i
                    min_cnt = diff
            new_ctx = self.get_ctx(way_index)
            waypoints.append(WayPoint(slice_num=way_index, pc=self.brk[way_index][0], rel_cnt=min_cnt, abs_cnt=self.brk[way_index][1], ctx=new_ctx))
            print(f'gen waypoint from {start_index} to {end_index}', waypoints[-1].slice_num, hex(waypoints[-1].pc), waypoints[-1].abs_cnt, waypoints[-1].rel_cnt, file=sys.stderr)
        return {wp.slice_num: wp for wp in waypoints}

    def get_path(self, slice_nums):
        results = []
        wayp_nums = sorted([wp for wp in self.waypoints])
        wp_iter = iter(wayp_nums)
        wp = next(wp_iter)
        for sid, snum in slice_nums:
            while wp < snum:
                results.append(self.waypoints[wp])
                wp = next(wp_iter)
            results.append(SimPoint(simpt_id=sid, slice_num=snum, ctx=self.get_ctx(snum)))
        return results

    def search_waypoint(self, start, end):
        # search a waypoint based on the context at start, so the search range is start+1 -> end (included)
        ctx = self.get_ctx(start)
        way_index = None
        min_cnt = inf
        for i in range(start + 1, end + 1):
            brk_pc, brk_cnt = self.brk[i]
            diff = brk_cnt - ctx.get(brk_pc, 0)
            if diff < min_cnt and diff > 0:
                way_index = i
                min_cnt = diff
        new_ctx = self.get_ctx(way_index)
        wp = WayPoint(slice_num=way_index, pc=self.brk[way_index][0], rel_cnt=min_cnt, abs_cnt=self.brk[way_index][1], ctx=new_ctx)
        return wp

    def binary_search(self, start, slice_num, simpt_id, threshold=1000000):
        waypoints = []
        end = slice_num
        brk_pc, brk_cnt = self.brk[end]

        ctx = self.get_ctx(start)
        wp_start = start
        while brk_cnt - ctx.get(brk_pc, 0) > threshold and wp_start < end - 1:
            print(f'searching... {wp_start}-{end-1}, size={len(waypoints)}')
            wp = self.search_waypoint(wp_start, end - 1)
            waypoints.append(wp)
            ctx = wp.ctx
            wp_start = wp.slice_num
        waypoints.append(SimPoint(simpt_id=simpt_id, slice_num=slice_num, ctx=self.get_ctx(end)))
        return waypoints

    def get_ctx(self, index):
        # get the context until index (included)
        if index not in self.ctx_cache:
            # search for nearest startpoint in cache
            start_point = min([s for s in self.ctx_cache if s < index], key=lambda x: index - x)
            self.ctx_cache[index] = self._acc(start_point, index)
        return self.ctx_cache[index]

    def _acc(self, start, end):
        # include end
        accumulator = dict(self.ctx_cache[start])
        for i in range(start + 1, end + 1):
            for k, v in self.bbv[i].items():
                if k in accumulator:
                    accumulator[k] += v
                else:
                    accumulator[k] = v
        return accumulator

    def bbv_parser(self, fd) -> list:
        trace = []
        for line in fd:
            record = defaultdict(lambda: 0)
            for bb in line.strip().split():
                bbid, cnt = list(map(int, bb.split(':')[1:]))
                record[self.bbid[bbid]] += cnt  # convert bbid to PC
            trace.append(record)
        return trace

    @staticmethod
    def brk_parser(fd) -> list:
        brks = []
        for line in fd:
            pc, cnt = line.strip().split()
            brks.append((int(pc, base=16), int(cnt)))
        return brks

    @staticmethod
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--bbv', type=str, help='path to bbv', default='out.bb')
    parser.add_argument('--brk', type=str, help='path to glibc function black list', default='out.brk')
    parser.add_argument('--bbid', type=str, help='path to the output file', default='out.bbid')
    parser.add_argument('--simpt', type=str, help='path to the output file', default='results.simpts')
    parser.add_argument('--output', type=str, help='gdb commands', default='gdb.cmd')
    parser.add_argument('-d', '--cwd', type=str, help='current work directory', default='.')
    parser.add_argument('-i', '--interval', type=int, help='maximum number of breakpoints', default=300)
    parser.add_argument('-t', '--threshold', type=int, help='maximum ignores', default=1000000)
    parser.add_argument('-T', '--tradition', action='store_true', help='use tradition mode')
    args = parser.parse_args()

    # load data
    cwd = Path(args.cwd).resolve()
    bbv_path   = cwd / args.bbv
    brk_path   = cwd / args.brk
    bbid_path  = cwd / args.bbid
    simpt_path = cwd / args.simpt
    out_path   = cwd / args.output

    pf = PathFinder(bbv_path, brk_path, bbid_path, args.interval, args)

    with simpt_path.open() as simpt_in:
        simpts = simpt_parser(simpt_in)
    simpts = sorted(simpts, key=lambda x: x[0])

    cmds = []
    slice_nums = []
    for slice_num, simpt_id in simpts:
        if slice_num == 0:
            cmds += [f'#ckpt@{simpt_id}']
        else:
            slice_nums.append((simpt_id, slice_num - 1))

    if args.tradition:
        path = pf.get_path(slice_nums)
    else:
        path = []
        start = -1
        for simpt_id, slice_num in slice_nums:
            path.extend(pf.binary_search(start, slice_num, simpt_id, args.threshold))
            start = slice_num

    skip_cnt = 1
    total_ignore = 0
    for index, ckpt in enumerate(path):
        if isinstance(ckpt, WayPoint):
            ctx = defaultdict(lambda: 0) if index == 0 else path[index - skip_cnt].ctx
            brk_pc, brk_cnt = ckpt.pc, ckpt.abs_cnt
            brk_cnt = brk_cnt - ctx.get(brk_pc, 0)
            if brk_cnt > 0:
                cmds += [f'break * {brk_pc:#x}']
                if brk_cnt > 1:
                    cmds.append(f'#ignore@{brk_cnt}')
                    total_ignore += brk_cnt
                cmds += ['c', 'delete']
                skip_cnt = 1
            else:
                skip_cnt += 1
        elif isinstance(ckpt, SimPoint):
            ctx = defaultdict(lambda: 0) if index == 0 else path[index - skip_cnt].ctx
            brk_pc, brk_cnt = pf.brk[ckpt.slice_num]
            print(ckpt.simpt_id, ckpt.slice_num, hex(brk_pc), brk_cnt, ctx.get(brk_pc, 0), file=sys.stderr)
            brk_cnt = brk_cnt - ctx.get(brk_pc, 0)
            assert brk_cnt > 0
            cmds.append(f'break * {brk_pc:#x}')
            if brk_cnt > 1:
                cmds.append(f'#ignore@{brk_cnt}')
                total_ignore += brk_cnt
            cmds += ['c', f'#ckpt@{ckpt.simpt_id}', 'delete']
            skip_cnt = 1

    print(f'Ignore {total_ignore // 1000000}M times in total')
    with out_path.open('w') as f:
        f.write('\n'.join(cmds))
