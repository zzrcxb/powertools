#! /usr/bin/env python3

import io
import sys
import os
import time
import json
import shutil
import logging
import datetime
import subprocess

from pathlib import Path
from multiprocessing import cpu_count
from concurrent.futures import ThreadPoolExecutor


RUN_DIR = None
CKPT_PATH = None
PIN_ROOT = Path(os.getenv('PIN_ROOT'))
BBV_PATH = '/home/neil/powertools/inscount/obj-intel64/bbv.so'
BRKPT_PATH = '/home/neil/powertools/inscount/obj-intel64/brkpt.so'
GDBDRIVER = '/home/neil/powertools/lapi-plus/GDBDriver.py'
GDBONLYDRIVER = '/home/neil/powertools/lapi-plus/GDBOnly.py'
SIMPT_PATH = '/home/neil/Simpoint3.2/bin/simpoint'
PATHFINDER = '/home/neil/powertools/inscount/gdb_gen.py'
PATCHER_PATH = Path(__file__).parent / 'patch.py'


def gen_bbv(args):
  name = args.name
  log_dir = args.LOG_DIR / 'bbv'
  log_dir.mkdir(parents=True, exist_ok=True)
  bench_dir = args.RUN_DIR / name

  os.chdir(bench_dir)

  cmd_path = 'cmd.txt'
  with open(cmd_path) as f:
    cmd = f.read()

  infile = None
  cmd = cmd.strip().split('>')[0]
  splitted = cmd.split('<')
  if len(splitted) == 2:
    cmd, infile = splitted
    infile = open(bench_dir / infile.strip().split()[0], 'rb')
    cmd = cmd.split()
  else:
    cmd = cmd.split()
  cmd[0] = './' + cmd[0]

  with open(log_dir / '{}.out'.format(name), 'wb') as out , open(log_dir / '{}.err'.format(name), 'wb') as err:
    run_cmd = [str(PIN_ROOT / 'pin'), '-t', str(BBV_PATH), '--'] + cmd
    logging.debug('Exec: {}'.format(' '.join(run_cmd)))
    p = subprocess.Popen(run_cmd, stdin=infile, stdout=out, stderr=err)
    p.communicate()
    if infile:
      infile.close()

  logging.info('{} finished.'.format(name))


def gen_simpt(args):
  name = args.name
  log_dir = args.LOG_DIR / 'simpt'
  log_dir.mkdir(parents=True, exist_ok=True)
  bench_dir = args.RUN_DIR / name

  os.chdir(bench_dir)

  with open(log_dir / '{}.out'.format(name), 'wb') as out , open(log_dir / '{}.err'.format(name), 'wb') as err:
    run_cmd = [SIMPT_PATH, '-loadFVFile', 'out.bb', '-maxK', str(args.maxK), '-saveSimpoints', 'results.simpts', '-saveSimpointWeights', 'results.weights']
    logging.debug('Exec: {}'.format(' '.join(run_cmd)))
    p = subprocess.Popen(run_cmd, stdout=out, stderr=err)
    p.communicate()

  out_simpts = bench_dir / 'results.simpts'
  out_weight = bench_dir / 'results.weights'
  pin_break = bench_dir / 'break.txt'
  brkpt_file = bench_dir / 'out.brk'

  assert(out_simpts.exists())
  assert(out_weight.exists())
  assert(brkpt_file.exists())
  with out_simpts.open() as simpt, brkpt_file.open() as brkpt, pin_break.open('w') as out:
    brk_data = list(brkpt)
    simpts = []
    for line in simpt:
      slice_cnt, slice_id = list(map(int, line.split()))
      simpts.append((slice_cnt, slice_id))

    for slice_cnt, slice_id in simpts:
      if slice_cnt > 0:
        # important! breakpoint data generated AFTER each slice execution
        brk_info = brk_data[slice_cnt - 1]
        out.write('{} {}'.format(slice_id, brk_info))
      else:
        out.write('{} {}'.format(slice_id, '0 0\n'))

  assert(pin_break.exists())
  logging.info('{} finished.'.format(name))


