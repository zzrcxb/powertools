import argparse


from functools import wraps



def enforce_width(func):
  @wraps(func)
  def wrapper(*args, **kwargs):
    self = args[0]
    return self.width_enforcer(func(*args, **kwargs))
  return wrapper



class CeliAction:
  def __init__(self, subcmds, params, cliArgs, in_length=5, preserve_fmt=None, width=10, default_fmt='s'):
    """
      preserve_fmt overrides default_fmt
      formats specified close to the cols # override preserve_fmt
      width works only when it is using the preserve_fmt
    """
    self.subcmds = subcmds
    self.preserve_fmt = preserve_fmt
    self.width = width
    self.default_fmt = default_fmt
    self.params, self.fmt_codes = self._parse(params)
    self.cliArgs = cliArgs
    self.validate()
    self.in_length = in_length

  def _parse(self, params):
    raise NotImplementedError

  def _parse_binary(self, params):
    def check_instant_number(s):
      return s.lower().endswith('i') or s.lower().endswith('f') or s.lower().endswith('x')

    def get_instant_number(s):
      if s.lower().endswith('i'):
        return int(s[:-1])
      elif s.lower().endswith('f'):
        return float(s[:-1])
      elif s.lower().endswith('x'):
        return int(s[:-1], base=16)
      else:
        return int(s)

    if len(params) == 1 and len(params[0]) == 2:
      ps, codes = self._arg_list_splitter(params[0])
      self.instant_numbers = tuple(map(check_instant_number, ps))
      return [tuple(map(get_instant_number, ps)), ], (codes[-1], )

    raise argparse.ArgumentTypeError('Binary actions take only two arguments within one argument list')

  def _parse_unary(self, params):
    if len(params) == 1 and len(params[0]) > 0:
      ps, codes = self._arg_list_splitter(params[0])
      if len(ps) == 1 and ps[0] == '*':
        return [ps, ], codes
      else:
        return [tuple(map(int, ps)), ], codes

    raise argparse.ArgumentTypeError(
        'Unary actions take at least one argument within one argument list')

  def _arg_list_splitter(self, arg_list):
    ps = []
    codes = []
    for index, arg in enumerate(arg_list):
      splitted = arg.split(':')
      if len(splitted) in range(2, 4):
        p, code = splitted[0], ':'.join(splitted[1:])
      elif ':' not in arg:
        if self.preserve_fmt:
          # TODO: fix preserve_fmt
          p, code = arg, '{}'.format(self.preserve_fmt[index])
        else:
          p, code = arg, self.default_fmt
      else:
        raise argparse.ArgumentTypeError(
          'Argument {} containts an invalid Python formatter'.format(arg))
      ps.append(p)
      codes.append(code)
    return ps, codes

  def header(self, headers):
    raise NotImplementedError

  def execute(self, row):
    raise NotImplementedError

  def close(self):
    raise StopIteration

  def validate(self):
    return True

  def width_enforcer(self, row):
    tp = '{{:>{}}}'.format(self.width)
    return [tp.format(s) for s in row]

  def __len__(self):
    raise NotImplementedError