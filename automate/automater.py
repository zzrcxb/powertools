import os
import sys
import logging
import htcondor
import subprocess

from pathlib import Path
from functools import wraps
from subprocess import PIPE, TimeoutExpired


class AutoJob:
  def __init__(self, funcs, as_condor, log_dir=None):
    self.funcs = funcs
    self.as_condor = as_condor
    self.log_dir = Path(log_dir) if log_dir else None
    self.cwd = Path(os.getcwd())
    self.has_error = False

  def run(self):
    for f in self.funcs:
      if self.has_error:
        os.chdir(self.cwd)
        return
      logging.debug('executing {} <- {}'.format(f.__name__, self))
      f()
    os.chdir(self.cwd)

  def automate(self, name, cmds, shell=False, timeout=None, nproc=1, Async=False, inputs=sys.stdin):
    log_dir = self.log_dir
    if log_dir:
      log_dir.mkdir(parents=True, exist_ok=True)
      log_out = log_dir / name + '.out'
      log_err = log_dir / name + '.err'
      log_log = log_dir / name + '_condor.log'

    self._auto_responds = []
    for cmd in cmds:
      # resolve cmd
      cmd = list(map(lambda s: s.format(**self.__dict__), cmd))
      logging.debug('{} <- {}'.format(' '.join(cmd), self))
      if not self.as_condor:
        if not Async:
          p = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, stdin=inputs, shell=shell)
          try:
            stdout_b, stderr_b = p.communicate(timeout=timeout)
            self._auto_responds.append((stdout_b, stderr_b))
          except TimeoutExpired:
            p.kill()
            logging.error('Failed to execute {} within {} seconds. Job failed!'.format(cmd, timeout))
            self.has_error = True
          if log_dir:
            with log_out.open('wb') as out, log_err.open('wb') as err:
              out.write(stdout_b)
              err.write(stderr_b)
        else:
          assert(log_dir) # must set log_dir when it's running in asyc mode
          with log_out.open('wb') as out, log_err.open('wb') as err:
            p = subprocess.Popen(cmd, stdout=out, stderr=err, stdin=inputs, shell=shell)
        self._auto_responds.append(p)
    else:
      if log_dir:
        log_paths = (log_out, log_err, log_log)
      else:
        log_paths = None
      job = self.get_condor_job(cmd, log_paths, nproc)
      submission = htcondor.Submit(job)

  @staticmethod
  def get_condor_job(cmd, log_paths=None, nproc=1):
    if log_paths:
      out, err, log = log_paths
      log_options = dict(output=str(out), error=str(err), log=str(log))
    else:
      log_options = dict()

    return dict(
      universal='vanilla',
      executable=cmd[0],
      arguments=' '.join(cmd[1:]),
      getenv='true',
      requirements='Arch == "X86_64"',
      request_cpus=str(nproc),
      nice_user='true',
      initialdir=os.getcwd()
    ).update(log_options)

  def __str__(self):
    return self.__class__.__name__

  def __repr__(self):
    return '{}(as_condor={})'.format(self.__class__.__name__, self.as_condor)


def automate(cmds, shell=False, timeout=None, nproc=1, Async=False):
  def decorate(func):
    @wraps(func)
    def wrapper(self: AutoJob, *args, **kwargs):
      log_dir = self.log_dir
      if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_out = log_dir / func.__name__ + '.out'
        log_err = log_dir / func.__name__ + '.err'
        log_log = log_dir / func.__name__ + '_condor.log'

      self._auto_responds = []
      for cmd in cmds:
        # resolve cmd
        cmd = list(map(lambda s: s.format(**self.__dict__), cmd))
        logging.debug('{} <- {}'.format(' '.join(cmd), self))
        if not self.as_condor:
          if not Async:
            p = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, shell=shell)
            try:
              stdout_b, stderr_b = p.communicate(timeout=timeout)
              self._auto_responds.append((stdout_b, stderr_b))
            except TimeoutExpired:
              p.kill()
              logging.error('Failed to execute {} within {} seconds. Job failed!'.format(cmd, timeout))
              self.has_error = True

            if log_dir:
              with log_out.open('wb') as out, log_err.open('wb') as err:
                out.write(stdout_b)
                err.write(stderr_b)
          else:
            assert(log_dir) # must set log_dir when it's running in async mode
            with log_out.open('wb') as out, log_err.open('wb') as err:
              p = subprocess.Popen(cmd, stdout=out, stderr=err, shell=shell)
              self._auto_responds.append(p)
        else:
          if log_dir:
            log_paths = (log_out, log_err, log_log)
          else:
            log_paths = None
          job = self.get_condor_job(cmd, log_paths, nproc)
          submission = htcondor.Submit(job)
          # start to sync
          # TODO: sync

      return func(self, *args, **kwargs)

    return wrapper
  return decorate
