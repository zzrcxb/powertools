#! /usr/bin/env python3
# MIT License

# Copyright (c) 2019 Ian Glen Neal
# Modified by: Copyright (c) 2019-2020 Neil Zhao

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import json, os, resource
import subprocess
import logging

from elftools.elf.elffile import ELFFile
from pathlib import Path
from time import sleep

from Checkpoints import GDBCheckpoint


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
            # for vaddr, mapping_dict in self.mappings.items():
            #     if vaddr == 0 or vaddr == 'mem_size':
            #         continue

            #     maybe_file = Path(mapping_dict['name'])
                # print('maybe file: ', maybe_file)
            #     if maybe_file.exists() and maybe_file.is_file():
            #         for s in core_elf.iter_segments():
                        # print('seg: ', s['p_type'])
            #             if s['p_type'] != 'PT_LOAD':
            #                 continue
            #             elf_start_vaddr = int(s['p_vaddr'])
            #             elf_max_vaddr = elf_start_vaddr + int(s['p_memsz'])
            #             if elf_start_vaddr <= vaddr and vaddr < elf_max_vaddr:
            #                 continue
            #             else:
            #                 with maybe_file.open('rb') as shared_object:
            #                     offset = int(mapping_dict['offset'])
            #                     size   = int(mapping_dict['size'])
            #                     paddr  = int(mapping_dict['paddr'])

            #                     shared_object.seek(offset, 0)
            #                     pmem_raw.seek(paddr, 0)

            #                     buf = shared_object.read(size)
            #                     pmem_raw.write(buf)

            # Load everything else
            for s in core_elf.iter_segments():
                if s['p_type'] != 'PT_LOAD':
                    continue
                assert s['p_filesz'] == s['p_memsz']
                # assert s['p_memsz'] % pgsize == 0
                if s['p_vaddr'] in self.mappings:

                    mapping = self.mappings[s['p_vaddr']]
                    paddr = int(mapping['paddr'])
                    pmem_raw.seek(paddr, 0)

                    mem = s.data()
                    assert len(mem) == s['p_memsz']
                    pmem_raw.write(mem)

        return self.gdb_checkpoint.pmem_file


def convert_checkpoint(gdb_checkpoint, force_recreate, compress=True):
    assert isinstance(gdb_checkpoint, GDBCheckpoint)

    if gdb_checkpoint.pmem_file_exists() and not force_recreate:
        return None

    converter = GDBCheckpointConverter(gdb_checkpoint)
    pmem_out_file = converter.create_pmem_file()
    assert pmem_out_file.exists()
    if compress:
        logging.info('Starting to compress pmem')
        converter.compress_memory_image(pmem_out_file)
        logging.info('Compression finished')
        assert pmem_out_file.exists()
    return pmem_out_file
