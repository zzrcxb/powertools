#! /usr/bin/env python3

import fileinput
import argparse
import sys
import math
import celi_actions as CA

from collections import namedtuple


class CeliCore:
  available_actions = {'sel', 'add', 'sub', 'mul', 'div', 'grp', 'avg', 'sum', 'max', 'min', 'sort'}
  Action = namedtuple('Action', 'name subcmds params')

  def __init__(self, fd, args):
    self.fd = fd
    self.args = args
    actions = [self.Action(a.split(':')[0], a.split(':')[1:], tuple(
        map(str.split, ' '.join(b).split('-')))) for a, *b in args.actions]
    self.executors = []
    for ac in actions:
      actioncls = getattr(CA, 'Celi{}'.format(ac.name.capitalize()), None)
      if not callable(actioncls):
        raise argparse.ArgumentTypeError('Invalid action {}!'.format(ac.name))
      actor = actioncls(ac.subcmds, ac.params, self.args,
                        default_fmt=self.args.default_out_type, width=self.args.width)
      self.executors.append(actor)

  def run(self):
    for i, line in enumerate(self.fd):
      row = []
      splitted = list(map(str.strip, line.split(self.args.in_delimiter)))
      if i >= self.args.row_header:
        splitted = self.process_input(splitted, self.args.in_types)

      for extr in self.executors:
        try:
          if i < self.args.row_header:
            row.extend(extr.header(splitted))
          else:
            row.extend(extr.execute(splitted))
        except IndexError:
          raise argparse.ArgumentTypeError('Invalid index ({}) for action {}!'.format(extr.params, extr.__class__.__name__))

      if len(row) > 0:
        self.print_row(row)

    # close and print all the delayed
    closed = []
    status = []
    for e in self.executors:
      try:
        closed.append(e.close())
        status.append(True)
      except StopIteration:
        closed.append(None)
        status.append(False)

    while all(status):
      row = []
      print_flag = False
      for index, (e, c) in enumerate(zip(self.executors, closed)):
        if status[index]:
          try:
            line = next(c)
            print_flag = True
          except StopIteration:
            tp = '{{:>{}}}'.format(self.args.width)
            line = [tp.format(''), ] * len(e)
            status[index] = False
          row.extend(line)
      if print_flag:
        self.print_row(row)


  # def build_header(self, headers, a, params):
  #   if a == 'sel':
  #     return [headers[p] for p in params]
  #   elif a == 'grpcnt':
  #     return [headers[params[0]], 'grpcnt({})'.format(headers[params[0]])]
  #   elif a == 'grpsum':
  #     return [headers[params[0]], ] + ['grpsum({})'.format(headers[p]) for p in params[1:]]
  #   elif a in self.unary_actions:
  #     return ['{}{}{}'.format(headers[params[0]], self.unary_actions[a], headers[params[1]])]
  #   else:
  #     return ['{}({})'.format(a, headers[p]) for p in params]

  # def build_data(self, row, a, params):
  #   if '-' in a:
  #     fname, *sub_cmd = a.split('-')
  #   else:
  #     fname = a
  #     sub_cmd = []

  #   func = getattr(self, fname, None)
  #   if not callable(func):
  #     raise argparse.ArgumentTypeError('Invalid action: {}'.format(a))
  #   try:
  #     params = sub_cmd.extend(params)
  #     params = [row, ] + params
  #     return func(*params)
  #   except TypeError:
  #     raise argparse.ArgumentTypeError('Invalid params {} for action {}'.format(params, a))

  def process_input(self, row, format):
    handlers = {
      's': str,
      'd': int,
      'x': lambda x: int(x, base=16),
      'b': bool,
      'f': float,
      '%': lambda x: float(x.replace('%', '')) / 100
    }
    processed = []
    for i, elem in enumerate(row):
      if i < len(format):
        code = format[i]
      else:
        code = self.args.default_in_type
      try:
        processed.append(handlers[code](elem))
      except KeyError:
        raise argparse.ArgumentTypeError('Invalid format code:', code)
      except ValueError:
        raise argparse.ArgumentTypeError('Invalid input: {} for format code: {}'.format(elem, code))
    return processed

  def print_row(self, row, format=None):
    if format:
      formatted = []
      for i, elem in enumerate(row):
        if i < len(format):
          code = format[i]
        else:
          code = self.args.default_out_type
        if code == 's':
          formatted.append('{}'.format(row[i]))
        elif code == 'f' or code == '%':
          formatted.append('{{:.2{}}}'.format(code).format(row[i]))
        else:
          formatted.append('{{:{}}}'.format(code).format(row[i]))
    else:
      formatted = row
    print(self.args.out_delimiter.join(row))

  def sel(self, row, col1, *args, fake=False):
    cols = [col1, ] + args
    if not fake:
      return [row[c] for c in cols]

  def add(self, row, col1, col2, fake=False):
    col1, col2 = int(col1), int(col2)
    if not fake:
      return [row[col1] + row[col2]]

  def sub(self, row, col1, col2, fake=False):
    col1, col2 = int(col1), int(col2)
    if not fake:
      return [row[col1] - row[col2]]

  def mul(self, row, col1, col2, fake=False):
    col1, col2 = int(col1), int(col2)
    if not fake:
      return [row[col1] * row[col2]]

  def div(self, row, col1, col2, fake=False):
    col1, col2 = int(col1), int(col2)
    if not fake:
      try:
        r = row[col1] / row[col2]
      except ZeroDivisionError:
        r = math.nan
      return [r, ]

  def grpsum(self, row, col1, col2, fake=False):
    pass


