#! /usr/bin/env python3

import gzip, json, mimetypes, os, resource, shutil
import subprocess

from argparse import ArgumentParser
from elftools.elf.elffile import ELFFile
from multiprocessing import cpu_count, Pool, Lock, Process
from pathlib import Path
from pprint import pprint
from progressbar import ProgressBar
from time import sleep

from Checkpoints import GDBCheckpoint


def get_directory_entries_by_time(directory_path):
    from natsort import natsorted
    assert isinstance(directory_path, Path)
    get_name = lambda d: str(d.name)
    return natsorted(directory_path.iterdir(), key=get_name)

def select_evenly_spaced(list_or_dict, num_to_select):
    from natsort import natsorted, ns
    from copy import copy
    if num_to_select > len(list_or_dict):
        return copy(list_or_dict)

    sorted_keys = natsorted(list_or_dict, alg=ns.IGNORECASE)
    # https://en.wikipedia.org/wiki/Bresenham%27s_line_algorithm
    f = lambda m, n: [i*n//m + n//(2*m) for i in range(m)]
    indices = f(num_to_select, len(sorted_keys))
    sublist = [ sorted_keys[i] for i in indices ]

    if isinstance(list_or_dict, list):
        return sublist

    return { k: list_or_dict[k] for k in sublist }


class GDBCheckpointConverter:

    def __init__(self, gdb_checkpoint):
        assert isinstance(gdb_checkpoint, GDBCheckpoint)
        assert gdb_checkpoint.is_valid_checkpoint()
        self.gdb_checkpoint = gdb_checkpoint
        self.mappings = self.gdb_checkpoint.get_mappings()

    @staticmethod
    def compress_memory_image(file_path):
        subprocess.call(['gzip', '-f', str(file_path)])
        gzip_path = Path(str(file_path) + '.gz')
        gzip_path.rename(file_path)

    def create_pmem_file(self):

        with self.gdb_checkpoint.get_pmem_file_handle() as pmem_raw,\
             self.gdb_checkpoint.get_core_file_handle() as core:
            core_elf = ELFFile(core)
            pgsize = resource.getpagesize()
            idx = 0

            # Write out whole file as zeros first
            pmem_raw.truncate(self.mappings['mem_size'])

            # Check for shared object files
            for vaddr, mapping_dict in self.mappings.items():
                if vaddr == 0 or vaddr == 'mem_size':
                    continue

                maybe_file = Path(mapping_dict['name'])
                if maybe_file.exists() and maybe_file.is_file():
                    for s in core_elf.iter_segments():
                        if s['p_type'] != 'PT_LOAD':
                            continue
                        elf_start_vaddr = int(s['p_vaddr'])
                        elf_max_vaddr = elf_start_vaddr + int(s['p_memsz'])
                        if elf_start_vaddr <= vaddr and vaddr < elf_max_vaddr:
                            continue
                        else:
                            with maybe_file.open('rb') as shared_object:
                                offset = int(mapping_dict['offset'])
                                size   = int(mapping_dict['size'])
                                paddr  = int(mapping_dict['paddr'])

                                shared_object.seek(offset, 0)
                                pmem_raw.seek(paddr, 0)

                                buf = shared_object.read(size)
                                pmem_raw.write(buf)

            # Load everything else
            for s in core_elf.iter_segments():
                if s['p_type'] != 'PT_LOAD':
                    continue
                print('memsz:', s['p_memsz'], 'page size:', pgsize)
                assert s['p_filesz'] == s['p_memsz']
                # assert s['p_memsz'] % pgsize == 0
                if s['p_vaddr'] in self.mappings:

                    mapping = self.mappings[s['p_vaddr']]
                    paddr = int(mapping['paddr'])
                    pmem_raw.seek(paddr, 0)

                    mem = s.data()
                    assert len(mem) == s['p_memsz']
                    #print('{}: {} -> {}, size {}'.format(os.getpid(), s['p_vaddr'], paddr, len(mem)))
                    pmem_raw.write(mem)

        return self.gdb_checkpoint.pmem_file


################################################################################

def convert_checkpoint(gdb_checkpoint, force_recreate):
    assert isinstance(gdb_checkpoint, GDBCheckpoint)

    if gdb_checkpoint.pmem_file_exists() and not force_recreate:
        return None

    converter = GDBCheckpointConverter(gdb_checkpoint)
    pmem_out_file = converter.create_pmem_file()
    assert pmem_out_file.exists()
    return pmem_out_file


def add_arguments(parser):
    parser.add_argument('--pool-size', '-p', default=cpu_count(),
                        help='Number of threads to run at a time.')
    parser.add_argument('--checkpoint-dir', '-d',
                        help='Directory that contains all checkpoints.')
    parser.add_argument('--num-checkpoints', '-n', default=None, type=int,
        help='Number of checkpoints to simulate. If None, then all.')
    parser.add_argument('--force', '-f', default=False, action='store_true',
        help='Override existing checkpoints. Disabled by default')
    parser.add_argument('--no-compression', '-x', default=False,
        action='store_true', help='Do not compress pmem file. Faster, but space intensive')


def main():
    parser = ArgumentParser(description='Convert gdb core dumps into gem5 pmem files.')
    add_arguments(parser)

    args = parser.parse_args()

    checkpoint_dir = Path(args.checkpoint_dir)
    assert checkpoint_dir.exists()

    pool_args = []
    for checkpoint_subdir in get_directory_entries_by_time(checkpoint_dir):
        if checkpoint_subdir.is_dir():
            checkpoint = GDBCheckpoint(checkpoint_subdir)
            if checkpoint.is_valid_checkpoint():
                pool_args += [ (checkpoint, args.force) ]
            else:
                print('{} is not a valid checkpoint, skipping.'.format(checkpoint))

    if args.num_checkpoints is not None:
        pool_args = select_evenly_spaced(pool_args, args.num_checkpoints)

    with Pool(int(args.pool_size)) as pool:
        bar = ProgressBar(max_value=len(pool_args))
        lock = Lock()

        def update_bar(pmem_file_dest):
            try:
                lock.acquire()
                bar.update(update_bar.num_complete)
                update_bar.num_complete += 1
                if pmem_file_dest is not None:
                    update_bar.newly_created += 1
                    if update_bar.compress:
                        gzip_proc = Process(target=GDBCheckpointConverter.compress_memory_image,
                                            args=(pmem_file_dest,))
                        update_bar.gzip_procs += [gzip_proc]
                        gzip_proc.start()
            finally:
                lock.release()

        update_bar.num_complete = 0
        update_bar.newly_created = 0
        update_bar.gzip_procs = []
        update_bar.compress = not args.no_compression
        bar.start()

        def fail(e):
            raise e

        results = []
        for args in pool_args:
            result = pool.apply_async(convert_checkpoint, args, callback=update_bar,
                error_callback=fail)
            results += [result]

        all_ready = False
        while not all_ready:
            all_ready = True
            for result in [r for r in results if not r.ready()]:
                result.wait(0.1)
                if not result.ready():
                    all_ready = False
                sleep(1)

        bar.finish()
        progressbar.streams.flush()

        for gzip_proc in update_bar.gzip_procs:
            if gzip_proc is not None:
                gzip_proc.join()

        print('\n{}/{} newly created, {}/{} already existed.'.format(
          update_bar.newly_created, len(pool_args),
          len(pool_args) - update_bar.newly_created, len(pool_args)))

    return 0

if __name__ == '__main__':
    exit(main())
