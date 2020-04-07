#! /usr/bin/env python3

from pathlib import Path

from spec_compiler import SPECBuilder
from concurrent.futures import ThreadPoolExecutor, as_completed

import configs
import logging


def build(args):
  logging.getLogger().setLevel(logging.DEBUG)
  spec_configs = configs.SPEC_CONFIG(args.suite)
  for p in spec_configs.programs:
    builder = SPECBuilder(p, spec_configs, args.output, args.log)
    builder.run()
    if builder.has_error:
      logging.error('Failed to build benchmark {}'.format(p))


if __name__ == '__main__':
  import argparse
  import csv
  import os
  cwd = os.getcwd()

  def path(s):
    p = Path(s)
    print(p, p.exists(), p.is_dir())
    assert(p.exists() and p.is_dir())
    return p

  parser = argparse.ArgumentParser()
  parser.add_argument('-l', '--log', action='store', type=path, default='', help='path to the log dir')

  subparsers = parser.add_subparsers(help='sub-command help')

  spec_build_parser = subparsers.add_parser('build', help='spec-build help')
  spec_build_parser.add_argument('-s', '--suite', action='store', type=str, help='benchmark suite',
                                 choices=['SPEC06', 'SPEC17R', 'SPEC17Rate'], default='SPEC17R')
  spec_build_parser.add_argument('output', action='store', type=path, help='path to the collection dir')
  spec_build_parser.set_defaults(func=build)

  args = parser.parse_args()
  args.func(args)

