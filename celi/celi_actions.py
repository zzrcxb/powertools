import argparse

from celi_base import CeliAction, enforce_width
from collections import OrderedDict


class CeliSel(CeliAction):
  def _parse(self, params):
    return self._parse_unary(params)

  def __len__(self):
    if self.params[0][0] == '*':
      return self.in_length
    else:
      return len(self.params[0])

  @enforce_width
  def header(self, headers):
    if self.params[0][0] == '*':
      return headers
    else:
      return [headers[p] for p in self.params[0]]

  @enforce_width
  def execute(self, row):
    if self.params[0][0] == '*':
      tp = '{{:{}}}'.format(self.fmt_codes[0])
      return [tp.format(e) for e in row]
    else:
      return ['{{:{}}}'.format(fmt).format(row[p]) for p, fmt in zip(self.params[0], self.fmt_codes)]


class CeliAdd(CeliAction):
  def _parse(self, params):
    return self._parse_binary(params)

  def __len__(self):
    return 1

  @enforce_width
  def header(self, headers):
    col1, col2 = self.params[0]
    inst1, inst2 = self.instant_numbers
    header1 = headers[col1] if not inst1 else col1
    header2 = headers[col2] if not inst2 else col2
    return ['{}+{}'.format(header1, header2)]

  @enforce_width
  def execute(self, row):
    col1, col2 = self.params[0]
    inst1, inst2 = self.instant_numbers
    elem1 = row[col1] if not inst1 else col1
    elem2 = row[col2] if not inst2 else col2
    tp = '{{:{}}}'.format(self.fmt_codes[0])
    return [tp.format(elem1 + elem2)]


class CeliSub(CeliAction):
  def _parse(self, params):
    return self._parse_binary(params)

  def __len__(self):
    return 1

  @enforce_width
  def header(self, headers):
    col1, col2 = self.params[0]
    inst1, inst2 = self.instant_numbers
    header1 = headers[col1] if not inst1 else col1
    header2 = headers[col2] if not inst2 else col2
    return ['{}-{}'.format(header1, header2)]

  @enforce_width
  def execute(self, row):
    col1, col2 = self.params[0]
    inst1, inst2 = self.instant_numbers
    elem1 = row[col1] if not inst1 else col1
    elem2 = row[col2] if not inst2 else col2
    tp = '{{:{}}}'.format(self.fmt_codes[0])
    return [tp.format(elem1 - elem2)]


class CeliMul(CeliAction):
  def _parse(self, params):
    return self._parse_binary(params)

  def __len__(self):
    return 1

  @enforce_width
  def header(self, headers):
    col1, col2 = self.params[0]
    inst1, inst2 = self.instant_numbers
    header1 = headers[col1] if not inst1 else col1
    header2 = headers[col2] if not inst2 else col2
    return ['{}*{}'.format(header1, header2)]

  @enforce_width
  def execute(self, row):
    col1, col2 = self.params[0]
    inst1, inst2 = self.instant_numbers
    elem1 = row[col1] if not inst1 else col1
    elem2 = row[col2] if not inst2 else col2
    tp = '{{:{}}}'.format(self.fmt_codes[0])
    return [tp.format(elem1 * elem2)]


class CeliDiv(CeliAction):
  def _parse(self, params):
    return self._parse_binary(params)

  def __len__(self):
    return 1

  @enforce_width
  def header(self, headers):
    col1, col2 = self.params[0]
    inst1, inst2 = self.instant_numbers
    header1 = headers[col1] if not inst1 else col1
    header2 = headers[col2] if not inst2 else col2
    return ['{}/{}'.format(header1, header2)]

  @enforce_width
  def execute(self, row):
    col1, col2 = self.params[0]
    inst1, inst2 = self.instant_numbers
    elem1 = row[col1] if not inst1 else col1
    elem2 = row[col2] if not inst2 else col2
    tp = '{{:{}}}'.format(self.fmt_codes[0])
    try:
      return [tp.format(elem1 / elem2)]
    except ZeroDivisionError:
      return ['nan']


class CeliGrp(CeliAction):
  def _parse(self, params):
    self.pool = OrderedDict()

    if self.subcmds[0] == 'sum':
      if len(params) == 2 and len(params[0]) > 0 and len(params[1]) > 0:
        ps1, codes1 = self._arg_list_splitter(params[0])
        ps2, codes2 = self._arg_list_splitter(params[1])
        return [tuple(map(int, ps1)), tuple(map(int, ps2))], codes1 + codes2

      raise argparse.ArgumentTypeError(
          'grp:sum takes two argument lists')

    elif self.subcmds[0] == 'cnt':
      if len(params) == 1 and len(params[0]) > 0:
        pss, codes = self._parse_unary(params)
        ps = pss[0]
        if ps[-1] == '':
          del ps[-1]
        else:
          codes.append('{}d'.format(self.width))
        return [ps, ], codes

      raise argparse.ArgumentTypeError(
          'grp:cnt takes at least one argument within one argument list')

  def __len__(self):
    if self.subcmds[0] == 'sum':
      return len(self.params[0]) + len(self.params[1])
    elif self.subcmds[0] == 'cnt':
      if self.params[0][0] == '*':
        return self.in_length + 1
      else:
        return len(self.params[0]) + 1

  def validate(self):
    if len(self.subcmds) != 1 or self.subcmds[0] not in {'sum', 'cnt'}:
      raise argparse.ArgumentTypeError('Invalid sub command {} for grp'.format(self.subcmds[0]))
    self.map = dict()

  @enforce_width
  def header(self, headers):
    header = []
    if self.subcmds[0] == 'sum':
      for p in self.params[0]:
        header.append(headers[p])
      for p in self.params[1]:
        header.append('sum({})-per-{}'.format(headers[p], '-'.join(header)))
    elif self.subcmds[0] == 'cnt':
      if self.params[0][0] == '*':
        header = headers
      else:
        for p in self.params[0]:
          header.append(headers[p])
      header.append('cnt(per {})'.format('-'.join(header)))
    return header

  @enforce_width
  def execute(self, row):
    if self.subcmds[0] == 'sum':
      key = tuple([row[p] for p in self.params[0]])
      if key in self.pool:
        value = self.pool[key]
        for index, p in enumerate(self.params[1]):
          value[index] += row[p]
      else:
        value = [row[p] for p in self.params[1]]
        self.pool[key] = value
    elif self.subcmds[0] == 'cnt':
      if self.params[0][0] == '*':
        key = tuple(row)
      else:
        key = tuple([row[p] for p in self.params[0]])
      if key in self.pool:
        self.pool[key][0] += 1
      else:
        self.pool[key] = [1, ]
    return []

  def close(self):
    for key, value in self.pool.items():
      yield self.width_enforcer(['{{:{}}}'.format(fmt).format(v) for v, fmt in zip(list(key) + list(value), self.fmt_codes)])
      # yield list(key) + list(value)
