#! /usr/bin/env python3

import subprocess
import argparse
import re
import platform
import sys


PYTHON_INTERPRETER = 'python' if platform.system() == 'Windows' else 'python3'


def translate(source: str, stdin_cp: str, stdout_cp: str, context: dict={}, defs: list=[], indentation: int=4):
  string_pattern = re.compile(r'([ \t]*)#([^\r\n]+)')
  leading_ws = re.compile(r'^[ \t]*')

  HEAD = [
    '#!/usr/bin/env python3',
    'import sys'
  ]

  for name, value in context.items():
    HEAD.append('{} = {}'.format(name, repr(value)))

  for d in defs:
    HEAD.append(d)

  lines = source.split('\n')
  for index, s in enumerate(lines):
    m_obj = string_pattern.match(s)
    if m_obj:
      tmp_str = m_obj.group(2)
      cmt_obj = string_pattern.match(tmp_str)
      if not cmt_obj:
        l_ws = leading_ws.match(tmp_str).group(0).replace('\t', ' ' * indentation)
        tmp_str = ' ' * (len(l_ws) // indentation) * indentation + tmp_str.lstrip()
        indent = (len(m_obj.group(1).replace('\t', '    ')) // indentation) * indentation
        tail = '\\n'
        if tmp_str.endswith('#') and not tmp_str.endswith('\\#'):
          tail = ''
          tmp_str = tmp_str[:-1]
        tmp_str = tmp_str.replace('{', '{{').replace('}', '}}').replace('{<', '').replace('>}', '').replace('\r', '').replace('\\#', '#').replace('"', '\\"')
        tmp_str += tail
        tmp_str = ' ' * indent + 'sys.stdout.buffer.write("{raw}".format(**locals()).encode("{cp}"))'.format(raw=tmp_str, cp=stdout_cp)
      lines[index] = tmp_str

  p = subprocess.Popen([PYTHON_INTERPRETER, '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
  stdout, stderr = p.communicate('\n'.join(HEAD + lines).encode(stdin_cp))
  return stdout.decode(stdout_cp)


if __name__ == '__main__':
  import json

  parser = argparse.ArgumentParser()
  parser.add_argument('-c', '--codepage', type=str, help='Set codepage for your input file or strings and communication to python.')
  parser.add_argument('-i', '--input', type=str, help='Set input file name.')
  parser.add_argument('-o', '--output', type=str, help='output file name')
  parser.add_argument('-p', '--pipe', help='Get input from pipe, and it will override -i option', action='store_true')
  parser.add_argument("-I", "--indentation", type=int, default=4, help="Indentation")
  parser.add_argument('--context', type=str, help='Specify context by passing a json string')
  args, defs = parser.parse_known_args()

  stdin_cp = args.codepage if args.codepage else sys.stdin.encoding
  stdout_cp = args.codepage if args.codepage else sys.stdout.encoding
  fs_cp = args.codepage if args.codepage else sys.getfilesystemencoding()

  if args.pipe:
    s = sys.stdin.buffer.read().decode(stdin_cp)
  elif args.input:
    with open(args.input, 'r', encoding=args.codepage) as f:
      s = f.read()
  else:
    sys.stderr.write('An input file or pipe is required')
    exit(1)

  context = json.loads(args.context) if args.context else {}

  res = translate(s, stdin_cp, stdout_cp, context, defs, args.indentation)

  if args.output:
    with open(args.output, 'w', encoding=fs_cp) as f:
      f.write(res)
  else:
    sys.stdout.buffer.write(res.encode(stdout_cp))
