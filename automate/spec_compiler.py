import os
import sys
import shutil
import logging
import subprocess

from multiprocessing import cpu_count
from configs import SPEC_CONFIG
from pathlib import Path


target_name_map = {
  '17': {
    '502.gcc_r': 'cpugcc_r',
    '523.xalancbmk_r': 'cpuxalan_r',
    '507.cactuBSSN_r': 'cactusBSSN_r'
  },
  '06': {
  }
}

cmd_map = {
  '17': {
    '525.x264_r': 'TARGET=x264_r',
    '511.povray_r': 'TARGET=povray_r',
    '521.wrf_r': 'TARGET=wrf_r',
    '526.blender_r': 'TARGET=blender_r',
    '527.cam4_r': 'TARGET=cam4_r',
    '538.imagick_r': 'TARGET=imagick_r'
  },
  '06': {
  }
}


class SPECBuilder:
  def __init__(self, spec_name, spec_config: SPEC_CONFIG, collection_dir: Path, log_dir=''):
    self.spec_name = spec_name
    self.target_name = target_name_map[spec_config.version].get(self.spec_name, spec_name.split('.')[1])
    self.config = spec_config
    self.collection_dir = collection_dir
    if log_dir:
      self.log_dir = log_dir / 'SPEC_Compilation/{}'.format(self.spec_name)
      self.log_dir.mkdir(parents=True, exist_ok=True)
      self._log = True
    else:
      self._log = False

    self.bench_dir = self.config.benchmark_root / self.spec_name
    self.cwd = Path(os.getcwd())
    self.has_error = False

  @staticmethod
  def filter_the_one(ite, func, error_msg_empty, error_msg_multiple):
    candidates = list(filter(func, ite))
    if len(candidates) == 1:
      return candidates[0]
    elif len(candidates) == 0:
      raise RuntimeError(error_msg_empty)
    else:
      raise RuntimeError(error_msg_multiple)

  def get_build_dir(self):
    error_msg_multiple = 'Build dir of {} is not clear! Try to clear it first'.format(self.spec_name)
    error_msg_empty = 'Build dir of {} does not exists!'.format(self.spec_name)
    prefix = 'build_{}'.format(self.config.TUNE)
    if self.config.version == '17':
      candidate_dir = self.bench_dir / 'build'
    elif self.config.version == '06':
      candidate_dir = self.bench_dir / 'run'
    return SPECBuilder.filter_the_one(candidate_dir.iterdir(), lambda s: s.name.startswith(prefix),
                                      error_msg_empty, error_msg_multiple)

  def get_run_dir(self):
    error_msg_multiple = 'Run dir of {} is not clear! Try to clear it first'.format(self.spec_name)
    error_msg_empty = 'Run dir of {} does not exists!'.format(self.spec_name)
    prefix = 'run_{}'.format(self.config.TUNE)
    candidate_dir = self.bench_dir / 'run'
    return SPECBuilder.filter_the_one(candidate_dir.iterdir(), lambda s: s.name.startswith(prefix),
                                      error_msg_empty, error_msg_multiple)

  def run(self):
    funcs = [self.fake_run, self.build, self.gen_command]
    for f in funcs:
      if self.has_error:
        os.chdir(self.cwd)
        return
      f()
    os.chdir(self.cwd)

  def fake_run(self):
    cmd = [self.config.specrun, '--fake', '--loose', '--size', self.config.INPUT_SIZE, '--tune', self.config.TUNE,
           '--config', self.config.COMPILER_CONFIG, self.spec_name]

    logging.debug('"{cmd}": {name}\'s fake run'.format(name=self.spec_name, cmd=' '.join(cmd)))
    if self._log:
      fake_run_out = self.log_dir / 'fake_run.out'
      fake_run_err = self.log_dir / 'fake_run.err'
      with fake_run_out.open('w') as out, fake_run_err.open('w') as err:
        out.write('--- {} ---'.format(' '.join(cmd)))
        err.write('--- {} ---'.format(' '.join(cmd)))
        p = subprocess.Popen(cmd, stdout=out, stderr=err)
    else:
      p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.communicate()

    try:
      self.build_dir = self.get_build_dir()
      self.run_dir = self.get_run_dir()
      assert(self.build_dir.exists())
      assert(self.run_dir.exists())
    except (RuntimeError, AssertionError) as e:
      # build directory does not found!
      logging.error('{}:{}'.format(str(e), self.spec_name))
      self.has_error = True

  def build(self):
    os.chdir(self.build_dir)

    clean_cmd = ['specmake', 'clean']
    if self.spec_name in cmd_map[self.config.version]:
      make_cmd = ['specmake', '-j{}'.format(cpu_count()), cmd_map[self.config.version][self.spec_name]]
    else:
      make_cmd = ['specmake', '-j{}'.format(cpu_count())]
    logging.debug('"{cmd}": for {name}\'s cleaning'.format(cmd=clean_cmd, name=self.spec_name))
    logging.debug('"{cmd}": for {name}\'s building'.format(cmd=make_cmd, name=self.spec_name))

    if self._log:
      build_out = self.log_dir / 'build.out'
      build_err = self.log_dir / 'build.err'
      with build_out.open('w') as out, build_err.open('w') as err:
        out.write('--- {} ---'.format(' '.join(clean_cmd)))
        err.write('--- {} ---'.format(' '.join(clean_cmd)))
        p = subprocess.Popen(clean_cmd, stdout=out, stderr=err)
        p.communicate()

        out.write('--- {} ---'.format(' '.join(make_cmd)))
        err.write('--- {} ---'.format(' '.join(make_cmd)))
        p = subprocess.Popen(make_cmd, stdout=out, stderr=err)
        p.communicate()
    else:
      p = subprocess.Popen(clean_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      p.communicate()

      p = subprocess.Popen(make_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      p.communicate()

    try:
      self.target_path = self.build_dir / self.target_name
      print
      assert(self.target_path.exists())
      shutil.copy2(self.target_path, self.run_dir / self.target_name)
    except AssertionError as e:
      logging.error('target doesn\'t exists {}: {}'.format(self.build_dir / self.target_name, self.spec_name))
      self.has_error = True

  def gen_command(self):
    os.chdir(self.run_dir)
    cmd = ['specinvoke', '-n']
    logging.debug('"{cmd}": for {name}\'s command generation'.format(cmd=cmd, name=self.spec_name))

    if self._log:
      invoke_out = self.log_dir / 'invoke.out'
      invoke_err = self.log_dir / 'invoke.err'
      with invoke_out.open('w') as out, invoke_err.open('w') as err:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err)
        stdout_b, _ = p.communicate()
        out.write(stdout_b.decode('utf8'))
    else:
      p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      stdout_b, _ = p.communicate()

    stdout = stdout_b.decode('utf8')
    try:
      cmd = next(filter(lambda x: not x.startswith('#'), stdout.split('\n')))
    except StopIteration:
      print('Unable to get program {}\'s cmd'.format(
          self.spec_name), file=sys.stderr)
      self.has_error = True

    cmd_splits = cmd.split()  # assume there's no space in the path
    cmd_splits[0] = './{}'.format(self.target_name)
    cmd = ' '.join(cmd_splits)
    with open(self.run_dir / 'cmd.txt', 'w') as f:
      f.write(cmd)

    try:
      shutil.copytree(self.run_dir, self.collection_dir / self.spec_name)
    except Exception:
      logging.error('Failed to copy results for {}'.format(self.spec_name))
      self.has_error = True
