#! /usr/bin/env python3
import os
import re
import git
import datetime

from pathlib import Path


DEFAULT_REGS = {
    'CR0': 2147483699,
    'DR6': 4294905840,
    'DR7': 1024,
    'M5': 243440,
    'EFER': 19713,
    'ES_ATTR': 46043,
    'CS_ATTR': 43731,
    'SS_ATTR': 46043,
    'DS_ATTR': 46043,
    'FS_ATTR': 46043,
    'GS_ATTR': 46043,
    'HS_ATTR': 46043,
    'TSL_ATTR': 46043,
    'TSG_ATTR': 46043,
    'LS_ATTR': 46043,
    'MS_ATTR': 46043,
    'TR_ATTR': 46043,
    'IDTR_ATTR': 46043,
    'APIC_BASE': 4276094976
}

PAGE_SIZE = 4 * 1024


def parse_map(args):
    pid = args.pid
    root_dir = args.root_dir
    pattern = "\\s*([0-9a-f]+)-([0-9a-f]+)\\s+[^\\s]+\\s+[^\\s]+\\s+[^\\s]+\\s+[^\\s]+\\s*([^\\s]*)"
    print(root_dir)
    with open(f'/proc/{pid}/maps') as f, open(root_dir / 'map.out', 'w') as out:
        for line in f:
            match = re.findall(pattern, line)
            if len(match) == 1:
                start = int(match[0][0], base=16)
                end = int(match[0][1], base=16)
                path = match[0][2]
                if start < 0x7fff00000000 or path in {'[vvar]', '[vdso]', '[stack]'}:
                    out.write(f'{start:#x} {end:#x} {path}\n')


def convert_from_raw(args):
    root_dir = args.root_dir
    regvals = DEFAULT_REGS

    if os.path.exists(root_dir / 'm5.cpt'):
        return

    with open(root_dir / 'm5.cpt.regs') as fin:
        for line in fin:
            name, val = line.strip().split(':')
            regvals[name] = int(val)
    regvals['FS_EFF_BASE'] = regvals['SEG_FS_BASE']

    stack_start = None
    stack_end = None
    mappings = []
    with open(root_dir / 'maps') as fin:
        for line in fin:
            if len(line.strip().split()) == 3:
                start, end, path = line.strip().split()
            else:
                start, end = line.strip().split()
                path = ''
            mappings.append((int(start, base=16), int(end, base=16), path))
            if path == '[stack]':
                stack_start = mappings[-1][0]
                stack_end = mappings[-1][1]

    page_table = []
    paddr = 0
    for seg in mappings:
        for vaddr in range(seg[0], seg[1], PAGE_SIZE):
            page_table.append((vaddr, paddr))
            paddr += PAGE_SIZE

    page_table_str = []
    for idx, (vaddr, paddr) in enumerate(page_table):
        page_table_str.append(
            f'[system.cpu.workload.Entry{idx}]\n'
            f'vaddr={vaddr}\n'
            f'paddr={paddr}\n'
            f'flags=0\n'
        )

    repo = git.Repo(path=__file__, search_parent_directories=True)
    repo_head = repo.head.object.hexsha

    with open(Path(__file__).parent / 'm5-2.cpt.template') as fin:
        with open(root_dir / 'm5.cpt', 'w') as out:
            text = fin.read()
            text = text.format(
                timeNow=str(datetime.datetime.now(datetime.timezone.utc)),
                repoHEAD=repo_head,
                fp_regs=get_fp_str(regvals),
                int_regs=get_int_str(regvals),
                pc=regvals['PC'],
                npc=regvals['NPC'],
                sbrk=regvals['SBRK'],
                stack_base=stack_end,
                stack_size=stack_end - stack_start,
                stack_min=stack_start,
                pagetable_size=len(page_table),
                page_table='\n'.join(page_table_str),
                isa_regs=get_isa_str(regvals),
                mem_size=4*1024*1024*1024
            )
            out.write(text)

    pmem_path = root_dir / 'system.physmem.store0.pmem'
    os.system(f'truncate -s4294967296 {pmem_path}')
    os.system(f'gzip {pmem_path}')
    os.system(f'mv {pmem_path}.gz {pmem_path}')


def get_int_str(regvals: dict):
    regs = ['RAX', 'RCX', 'RDX', 'RBX', 'RSP', 'RBP', 'RSI', 'RDI',
            'R8',  'R9',  'R10', 'R11', 'R12', 'R13', 'R14', 'R15']
    reg_str = ' '.join([str(regvals.get(r, 0)) for r in regs])
    reg_str += ' 0' * 22
    return reg_str


def get_fp_str(regvals: dict):
    reg_str = '0 ' * 8

    regs = []
    for i in range(8):
        regs.append(f'FPR{i}')

    for i in range(16):
        regs.append(f'XMM{i}_HIGH')
        regs.append(f'XMM{i}_LOW')

    for i in range(8):
        regs.append(f'MICROFP{i}')

    reg_str += ' '.join([str(regvals.get(r, 0)) for r in regs])
    return reg_str


