import os
import re
from pathlib import Path


class SPEC_CONFIG:
  SPEC06_PROGRAMS = ['astar', 'bwaves', 'bzip2', 'gamess', 'GemsFDTD', 'gobmk', 'h264ref', 'hmmer', 'lbm', 'leslie3d', 'libquantum', 'mcf', 'milc', 'namd', 'omnetpp', 'sjeng', 'soplex', 'sphinx3', 'tonto', 'zeusmp']

  SPEC17_PROGRAMS_RATE = ['500.perlbench_r', '502.gcc_r', '505.mcf_r', '520.omnetpp_r', '523.xalancbmk_r', '525.x264_r', '531.deepsjeng_r', '541.leela_r', '548.exchange2_r', '557.xz_r', '503.bwaves_r', '507.cactuBSSN_r', '508.namd_r', '510.parest_r', '511.povray_r', '519.lbm_r', '521.wrf_r', '526.blender_r', '527.cam4_r', '538.imagick_r', '544.nab_r', '549.fotonik3d_r', '554.roms_r']

  ROOT_DIR = Path(os.getenv('SPEC', ''))

  INPUT_SIZE = 'ref'
  TUNE = 'base'

  COMPILER_CONFIG = 'docker-clang'

  _benchmark_suites = {
    'SPEC06': SPEC06_PROGRAMS,
    'SPEC17R': SPEC17_PROGRAMS_RATE,
    'SPEC17Rate': SPEC17_PROGRAMS_RATE
  }

  def __init__(self, suite):
    if suite not in self._benchmark_suites:
      raise ValueError('Invalid benchmark suite option {}'.format(suite))
    self._suite = suite
    self.version = re.findall(r'\d+', suite)[0]

  @property
  def programs(self):
    return self._benchmark_suites[self._suite]

  @property
  def benchmark_root(self):
    rel_path = 'benchspec/CPU' if self.version == '17' else 'benchspec/CPU2006'
    return self.ROOT_DIR / rel_path

  @property
  def specrun(self):
    return 'runcpu' if self.version == '17' else 'runspec'

  @property
  def compiler_config(self):
    return self.COMPILER_CONFIG


class PIN_CONFIG:
  PIN_ROOT = Path(os.getenv('PIN_ROOT', ''))

  def __init__(self, toolset_root):
    path = Path(toolset_root)
    if not path.is_absolute():
      self.toolset_root = path.resolve(strict=True)
    self.toolset_root = path
    assert(self.toolset_root.exists())

  def get_tool_path(self, name):
    return self.toolset_root / 'obj-intel64' / (name + '.so')


class SIMPOINT_CONFIG:
  SIMP_PATH = Path(os.getenv('SIMPOINT', ''))
  WEIGHT_FILE = 'results.weights'
  CKPT_FILE = 'results.simpts'
  BRKT_FILE = 'out.brk'
  BBV_FILE = 'out.bb'


class LAPI_CONFIG:
  ROOT_DIR = Path(os.getenv('LAPI', ''))
  PORT_FILE = '.portinfo'

# SPEC_ROOT = "/root/spec"
# SPEC_BENCH_ROOT = os.path.join(SPEC_ROOT, "benchspec/CPU2006")
# SPEC_CONFIG = "linux64-clang-fence"
# RUN_ROOT = "/home/neil/Archive/run-fence"
# RUN_ROOT_DOCKER = "/root/run"

# PIN_ROOT = "/home/neil/pin-3.7"
# DIAMOND_SCRIPT = "/home/neil/diamond/bin_ana/run.py -S0"
# DIAMOND_COUNTER = "/home/neil/diamond/bin_ana/count_res.py"

# IF_SPEC_LOG = True
# SPEC_LOG_DIR = "/root/spec_log"

# IS_PIN_LOG = True
# PIN_LOG_DIR = "/home/neil/run/pin_log"
