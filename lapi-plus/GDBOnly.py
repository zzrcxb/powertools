import re
import os
import sys
import git
import json
import shutil
import struct
import logging
import resource
import datetime
import fileinput
import subprocess

from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from CheckpointConvert import convert_checkpoint
from CheckpointTemplate import MemoryMapping, RegisterValues, fill_checkpoint_template
from Checkpoints import GDBCheckpoint

try:
    import gdb  # pylint: disable=import-error
except ImportError:
    print('This is a GDB Python script that cannot be directly invoked.', file=sys.stderr)
    exit(1)


class CONFIGS:
    PORT_INFO_FILENAME = '.portinfo'
    PIN_INFO_FILENAME  = '.pininfo'
    PMEM_FILENAME      = 'system.physmem.store0.pmem'
    M5CPT_FILENAME     = 'm5.cpt'
    MMAP_FILENAME      = 'mappings.json'
    COREDUMP_FILENAME  = 'pinGDB.core'
    CHECKSUM_FILENAME  = '.checksum'
    PINTOOL_PLUGIN     = 'brkpt.so'
    DEFAULT_PIN_VER    = 'pin-3.11'


class GDBEngine:
    ''' This class is used by the gdb process running inside gdb.'''

    # start-address end-address size offset name
    VADDR_REGEX_STRING = r'\s*(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s*(.*)'
    VADDR_REGEX = re.compile(VADDR_REGEX_STRING)

    BAD_MEM_REGIONS = ['[vvar]', '[vsyscall]']

    def __init__(self, cmd: list, ckpt_prefix: Path, run_dir: Path, gdb_script: Path, compress_ckpt=True,
                 mem_size=4*1024*1024*1024, preserve_intermediate=True):
        assert(len(cmd) > 0)
        self.binary = run_dir / cmd[0]
        self.args = cmd[1:]
        assert(self.binary.exists())
        assert(gdb_script.exists())

        self._ckpt_prefix = ckpt_prefix
        self._gdb_script = gdb_script
        self._compress_ckpt = compress_ckpt
        self.mem_size = mem_size
        self._repo = git.Repo(path=__file__, search_parent_directories=True)
        self._preserve_intermediate = preserve_intermediate

        if self._repo.is_dirty():
            logging.warning('Repo is dirty! Are you developping or running final experiments?')

        # gdb.execute('handle SIGSEGV nostop noprint')
        gdb.execute('set follow-fork-mode child')
        gdb.execute('starti')

    def run(self):
        brkpt_num_pattern = r'Breakpoint +([0-9]+)'
        with self._gdb_script.open() as f:
            last_brknum = None
            for gdb_cmd in f:
                gdb_cmd = gdb_cmd.strip()
                if gdb_cmd.startswith('#'):
                    action, args = self._parse_cmd(gdb_cmd)
                    if action == 'ignore':
                        assert(last_brknum is not None)
                        skip = int(args[0])
                        gdb.execute(f'ignore {last_brknum} {skip}')
                    elif action == 'ckpt':
                        ckpt_id = int(args[0])
                        self._create_ckpt(ckpt_id)
                    else:
                        raise RuntimeError(f'Unknown action {gdb_cmd}')
                else:
                    if gdb_cmd.startswith('delete'):
                        last_brknum = None
                        gdb.execute(gdb_cmd)
                    elif gdb_cmd.startswith('break'):
                        res = gdb.execute(gdb_cmd, to_string=True)
                        last_brknum = int(re.findall(brkpt_num_pattern, res)[0])
                        logging.debug(f'BRKPT {last_brknum}')
                        logging.debug(res)
                    else:
                        gdb.execute(gdb_cmd)
        gdb.execute('q')

    def _parse_cmd(self, cmd):
        action, *args = cmd[1:].split('@')
        return action, args

    def _create_ckpt(self, ckpt_id):
        logging.info(f'creating {ckpt_id}')
        ckpt_name = f'cpt.None.SIMP-{ckpt_id}'
        brk_ID = 0
        brk_value = self._get_brk_value()
        fs_base   = self._get_fs_base()
        ckpt_dir    = self._ckpt_prefix / ckpt_name
        pmem_path     = ckpt_dir / CONFIGS.PMEM_FILENAME
        m5cpt_path    = ckpt_dir / CONFIGS.M5CPT_FILENAME
        mmap_path     = ckpt_dir / CONFIGS.MMAP_FILENAME
        coredump_path = ckpt_dir / CONFIGS.COREDUMP_FILENAME

        # check and clear
        if ckpt_dir.exists():
            logging.warning('Checkpoint #{} exists, overwriting!'.format(brk_ID))
            for file in ckpt_dir.glob('*'):  # delete everything
                file.unlink()
        else:
            ckpt_dir.mkdir(parents=True)

        # get program states, including mmap and registers
        mmaps, unexpanded_mmaps = self._create_mappings()
        regs = RegisterValues(fs_base)

        # check if the brkpt is ready to dump
        def ckpt_check():
            current_pc = int(regs.get_pc_string())
            for mapping in unexpanded_mmaps.values():
                if current_pc in mapping and mapping.name in self.BAD_MEM_REGIONS:
                    logging.warning('Skipping checkpoint #{} since current PC {:#} is in {}'.format(
                                    brk_ID, current_pc, mapping.name))
                    return False
            return True
        if not ckpt_check():
            return False

        # get stack mapping
        stack_mapping = [m for v, m in unexpanded_mmaps.items() if 'stack' in m.name]
        assert len(stack_mapping) == 1
        stack_mapping = stack_mapping[0]

        # fill ninja2 template
        fill_checkpoint_template(
            m5cpt_path,
            mappings=mmaps,
            misc_reg_string=regs.get_misc_reg_string(),
            int_reg_string=regs.get_int_reg_string(),
            pc_string=regs.get_pc_string(),
            next_pc_string=regs.get_next_pc_string(),
            float_reg_string=regs.get_float_reg_string(),
            mem_size=self.mem_size,
            stack_mapping=stack_mapping,
            brk=brk_value,
            mmap_end=self.mmap_end,
            timeNow=str(datetime.datetime.now(datetime.timezone.utc)),
            repoHEAD=self._repo.head.object.hexsha)

        self._dump_core_to_file(coredump_path)
        self._dump_mappings_to_file(unexpanded_mmaps, self.mem_size, mmap_path)
        convert_checkpoint(GDBCheckpoint(ckpt_dir, CONFIGS), True, compress=self._compress_ckpt)

        if not self._preserve_intermediate:
            coredump_path.unlink()
            mmap_path.unlink()

        return True

    def _get_brk_value(self):
        # ret = gdb.execute('print ((void *(*) (unsigned long)) sbrk)(0)', to_string=True)
        # brk = int(re.findall('0x[0-9a-fA-F]+', ret)[0], base=16)
        # print('brk:', hex(brk))
        # return brk
        # lang = gdb.execute('show language', to_string=True).split()[-1].split('"')[0]
        gdb.execute('set language c')
        brk_c = (Path(__file__).parent / 'get_brk.c').resolve()
        print(f'compile file -raw {brk_c}')
        gdb.execute(f'compile file -raw {brk_c}', to_string=True)
        gdb.execute('set language auto')

        brk_file = Path('sbrk.dat')
        with brk_file.open('rb') as f:
            brk_val = struct.unpack('Q', f.read()[:8])[0]
        print('brk:', hex(brk_val))
        return brk_val

    def _get_fs_base(self):
        # lang = gdb.execute('show language', to_string=True).split()[-1].split('"')[0]
        gdb.execute('set language c')
        fs_c = (Path(__file__).parent / 'get_fs_base.c').resolve()
        print(f'compile file -raw {fs_c}')
        gdb.execute(f'compile file -raw {fs_c}', to_string=True)
        gdb.execute('set language auto')

        fs_file = Path('fs_base.dat')
        with fs_file.open('rb') as f:
            fs_base = struct.unpack('Q', f.read()[:8])[0]
        print('fs:', hex(fs_base))
        return fs_base

    def _get_virtual_addresses(self):
        # vaddrs  = [0]
        # sizes   = [resource.getpagesize()]
        # offsets = [0]
        # names   = ['null']
        vaddrs  = []
        sizes   = []
        offsets = []
        names   = []
        # p = subprocess.Popen(['gdb', self.binary, '--batch', '-ex', 'info proc mappings {}'.format(pid)], stdout=subprocess.PIPE)
        # raw_mappings = p.communicate()[0].decode('utf8')
        raw_mappings = gdb.execute('info proc mappings', to_string=True)
        with open('proc.map', 'w') as f:
            f.write(raw_mappings)

        for entry in raw_mappings.split(os.linesep):
            matches = self.VADDR_REGEX.match(entry.strip())
            if matches:
                sec_name = str(matches.group(4)).strip()
                vaddrs   += [int(matches.group(1), 16)]
                sizes    += [int(matches.group(2), 16)]
                offsets  += [int(matches.group(3), 16)]
                names    += [sec_name]

        paddrs = []
        flags = []
        next_paddr = 0
        for _, size in zip(vaddrs, sizes):
            paddrs += [next_paddr]
            flags += [0]
            next_paddr += size

        return paddrs, vaddrs, sizes, offsets, flags, names

    def _create_mappings(self):
        paddrs, vaddrs, sizes, offsets, flags, names = self._get_virtual_addresses()
        assert len(paddrs) == len(vaddrs)
        assert len(paddrs) == len(sizes)
        assert len(paddrs) == len(flags)
        assert len(paddrs) == len(names)
        mappings = {}
        unexpanded = {}
        index = 0
        pgsize = resource.getpagesize()
        for p, v, s, o, f, name in zip(paddrs, vaddrs, sizes, offsets, flags, names):
            unexpanded[v] = MemoryMapping(index, p, v, s, o, f, name)
            for off in range(0, s, pgsize):
                paddr = p + off
                vaddr = v + off
                offset = o + off
                mappings[vaddr] = MemoryMapping(
                    index, paddr, vaddr, pgsize, offset, f, name)
            index += 1
        return mappings, unexpanded

    def _dump_core_to_file(self, file_path):
        gdb.execute('set use-coredump-filter off')
        gdb.execute('set dump-excluded-mappings off')
        gdb.execute('gcore {}'.format(str(file_path)))

    def _dump_mappings_to_file(self, mappings, mem_size, file_path):
        json_mappings = {'mem_size': mem_size}
        for vaddr, mapping in mappings.items():
            json_mappings[vaddr] = mapping.__dict__

        with file_path.open('w') as f:
            json.dump(json_mappings, f, indent=4)

    @property
    def is_running(self):
        # TODO: test on multi-threaded programs
        if not any(gdb.selected_inferior().threads()):
            logging.info('Program stopped')
            return False
        else:
            return True

    @property
    def mmap_end(self):
        return 18446744073692774400


