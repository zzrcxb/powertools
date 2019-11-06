import os
import sys
import time
import subprocess

from pathlib import Path
from automater import AutoJob, automate
from configs import PIN_CONFIG, SIMPOINT_CONFIG, LAPI_CONFIG


class SimpointRunner(AutoJob):
  BBV_CMD = ['{pin_path}', '-t', '{bbv_plugin_path}', '-i', '{interval}',
              '--', '{bench_cmd}']

  def __init__(self, run_dir: Path, interval: int, pin_config: PIN_CONFIG,
               as_condor: bool, log_dir=None):
    super().__init__([self.bbv, self.simpoint], as_condor, log_dir)
    self.run_dir = run_dir
    self.interval = interval
    self.pin_config = pin_config
    self.pin_path = self.pin_config.PIN_ROOT / 'pin'
    self.bbv_plugin_path = self.pin_config.get_tool_path('bbv')

    bench_cmd_path = self.run_dir / 'cmd.txt'
    with bench_cmd_path.open() as f:
      self.bench_cmd = f.read()

    assert(self.run_dir.exists() and self.run_dir.is_dir())
    assert(self.pin_path.exists())
    assert(self.bbv_plugin_path.exists())

  @automate(BBV_CMD,)
  def bbv(self):
    pass

  def simpoint(self):
    pass


class LapiRunner(AutoJob):
  def __init__(self, run_dir: Path, bench_name, pin_config: PIN_CONFIG, log_dir=None):
    super().__init__([self.brkpt, self.rgdb, self.poll], False, log_dir)
    self.run_dir = run_dir
    self.pin_config = pin_config
    self.bench_name = bench_name

    self.pin_path = self.pin_config.PIN_ROOT / 'pin'
    self.brkpt_plugin_path = self.pin_config.get_tool_path('brkpt')

    self._portinfo_path = self.run_dir / LAPI_CONFIG.PORT_FILE
    self._gdb_driver = LAPI_CONFIG.ROOT_DIR / 'GDBDriver.py'

    self.roi_path = self.run_dir / SIMPOINT_CONFIG.CKPT_FILE
    self.brk_path = self.run_dir / SIMPOINT_CONFIG.BRKT_FILE

    # start to generate
    self.brkt4pin = self.run_dir / 'break.txt'
    with self.brk_path.open() as brk, self.roi_path.open() as roi:
      brk_data = list(brk)
      simpts = []
      for line in roi:
        slice_cnt, slice_id = list(map(int, line.split()))
        simpts.append((slice_cnt, slice_id))
      with self.brkt4pin.open('w') as out:
        for slice_cnt, slice_id in simpts:
          assert(slice_cnt > 0)
          # important! breakpoint data generated AFTER each slice execution
          brk_info = brk_data[slice_cnt - 1]
          out.write('{} {}\n'.format(slice_id, brk_info))

    bench_cmd_path = self.run_dir / 'cmd.txt'
    with bench_cmd_path.open() as f:
      self.bench_cmd = f.read()

    assert(self.brkt4pin.exists())
    assert(self.pin_path.exists())
    assert(self.brkpt_plugin_path.exists())

  def brkpt(self):
    os.chdir(self.run_dir)

    self.automate('brkpt',
                  ['{pin_path}', '-appdebug_enable', '-appdebug_silent',
                   '-t', '{brkpt_plugin_path}', '--'] + self.bench_cmd.split(),
                  Async=True)

  def rgdb(self):
    # while for rgdb info
    while not self._portinfo_path.exists():
      time.sleep(1)

    self.automate('rgdb'
        ['']
    )

  def poll(self):
    pass
