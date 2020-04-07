import os
import sys
import logging
import datetime

from pathlib import Path
from colorama import Fore, Back, Style, init


init()  # make coloramam work for Windows


def verbose_level_switcher(verbose):
  return {
    0: logging.CRITICAL,
    1: logging.ERROR,
    2: logging.WARNING,
    3: logging.INFO,
    4: logging.DEBUG
  }.get(verbose, 3)


class LogFormatter(logging.Formatter):
  def __init__(self, style='{'):
    logging.Formatter.__init__(self, style=style)

  def format(self, record):
    stderr_template = '{asctime} {threadName}: ' + '{message}'
    prefix = '[{}{{levelname}}' + Fore.RESET + Back.RESET + Style.RESET_ALL + '] '

    all_formats = {
      logging.DEBUG:    logging.StrFormatStyle(prefix.format(Fore.LIGHTBLUE_EX + Style.DIM) + stderr_template),
      logging.INFO:     logging.StrFormatStyle(prefix.format(Fore.GREEN) + stderr_template),
      logging.WARNING:  logging.StrFormatStyle(prefix.format(Fore.YELLOW) + stderr_template),
      logging.ERROR:    logging.StrFormatStyle(prefix.format(Fore.RED) + stderr_template),
      logging.CRITICAL: logging.StrFormatStyle(prefix.format(Fore.RED + Back.WHITE + Style.BRIGHT) + stderr_template)
    }

    self._style = all_formats.get(record.levelno, logging.StrFormatStyle(logging._STYLES['{'][1]))
    self._fmt = self._style._fmt
    result = logging.Formatter.format(self, record)
    return result


def init_logger(level=logging.INFO, logger=logging.getLogger(), log_dir: str=None, file_prefix: str=None, fmt: str=None, console_fmt=LogFormatter):
  if isinstance(level, int):
    logger.setLevel(verbose_level_switcher(level))
  else:
    logger.setLevel(level)

  logger.name

  if fmt:
    log_formatter = logging.Formatter(fmt)
  else:
    log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(threadName)s: %(message)s")

  if log_dir:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    if file_prefix:
      log_path = log_dir / '{}-{}@{}'.format(file_prefix, logger.name, str(datetime.datetime.now()).replace(':', '-') + '.log')
    else:
      log_path = log_dir / '{}@{}'.format(logger.name, str(datetime.datetime.now()).replace(':', '-') + '.log')

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)

  console_handler = logging.StreamHandler(stream=sys.stderr)
  console_handler.setFormatter(console_fmt())
  logger.addHandler(console_handler)


if __name__ == "__main__":
  init_logger(level=logging.DEBUG)
  logging.debug('debug')
  logging.info('info')
  logging.warning('warning')
  logging.error('error')
  logging.critical('critical')