if __name__ == "__main__":
  def non_negative(s):
    return 0 if int(s) <= 0 else 1

  parser = argparse.ArgumentParser('celi.py')

  # input related
  parser.add_argument('-rh', '--row-header',  type=non_negative, default=1,
                      help='How many rows does the header take')
  parser.add_argument('-d', '--in-delimiter', type=str, default=',',
                      help='Input delimiter')
  parser.add_argument('--code-page', type=str, default='utf-8',
                      help='Codepage of the input')
  parser.add_argument('-t', '--in-types', type=str, default='d',
                      help='''Input types,
                      "s" stands for string,
                      "d" stands for decimal,
                      "x" stands for hex,
                      "b" stands for boolean,
                      "f" stands for float,
                      "%" stands for percentange.
                      An example input "sxdddd", default value for an unspecified column is "d"''')
  parser.add_argument('--default-in-type', type=str, default='d', help='Default input type for unspecified columns')
  parser.add_argument('--preserve-white-space', action='store_true',
                      help='Preservece white spaces during reading')

  # action related
  parser.add_argument('-a', '--actions', action='append', nargs='*', type=str,
                      help='''
                      Actions applied to the input.
                      Available actions:
                      sel col1 [col2 ...]
                      add col1 col2
                      sub col1 col2
                      mul col1 col2
                      div col1 col2
                      grp:sum keycol1 [keycol2 ...] - sumcol1 [sumcol2 ...]
                      grp:cnt col1 [col2 ...]
                      avg col1 [col2 ...]
                      sum col1 [col2 ...]
                      max col1 [col2 ...]
                      min col1 [col2 ...]
                      blk
                      ''')

  # output related
  parser.add_argument('-p', '--preserve', action='store_true',
                      help='preserve columns in the original files')
  parser.add_argument('-w', '--width', type=int, default=10,
                      help='Minimum width of a column')
  parser.add_argument('-D', '--out-delimiter', type=str, default=', ',
                      help='Output delimiter')
  parser.add_argument('--default-out-type', type=str, default='',
                      help='Default output type for unspecified columns')

  parser.add_argument('filename', nargs='?', type=str, default='')

  args = parser.parse_args()

  files = [args.filename, ] if args.filename else []
  with fileinput.input(files=files) as fd:
    celi = CeliCore(fd, args)
    celi.run()