def gen_ckpt(args):
  import resource
  resource.setrlimit(resource.RLIMIT_CORE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))

  name = args.name
  log_dir = args.LOG_DIR / 'ckpt'
  log_dir.mkdir(parents=True, exist_ok=True)

  os.chdir(args.RUN_DIR / name)
  with open('cmd.txt') as f:
    cmd = f.read()

  infile = None
  cmd = cmd.strip().split('>')[0]
  splitted = cmd.split('<')
  if len(splitted) == 2:
    cmd, infile = splitted
    infile = open(infile.strip(), 'rb')
  cmd = cmd.split()
  cmd[0] = './' + cmd[0]
  assert(Path(args.RUN_DIR / name / 'break.txt').exists())

  # start pin side
  with open(log_dir / 'pin_{}.out'.format(name), 'wb') as pin_out , open(log_dir / 'pin_{}.err'.format(name), 'wb') as pin_err:
    run_cmd = [str(PIN_ROOT / 'pin'), '-appdebug_enable', '-appdebug_silent', '-t', str(BRKPT_PATH), '--'] + cmd
    logging.debug('Pin exec: {} in {}'.format(' '.join(run_cmd), os.getcwd()))
    pin_proc = subprocess.Popen(run_cmd, stdin=infile, stdout=pin_out, stderr=pin_err)

    # wait for port
    while not os.path.exists('.portinfo'):
      time.sleep(1)

    logging.debug('port info exposed, try to connect to {}'.format(name))

    with open(log_dir / 'gdb_{}.out'.format(name), 'wb') as gdb_out , open(log_dir / 'gdb_{}.err'.format(name), 'wb') as gdb_err:
      run_cmd = ['gdb', cmd[0], '--batch', '-x', str(GDBDRIVER)]
      logging.debug('GDB exec: {}'.format(' '.join(run_cmd)))
      # setup config
      config = {
        'cmd': cmd,
        'ckpt-prefix': os.path.join(args.CKPT_DIR, name),
        'run-dir': str(args.RUN_DIR / name)
      }
      config_path = Path('config.json')
      with config_path.open('w') as f:
        json.dump(config, f)

      # start gdb
      with config_path.open() as config_in:
        gdb_proc = subprocess.Popen(run_cmd, stdin=config_in, stdout=gdb_out, stderr=gdb_err)
        gdb_proc.wait()
        pin_proc.wait()

        if (gdb_proc.returncode):
          logging.error('GDB error, {}'.format(name))
          raise RuntimeError('GDB error')
        if (pin_proc.returncode):
          logging.error('PIN error, {}'.format(name))
          raise RuntimeError('PIN error')

        if infile:
          infile.close()

  logging.info('{} finished.'.format(name))