class LogFormatter(logging.Formatter):
    def __init__(self, style='{'):
        logging.Formatter.__init__(self, style=style)

    def format(self, record):
        from colorama import Fore, Back, Style
        stdout_template = ' {threadName}: ' + '{message}'
        stdout_head = '[%s{levelname}%s]'

        debug_head = stdout_head % (Fore.LIGHTBLUE_EX, Fore.RESET)
        info_head  = stdout_head % (Fore.GREEN, Fore.RESET)
        warn_head  = stdout_head % (Fore.YELLOW + Style.BRIGHT, Fore.RESET + Style.NORMAL)
        error_head = stdout_head % (Fore.RED + Style.BRIGHT, Fore.RESET + Style.NORMAL)
        criti_head = stdout_head % (Fore.RED + Style.BRIGHT + Back.WHITE, Fore.RESET + Style.NORMAL + Back.RESET)

        all_formats = {
          logging.DEBUG   : logging.StrFormatStyle(debug_head + stdout_template),
          logging.INFO    : logging.StrFormatStyle(info_head  + stdout_template),
          logging.WARNING : logging.StrFormatStyle(warn_head  + stdout_template),
          logging.ERROR   : logging.StrFormatStyle(error_head + stdout_template),
          logging.CRITICAL: logging.StrFormatStyle(criti_head + stdout_template)
        }

        self._style = all_formats.get(record.levelno, logging.StrFormatStyle(logging._STYLES['{'][1]))
        self._fmt = self._style._fmt
        result = logging.Formatter.format(self, record)
        return result

    @classmethod
    def init_logger(cls, level=logging.INFO, file_prefix: str=None):
        if file_prefix and not os.path.exists('log'):
            os.mkdir('log')

        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(threadName)s: %(message)s")

        if file_prefix:
            if not os.path.exists(file_prefix):
                os.mkdir(file_prefix)
            file_handler = logging.FileHandler(os.path.join('log', str(datetime.datetime.now()).replace(':', '_') + '.log'))
            file_handler.setFormatter(log_formatter)
            root_logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(stream=sys.stderr)
        console_handler.setFormatter(cls())
        root_logger.addHandler(console_handler)


if __name__ == "__main__":
    LogFormatter.init_logger(logging.DEBUG)
    lines = []
    # with fileinput.input() as fd:
    #     for line in fd:
    #         lines.append(line)
    #     options = json.loads('\n'.join(lines))

    with open('config.json') as f:
        options = json.load(f)

    cmd = options['cmd']
    ckpt_prefix = Path(options['ckpt-prefix']).resolve()
    run_dir = Path(options['run-dir']).resolve()

    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))

    engine = GDBEngine(cmd, ckpt_prefix, run_dir, run_dir / 'gdb.cmd')
    engine.run()