def get_isa_str(regvals):
    regs = []
    reg_str = ''
    regs.extend([f'CR{i}' for i in range(16)])
    regs.extend([f'DR{i}' for i in range(8)])
    regs.extend(['RFLAGS', 'M5', 'TSC', 'MTRRCAP', 'SYSENTER_CS',
                 'SYSENTER_ESP', 'SYSENTER_EIP', 'MCG_CAP', 'MCG_STATUS',
                 'MCG_CTL', 'DEBUG_CTL_MSR', 'LBFI', 'LBTI', 'LEFI', 'LETI'])
    regs.extend([f'MTRR_PHYS_BASE{i}' for i in range(8)])
    regs.extend([f'MTRR_PHYS_MASK{i}' for i in range(8)])
    regs.extend([f'MTRR_FIX{i}' for i in range(11)])
    regs.extend(['PAT', 'DEF_TYPE'])
    regs.extend([f'MC{i}_CTL' for i in range(8)])
    regs.extend([f'MC{i}_STATUS' for i in range(8)])
    regs.extend([f'MC{i}_ADDR' for i in range(8)])
    regs.extend([f'MC{i}_MISC' for i in range(8)])
    regs.extend(['EFER', 'STAR', 'LSTAR', 'CSTAR', 'SF_MASK',
                 'KERNEL_GS_BASE', 'TSC_AUX'])
    regs.extend([f'PERF_EVT_SEL{i}' for i in range(4)])
    regs.extend([f'PERF_EVT_CTR{i}' for i in range(4)])
    regs.extend(['SYSCFG', 'IORR_BASE0', 'IORR_BASE1', 'IORR_MASK0',
                 'IORR_MASK1', 'TOP_MEM', 'TOP_MEM2', 'VM_CR', 'IGNNE',
                 'SMM_CTL', 'VM_HSAVE_PA', 'SEG_ES', 'SEG_CS', 'SEG_SS',
                 'SEG_DS', 'SEG_FS', 'SEG_GS', 'SEG_HS', 'TSL', 'TSG',
                 'LS', 'MS', 'TR', 'IDTR', 'SEG_ES_BASE', 'SEG_CS_BASE',
                 'SEG_SS_BASE', 'SEG_DS_BASE', 'SEG_FS_BASE',
                 'SEG_GS_BASE', 'SEG_HS_BASE', 'TSL_BASE', 'TSG_BASE',
                 'LS_BASE', 'MS_BASE', 'TR_BASE', 'IDTR_BASE',
                 'ES_EFF_BASE', 'CS_EFF_BASE', 'SS_EFF_BASE',
                 'DS_EFF_BASE', 'FS_EFF_BASE', 'GS_EFF_BASE',
                 'HS_EFF_BASE', 'TSL_EFF_BASE', 'TSG_EFF_BASE',
                 'LS_EFF_BASE', 'MS_EFF_BASE', 'TR_EFF_BASE',
                 'IDTR_EFF_BASE', 'ES_LIMIT', 'CS_LIMIT', 'SS_LIMIT',
                 'DS_LIMIT', 'FS_LIMIT', 'GS_LIMIT', 'HS_LIMIT',
                 'TSL_LIMIT', 'TSG_LIMIT', 'LS_LIMIT', 'MS_LIMIT',
                 'TR_LIMIT', 'IDTR_LIMIT', 'ES_ATTR', 'CS_ATTR',
                 'SS_ATTR', 'DS_ATTR', 'FS_ATTR', 'GS_ATTR', 'HS_ATTR',
                 'TSL_ATTR', 'TSG_ATTR', 'LS_ATTR', 'MS_ATTR', 'TR_ATTR',
                 'IDTR_ATTR', 'X87_TOP', 'MXCSR', 'FCW', 'FSW', 'FTW',
                 'FPTAG', 'FISEG', 'FIOFF', 'FOSEG', 'FOOFF', 'FPOPCODE',
                 'APIC_BASE', 'PCI_CONFIG_ADDRESS'])
    # for i, r in enumerate(regs):
        # print(i, ':', r, regvals.get(r, -1))
    reg_str += ' '.join([str(regvals.get(r, 0)) for r in regs])
    return reg_str


if __name__ == '__main__':
    import sys
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('root_dir', action='store', type=Path)
    subparsers = parser.add_subparsers(help='sub-command help')

    map_parser = subparsers.add_parser('map', help='Get map for pid')
    map_parser.add_argument('pid', action='store', type=int)
    map_parser.set_defaults(func=parse_map)

    convert_parser = subparsers.add_parser('convert', help='Convert ckpt')
    convert_parser.set_defaults(func=convert_from_raw)

    args = parser.parse_args()
    args.func(args)