def gen_ckpt_gdbonly(args):
  import resource
  resource.setrlimit(resource.RLIMIT_CORE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
  name = args.name
  log_dir = args.LOG_DIR / 'ckpt'
  log_dir.mkdir(parents=True, exist_ok=True)
  os.chdir(args.RUN_DIR / name)
  with open('cmd.txt') as f:
    cmd = f.read()
  infile = None
  cmd = cmd.strip().split('>')[0]
  splitted = cmd.split('<')
  if len(splitted) == 2:
    cmd, infile = splitted
    infile = open(infile.strip(), 'rb')
  cmd = cmd.split()
  cmd[0] = './' + cmd[0]
  with open(log_dir / 'gdb_{}.out'.format(name), 'wb') as gdb_out , open(log_dir / 'gdb_{}.err'.format(name), 'wb') as gdb_err:
    run_cmd = ['gdb', '--batch', '-x', str(GDBDRIVER), '--args', cmd]
    logging.debug('GDB exec: {}'.format(' '.join(run_cmd)))
    config = {
        'cmd': cmd,
        'ckpt-prefix': os.path.join(args.CKPT_DIR, name),
        'run-dir': str(args.RUN_DIR / name)
      }
    config_path = Path('config.json')
    with config_path.open('w') as f:
      json.dump(config, f)
    gdb_proc = subprocess.Popen(run_cmd, stdin=infile, stdout=gdb_out, stderr=gdb_err)
    gdb_proc.communicate()
  if (gdb_proc.returncode):
    logging.error('GDB error, {}'.format(name))
    raise RuntimeError('GDB error')

  logging.info(f'{name} finished')

def gen_path(args):
  name = args.name
  log_dir = args.LOG_DIR / 'path'
  log_dir.mkdir(parents=True, exist_ok=True)
  bench_dir = args.RUN_DIR / name

  os.chdir(bench_dir)
  with open(log_dir / '{}.out'.format(name), 'wb') as out , open(log_dir / '{}.err'.format(name), 'wb') as err:
    run_cmd = [PATHFINDER]
    logging.debug('Exec: {}'.format(' '.join(run_cmd)))
    p = subprocess.Popen(run_cmd, stdout=out, stderr=err)
    p.communicate()

  assert Path(bench_dir / 'gdb.cmd').exists()
  logging.info('{} finished.'.format(name))


def gen_patches(args):
  for d in args.RUN_DIR.iterdir():
    if d.name not in IGNORES and d.is_dir():
      with open(d / 'cmd.txt') as f:
        name = f.read().split()[0]
      executable = d / name
      backup = d / (name + '.bak')

      if not backup.exists():
        shutil.copy2(executable, backup)

      if executable.exists():
        os.chmod(executable, 0o755)
      run_cmd = [str(PATCHER_PATH), str(backup), str(executable)]
      logging.debug('Exec: {}'.format(' '.join(run_cmd)))
      subprocess.run(run_cmd)
  logging.info('finished')


IGNORES = {'log', '.git', 'sbs', 'wrf', 'specrand_f', 'specrand_i', }  #'omnetpp', 'gcc', 'calculix', 'mcf'}


def check_ckpt_stauts(args):
  for d in args.RUN_DIR.iterdir():
    if d.name not in IGNORES and d.is_dir():
      ckpt_path = Path(args.CKPT_DIR) / d.name
      if not ckpt_path.exists() or len(list(ckpt_path.iterdir())) == 0:
        print(f'[\u2205] {d.name:>20}: empty')
        continue

      num_exists = len(list(ckpt_path.iterdir()))
      with open(d / 'break.txt') as f:
        num_expectation = len(list(f))
      if num_exists != num_expectation:
        print(f'[-] {d.name:>20}: missing {num_expectation - num_exists} checkpoints')
        continue

      corrupted = False
      for ckpt in ckpt_path.iterdir():
        cpt = ckpt / 'm5.cpt'
        pmem = ckpt / 'system.physmem.store0.pmem'
        try:
          assert(cpt.exists())
          assert(pmem.exists())
        except AssertionError:
          print(f'[\u2717] {d.name:>20}: corrupted checkpoint {ckpt.name}')
          corrupted = True

      if not corrupted:
        print(f'[\u2713] {d.name:>20}: clean!')


def gen_cmds(args):
  outfile = args.RUN_DIR / 'spec06_benchmarks.py'
  with outfile.open('w') as out:
    out.writelines([
      'import m5\n',
      'from m5.objects import *\n',
      '\n'
    ])

    for d in args.RUN_DIR.iterdir():
      cmd_file = d / 'cmd.txt'
      if cmd_file.exists():
        with cmd_file.open() as f:
          cmd = f.read()
          cmd = cmd.split('>')[0].strip()
          infile = None
          splitted = cmd.split('<')
          if len(splitted) == 2:
            cmd, infile = splitted
            cmd = cmd.split()
            infile = infile.strip()
          else:
            cmd = cmd.split()
        spec_name = d.name.split('.')[1] if len(d.name.split('.')) == 2 else d.name
        executable = Path(cmd[0]).name
        exec_args = ', '.join(['"{}"'.format(c) for c in cmd[1:]])
        out.writelines([
          f'# {d.name}\n',
          f'{spec_name} = Process()\n',
          f'{spec_name}.executable = "{executable}"\n',
          f'{spec_name}.cmd = ["{executable}"] + [{exec_args}]\n'
        ])
        if infile:
          out.writelines([f'{spec_name}.input = "{infile}"\n'])
        out.write('\n')


def bbv(args):
  sub_arg = args.sub
  futures = []
  fut_map = dict()
  with ThreadPoolExecutor(max_workers=args.parallelism) as executor:
    candidates = [d for d in args.RUN_DIR.iterdir() if d.is_dir() and d.name not in IGNORES]
    for cnt, d in enumerate(candidates):
      if sub_arg == 'simpt-runner':
        fu = executor.submit(subprocess.run, ['python3', __file__, sub_arg, d.name, '--maxK', str(args.maxK)])
      else:
        fu = executor.submit(subprocess.run, ['python3', __file__, sub_arg, d.name])
      futures.append(fu)
      fut_map[fu] = d.name

  for f in futures:
    try:
      c = f.result()
      if c.returncode:
        raise RuntimeError('Non-zero return value')
    except Exception:
      logging.error('Failed to run {} for {}'.format(sub_arg, fut_map[f]))


class LogFormatter(logging.Formatter):
  def __init__(self, style='{'):
    logging.Formatter.__init__(self, style=style)

  def format(self, record):
    from colorama import Fore, Back, Style
    stdout_template = ' {threadName} | {asctime}: ' + '{message}'
    stdout_head = '[%s{levelname}%s]'

    debug_head = stdout_head % (Fore.LIGHTBLUE_EX, Fore.RESET)
    info_head  = stdout_head % (Fore.GREEN, Fore.RESET)
    warn_head  = stdout_head % (Fore.YELLOW + Style.BRIGHT, Fore.RESET + Style.NORMAL)
    error_head = stdout_head % (Fore.RED + Style.BRIGHT, Fore.RESET + Style.NORMAL)
    criti_head = stdout_head % (Fore.RED + Style.BRIGHT + Back.WHITE, Fore.RESET + Style.NORMAL + Back.RESET)

    all_formats = {
      logging.DEBUG   : logging.StrFormatStyle(debug_head + stdout_template),
      logging.INFO  : logging.StrFormatStyle(info_head  + stdout_template),
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


if __name__ == '__main__':
  LogFormatter.init_logger(logging.DEBUG, file_prefix='log')

  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('-j', '--parallelism', action='store', type=int, default=cpu_count())
  parser.add_argument('-d', '--cwd', type=str, default='.')
  subparsers = parser.add_subparsers(help='sub-command help')

  bbv_parser = subparsers.add_parser('bbv', help='bbv for all')
  bbv_parser.set_defaults(func=bbv, sub='bbv-runner')

  ckpt_parser = subparsers.add_parser('simpt', help='simpt for all')
  ckpt_parser.add_argument('--maxK', action='store', type=int, default=20)
  ckpt_parser.set_defaults(func=bbv, sub='simpt-runner')

  ckpt_parser = subparsers.add_parser('ckpt', help='ckpt for all')
  ckpt_parser.set_defaults(func=bbv, sub='ckpt-runner')

  gdbonly_parser = subparsers.add_parser('gdbonly', help='ckpt-gdbonly for all')
  gdbonly_parser.set_defaults(func=bbv, sub='gdbonly-runner')

  path_parser = subparsers.add_parser('path', help='path for all')
  path_parser.set_defaults(func=bbv, sub='path-runner')

  bbv_runner_parser = subparsers.add_parser('bbv-runner', help='generate bbv for a specific app')
  bbv_runner_parser.add_argument('name', action='store')
  bbv_runner_parser.set_defaults(func=gen_bbv)

  simpt_runner_parser = subparsers.add_parser('simpt-runner', help='generate simpoint data for a specific app')
  simpt_runner_parser.add_argument('name', action='store')
  simpt_runner_parser.add_argument('--maxK', action='store', type=int, default=20)
  simpt_runner_parser.set_defaults(func=gen_simpt)

  ckpt_runner_parser = subparsers.add_parser('ckpt-runner', help='generate checkpoint for a specific app')
  ckpt_runner_parser.add_argument('name', action='store')
  ckpt_runner_parser.set_defaults(func=gen_ckpt)

  path_runner_parser = subparsers.add_parser('path-runner', help='generate gdb path for a specific app')
  path_runner_parser.add_argument('name', action='store')
  path_runner_parser.set_defaults(func=gen_path)

  gdbonly_runner_parser = subparsers.add_parser('gdbonly-runner', help='generate gdb path for a specific app')
  gdbonly_runner_parser.add_argument('name', action='store')
  gdbonly_runner_parser.set_defaults(func=gen_ckpt_gdbonly)

  ckpt_status_parser = subparsers.add_parser('ckpt-status', help='check all checkpoint generation status')
  ckpt_status_parser.set_defaults(func=check_ckpt_stauts)

  cmds_gen_parser = subparsers.add_parser('gen-cmds', help='generate spec17 config for gem5')
  cmds_gen_parser.set_defaults(func=gen_cmds)

  patch_gen_parser = subparsers.add_parser('gen-patches', help='patch all binares')
  patch_gen_parser.set_defaults(func=gen_patches)

  args = parser.parse_args()
  args.RUN_DIR  = Path(Path(args.cwd) / 'run').resolve()
  args.CKPT_DIR = Path(Path(args.cwd) / 'ckpt').resolve()
  args.LOG_DIR  = Path(Path(args.cwd) / 'log').resolve()
  try:
    args.func(args)
  except AttributeError:
    parser.print_help(sys.stderr)
