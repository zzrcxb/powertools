import re
import os
import sys
import git
import json
import shutil
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

    def __init__(self, cmd: list, ckpt_prefix: Path, run_dir: Path, compress_ckpt=True,
                 mem_size=4*1024*1024*1024, preserve_intermediate=True):
        assert(len(cmd) > 0)
        self.binary = run_dir / cmd[0]
        self.args = cmd[1:]
        assert(self.binary.exists())

        self._pin_info  = run_dir / CONFIGS.PIN_INFO_FILENAME
        self._port_info = run_dir / CONFIGS.PORT_INFO_FILENAME
        # try to load port info
        if not self._port_info.exists():
            logging.error('Remote GDB port information not found, please check whether the pintool is running')
        with self._port_info.open() as f:
            rgdb_port = json.load(f)['port']

        self._ckpt_prefix = ckpt_prefix
        self._compress_ckpt = compress_ckpt
        self.mem_size = mem_size
        self._repo = git.Repo(path=__file__, search_parent_directories=True)
        self._preserve_intermediate = preserve_intermediate

        if self._repo.is_dirty():
            logging.warning('Repo is dirty! Are you developping or running final experiments?')

        # Connect to remote GDB server
        gdb.execute('target remote :{}'.format(rgdb_port))
        gdb.execute('set follow-fork-mode child')

    def run(self):
        while self.is_running:
            self._create_ckpt()
            gdb.execute('c')

    def _create_ckpt(self):
        # load messages
        with self._pin_info.open() as f:
            pin_info = json.load(f)
        brk_ID    = pin_info['brkID']
        ckpt_name = 'cpt.None.SIMP-{}'.format(brk_ID)
        pid       = pin_info['pid']
        brk_value = pin_info['brkPoint']
        fs_base   = pin_info['fsBase']
        all_visited = pin_info['allVisited']
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
        mmaps, unexpanded_mmaps = self._create_mappings(pid)
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

        if all_visited:
            logging.info('Every breakpoint has been reached, exiting...')
            gdb.execute('q')
        return True

    def _get_virtual_addresses(self, pid):
        vaddrs  = []
        sizes   = []
        offsets = []
        names   = []
        p = subprocess.Popen(['gdb', self.binary, '--batch', '-ex', 'info proc mappings {}'.format(pid)], stdout=subprocess.PIPE)
        raw_mappings = p.communicate()[0].decode('utf8')

        def mmap_filter(name):
            return True
            return CONFIGS.PINTOOL_PLUGIN not in name and os.environ.get('PIN_ROOT', CONFIGS.DEFAULT_PIN_VER) not in name

        for entry in raw_mappings.split(os.linesep):
            matches = self.VADDR_REGEX.match(entry.strip())
            if matches:
                sec_name = str(matches.group(4)).strip()
                if mmap_filter(sec_name):
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

    def _create_mappings(self, pid):
        paddrs, vaddrs, sizes, offsets,flags, names = self._get_virtual_addresses(pid)
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
    LogFormatter.init_logger()
    lines = []
    with fileinput.input() as fd:
        for line in fd:
            lines.append(line)
        options = json.loads('\n'.join(lines))

    cmd = options['cmd']
    ckpt_prefix = options['ckpt-prefix']
    run_dir = options['run-dir']

    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))

    engine = GDBEngine(cmd, Path(ckpt_prefix), Path(run_dir))
    engine.run()
