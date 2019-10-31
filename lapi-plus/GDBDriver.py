import re
import os
import json
import argparse
import resource
import datetime
import subprocess
from multiprocessing import cpu_count, Pool, Lock, Process

import sys
WORK_DIR = os.path.dirname(__file__)
sys.path.append(WORK_DIR)
sys.path.append('/home/neil/.virtualenvs/lapi/lib/python3.7/site-packages')
print(sys.path)

from pathlib import Path
from CheckpointConvert import convert_checkpoint
from CheckpointTemplate import MemoryMapping, RegisterValues, fill_checkpoint_template
from Checkpoints import GDBCheckpoint


def get_mem_map():
  pass


def get_core_dump():
  pass




class GDBEngine:
    ''' This class is used by the gdb process running inside gdb.'''

    # start-address end-address size offset name
    VADDR_REGEX_STRING = r'\s*(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s*(.*)'
    VADDR_REGEX = re.compile(VADDR_REGEX_STRING)

    BAD_MEM_REGIONS = ['[vvar]', '[vsyscall]']

    def __init__(self,
                 checkpoint_root_dir,
                 compress_core_files,
                 convert_checkpoints,
                 pid, remote_port, args):
        from lapidary.checkpoint.GDBShell import GDBShell
        import gdb  # pylint: disable=import-error
        self.shell = GDBShell(self)
        self.chk_num = 0
        self.compress_core_files = compress_core_files
        self.compress_processes  = {}
        self.convert_checkpoints = convert_checkpoints
        self.convert_processes   = {}
        self.pid = pid

        # Otherwise long arg strings get mutilated with '...'
        gdb.execute('target remote :{}'.format(remote_port))
        gdb.execute('set print elements 0')
        gdb.execute('set follow-fork-mode child')
        # args = (gdb.execute('print $args', to_string=True)).split(' ')[2:]
        # args = [ x.replace('"','').replace(os.linesep, '') for x in args ]
        assert len(args) > 0
        self.binary = args[0]
        self.args = ' '.join(args[1:])
        if checkpoint_root_dir is not None:
            self.chk_out_dir = Path(checkpoint_root_dir) / \
                '{}_gdb_checkpoints'.format(Path(self.binary).name)
        else:
            self.chk_out_dir = Path( WORK_DIR ) / Path('{}_gdb_checkpoints'.format(Path(self.binary).name))
        gdb.execute('set print elements 200')


    def _get_virtual_addresses(self):
        import gdb  # pylint: disable=import-error
        vaddrs = [0]
        sizes = [resource.getpagesize()]
        offsets = [0]
        names = ['null']
        p = subprocess.Popen(['gdb', self.binary, '--batch', '-ex', 'info proc mappings {}'.format(self.pid)], stdout=subprocess.PIPE)
        raw_mappings = p.communicate()[0].decode('utf8')
        # raw_mappings = gdb.execute('info proc mappings', to_string=True)
        print(raw_mappings)

        for entry in raw_mappings.split(os.linesep):
            matches = self.VADDR_REGEX.match(entry.strip())
            if matches:
                if 'brp.so' not in str(matches.group(4)).strip() and '/home/neil/pin-3.11' not in str(matches.group(4)).strip():
                    vaddrs   += [int(matches.group(1), 16)]
                    sizes    += [int(matches.group(2), 16)]
                    offsets  += [int(matches.group(3), 16)]
                    names    += [str(matches.group(4)).strip()]

        return vaddrs, sizes, offsets, names

    def _get_memory_regions(self):
        vaddrs, sizes, offsets, names = self._get_virtual_addresses()
        paddrs = []
        flags = []
        next_paddr = 0
        for vaddr, size in zip(vaddrs, sizes):
            paddrs += [next_paddr]
            flags += [0]
            next_paddr += size

        return paddrs, vaddrs, sizes, offsets, flags, names

    def _create_mappings(self, filter_bad_regions=False, expand=False):
        paddrs, vaddrs, sizes, offsets,flags, names = self._get_memory_regions()
        assert len(paddrs) == len(vaddrs)
        assert len(paddrs) == len(sizes)
        assert len(paddrs) == len(flags)
        assert len(paddrs) == len(names)
        mappings = {}
        index = 0
        pgsize = resource.getpagesize()
        for p, v, s, o, f, name in zip(paddrs, vaddrs, sizes, offsets, flags, names):
            # if filter_bad_regions and name in GDBEngine.BAD_MEM_REGIONS:
            #     print('Skipping region "{}" (v{}->v{}, p{}->p{})'.format(name,
            #       hex(v), hex(v + s), hex(p), hex(p + s)))
            #     continue
            if expand:
                # print( "Expanding v = 0x%x" % (v) )
                for off in range(0, s, pgsize):
                    paddr = p + off if p != 0 else 0
                    vaddr = v + off
                    offset = o + off
                    mappings[vaddr] = MemoryMapping(
                        index, paddr, vaddr, pgsize, offset, f, name)
            else:
                mappings[v] = MemoryMapping(index, p, v, s, o, f, name)

            index += 1

        return mappings


    @staticmethod
    def _create_convert_process(checkpoint_dir):
        gdb_checkpoint = GDBCheckpoint(checkpoint_dir)
        proc = Process(target=convert_checkpoint,
                       args=(gdb_checkpoint, True))
        proc.start()
        return proc

    def _dump_core_to_file(self, file_path):
        import gdb  # pylint: disable=import-error
        gdb.execute('set use-coredump-filter off')
        gdb.execute('set dump-excluded-mappings off')
        gdb.execute('gcore {}'.format(str(file_path)))
        if self.compress_core_files:
            print('Creating gzip process for {}'.format(str(file_path)))
            gzip_proc = subprocess.Popen(['gzip', '-f', str(file_path)])
            self.compress_processes[file_path.parent] = gzip_proc
        elif self.convert_checkpoints:
            print('Creating convert process for {}'.format(str(file_path.parent)))
            convert_proc = GDBEngine._create_convert_process(file_path.parent)
            self.convert_processes[file_path.parent] = convert_proc

    def _dump_mappings_to_file(self, mappings, mem_size, file_path):
        json_mappings = {'mem_size': mem_size}
        for vaddr, mapping in mappings.items():
            json_mappings[vaddr] = mapping.__dict__

        with file_path.open('w') as f:
            json.dump(json_mappings, f, indent=4)


    def _calculate_memory_size(self, mappings):
        # 4GB
        return 4294967296

    def get_mmap_end(self):
        return 18446744073692774400

    def _create_gem5_checkpoint(self, debug_mode):
        chk_loc = self.chk_out_dir / '{}_check.cpt'.format(self.chk_num)
        if chk_loc.exists():
            print('Warning: {} already exists, overriding.'.format(str(chk_loc)))
        else:
            chk_loc.mkdir(parents=True)
        pmem_name = 'system.physmem.store0.pmem'
        chk_file = 'm5.cpt'

        template_mappings = self._create_mappings(True, expand=True)
        regs = RegisterValues(self.fs_base)

        total_mem_size = self._calculate_memory_size(template_mappings)
        print(total_mem_size)
        total_mem_size = 4294967296

        file_mappings = self._create_mappings(True)

        stack_mapping = [ m for v, m in file_mappings.items() if 'stack' in m.name ]
        assert len(stack_mapping) == 1
        stack_mapping = stack_mapping[0]

        brk_value = self._get_brk_value()
        mmap_end_value = self.get_mmap_end()

        fill_checkpoint_template(
            output_file=str(chk_loc / chk_file),
            mappings=template_mappings,
            misc_reg_string=regs.get_misc_reg_string(),
            int_reg_string=regs.get_int_reg_string(),
            pc_string=regs.get_pc_string(),
            next_pc_string=regs.get_next_pc_string(),
            float_reg_string=regs.get_float_reg_string(),
            mem_size=total_mem_size,
            stack_mapping=stack_mapping,
            brk=brk_value,
            mmap_end=mmap_end_value,
            timeNow=str(datetime.datetime.now(datetime.timezone.utc)))

        self._dump_core_to_file(chk_loc / 'gdb.core')
        self._dump_mappings_to_file(file_mappings, total_mem_size,
            chk_loc / 'mappings.json')
        self.chk_num += 1

    def _can_create_valid_checkpoint(self):
        mappings = self._create_mappings()
        regs = RegisterValues(self.fs_base)

        current_pc = int(regs.get_pc_string())
        for vaddr, mapping in mappings.items():
            if current_pc in mapping and mapping.name in GDBEngine.BAD_MEM_REGIONS:
                print('Skipping checkpoint at {} since it is in {} region'.format(
                      hex(current_pc), mapping.name))
                return False

        return True

    @staticmethod
    def _get_brk_value():
        import struct, gdb  # pylint: disable=import-error
        return 7368704
        lang = gdb.execute('show language', to_string=True).split()[-1].split('"')[0]
        gdb.execute('set language c')

        brk_file = Path('/tmp/sbrk.txt' )
        if os.path.exists( brk_file ):
            os.remove( brk_file )

        gdb.execute('compile file -raw get_brk.c') # % WORK_DIR )
        brk = 0
        print( "#"* 20 + "cwd = %s" % os.getcwd() )
        try:
            with brk_file.open('rb') as f:
                data    = f.read()[:8]
                print(data)
                print(struct.unpack('Q', data))
                brk = struct.unpack('Q', data)[0]
        except:
            pass
        finally:
            brk_file.unlink()
        # gdb.execute('set language {}'.format(lang))
        print('Found brk: {} ({})'.format(brk, hex(brk)))
        return brk



    @staticmethod
    def _get_fs_base():
        import struct, gdb  # pylint: disable=import-error
        lang = gdb.execute('show language', to_string=True).split()[-1].split('"')[0]
        gdb.execute('set language c')
        gdb.execute('compile file -raw %s/get_fs_base.c' % WORK_DIR )
        fs_base = 0
        fs_base_file = Path('fs_base.txt')
        try:
            with fs_base_file.open('rb') as f:
                data    = f.read()[:8]
                print('fs_base_data:', data)
                print(struct.unpack('Q', data))
                fs_base = struct.unpack('Q', data)[0]
        except:
            pass
        finally:
            fs_base_file.unlink()
        gdb.execute('set language {}'.format(lang))
        print('Found FS BASE: {} ({})'.format(fs_base, hex(fs_base)))
        return fs_base

    def _run_base(self, debug_mode):
        import gdb  # pylint: disable=import-error
        print(self.binary)
        return 7227520
        gdb.execute('set auto-load safe-path /')
        gdb.execute('exec-file {}'.format(self.binary))
        gdb.execute('file {}'.format(self.binary))

        gdb.execute('break main')
        print('Running with args: "{}"'.format(self.args))

        gdb.execute('run {}'.format(self.args))
        print('...', self.args)
        self.fs_base = self._get_fs_base()
        if debug_mode:
            import IPython
            IPython.embed()

    def _poll_background_processes(self, wait=False):
        timeout = 0.001
        if wait:
            print('Waiting for background processes to complete before exit.')
            timeout = None
        gzip_complete = []
        for file_path, gzip_proc in self.compress_processes.items():
            gzip_proc.join(timeout)
            if not gzip_proc.is_alive():
                gzip_complete += [file_path]
                if self.convert_checkpoints:
                    print('Creating convert process for {} after gzip'.format(
                        str(file_path)))
                    convert_proc = GDBEngine._create_convert_process(file_path)
                    self.convert_processes[file_path.parent] = convert_proc
        for key in gzip_complete:
            print('Background gzip for {} completed'.format(key))
            self.compress_processes.pop(key)

        convert_complete = []
        for file_path, convert_proc in self.convert_processes.items():
            convert_proc.join(timeout)
            if not convert_proc.is_alive():
                convert_complete += [file_path]
        for key in convert_complete:
            print('Background convert for {} completed'.format(key))
            self.convert_processes.pop(key)

    def try_create_checkpoint(self, debug_mode=False):
        self._poll_background_processes()

        if self._can_create_valid_checkpoint():
            print('Creating checkpoint #{}'.format(self.chk_num))
            self._create_gem5_checkpoint(debug_mode)


if __name__ == "__main__":
  import gdb  # pylint: disable=import-error
  engine = GDBEngine('/home/neil/test', False, True, 68498, 35689, ['./libquantum', '1397', '8'])
  engine.fs_base = engine._run_base(False)
  engine.try_create_checkpoint()
