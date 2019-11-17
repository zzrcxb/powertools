#!/usr/bin/env python3

import re
import os
import sys


infile, outfile = sys.argv[1:]
d = open(infile, 'rb').read()

# Match CPUID(eax=0), "xor eax,eax" followed closely by "cpuid"
o = re.sub(b'(\x31\xc0.{0,32}?)\x0f\xa2', b'\\1\x66\x90', d)

open(outfile, 'wb').write(o)
os.chmod(outfile, 0o775)
