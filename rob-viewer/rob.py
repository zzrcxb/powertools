#! /usr/bin/env python3

import fileinput
import termcolor
import curses
import time
import sys


class ROBInst:
  def __init__(self, pc, isLoad, isControl, prevInstsComplete=0, prevBrsResolved=0, prevInstsCommitted=0, prevBrsCommitted=0, readyToCommit=0, fault=0, squashed=0):
    self.pc = pc
    self.isLoad = isLoad
    self.isControl = isControl
    self.prevInstsComplete = prevInstsComplete
    self.prevBrsResolved = prevBrsResolved
    self.prevInstsCommitted = prevInstsCommitted
    self.prevBrsCommitted = prevBrsCommitted
    self.readyToCommit = readyToCommit
    self.fault = fault
    self.squashed = squashed

  def __str__(self):
    if self.isLoad and self.isControl:
      type_flag = 'L C'
    elif self.isLoad and not self.isControl:
      type_flag = 'L  '
    elif not self.isLoad and self.isControl:
      type_flag = 'C  '
    else:
      type_flag = '   '
    other_flags = [self.prevInstsComplete, self.prevBrsResolved, self.prevInstsCommitted, self.prevBrsCommitted, self.readyToCommit, self.fault, self.squashed]
    other_flags = list(map(str, other_flags))
    return '{:<8} {} {}'.format(hex(self.pc), type_flag, ' '.join(other_flags))

  def __repr__(self):
    return self.__str__()

  def __eq__(self, a):
    return self.pc == a.pc


class ROBViewer:
  def __init__(self, filepath, microPC=False, cache_length=10000):
    self.filepath = filepath
    self.cache_length = cache_length
    self.microPC = microPC
    self.index = -1
    self.base_cycle = 0
    self.entries = []
    self.EOF = False
    self.fd = fileinput.input(files=[self.filepath])
    self.next()

  def _parse(self, line):
    def parse_inst(inst):
      splitted = inst.split(',')
      pc = int(splitted[0], base=16)
      flags = list(map(int, splitted[1:]))
      return [pc, ] + flags

    raw_insts = line.split(';')[:-1]
    insts = [ROBInst(*parse_inst(inst)) for inst in raw_insts]
    return insts

  def _pass(self, lineno):
    self.base_cycle = self.cycle
    self.index = 0
    self.entries.clear()
    cnt = 0
    for _ in zip(range(lineno), self.fd):
      self.base_cycle += 1
      cnt += 1
    if cnt != lineno:
      self.EOF = True
      return False

  def _load(self, linenum=1):
    if self.EOF or linenum < 1:
      return False

    loaded = []
    for _, line in zip(range(linenum), self.fd):
      loaded.append(self._parse(line))

    # flush
    new_length = len(loaded) + len(self.entries)
    if new_length > self.cache_length:
      exceeded = new_length - self.cache_length
      del self.entries[:exceeded]
      self.index -= exceeded
      self.base_cycle += exceeded

    self.entries.extend(loaded)

    # EOF
    if len(loaded) < linenum:
      self.EOF = True
      self.fd.close()
      return False
    else:
      return True

  def next(self, cnt=1, batch_load=1):
    need2load = self.index + cnt + 1 - len(self.entries)
    linenum = max(need2load, batch_load)
    if need2load > 0:
      if linenum > self.cache_length:
        self._pass(linenum - self.cache_length)
        if not self._load(linenum=self.cache_length):
          self.index = self.cache_length - 1 # reach the end of file
          return False
        else:
          self.index = self.cache_length - 1
          return True
      else:
        if not self._load(linenum=linenum):
          self.index = self.cache_length - 1 # reach the end of file
          return False

    self.index += cnt
    return True

  def prev(self, step=1):
    self.index -= step
    if self.index < 0: # at the head of the cache
      self.index = 0
      return False
    else:
      return True

  def move(self, step):
    if step == 0:
      return True
    elif step > 0:
      return self.next(step)
    else:
      return self.prev(step)

  def search(self, pc, condition=None, skip=None):
    if skip:
      self.move(skip)
    pc = ROBInst(pc, 0, 0)
    if not callable(condition):
      condition = lambda: True

    while pc not in self.snapshot_now and not self.EOF and condition():
      self.next()

  def jump(self, cycle):
    cur_cycle = self.cycle
    distance = cycle - cur_cycle
    return self.move(distance)

  @property
  def snapshot_now(self):
    if self.index == -1:
      raise ValueError('Invalid index -1, need to call next first')
    return self.entries[self.index]

  @property
  def cycle(self):
    return self.base_cycle + self.index + 1


class ROBWin:
  def __init__(self, height, width, y, x, margins, paddings, header=None, footer=None, boarder=True, numbered=True, start_number=1, highlights=None):
    ''' margins: top, right, bottom, left
    '''
    margins, paddings = list(margins), list(paddings)
    self.win = curses.newwin(height, width, y, x)
    self.height, self.width = height, width
    self.margins, self.paddings = margins, paddings
    self.header, self.footer = header, footer
    self.numbered, self.start_number = numbered, start_number
    self.boarder = boarder
    self.highlights = highlights if highlights else []

    if header and margins[0] == 0:
      margins[0] = 1

    if footer and margins[2] == 0:
      margins[2] = 1

    self.numbered = self.numbered and boarder
    if numbered and len(str(self.start_number + self.avai_height)) > self.margins[3]:
      self.margins[3] += len(str(self.start_number + self.avai_height))

    self.avai_height_with_padding = self.avai_height + self.paddings[0] + self.paddings[2]
    self.avai_width_with_padding = self.avai_width + self.paddings[1] + self.paddings[3]
    if boarder:
      self.paint_boarder()
    if numbered:
      self.paint_lineno()
    self.paint_header_footer()
    self.rewind()

  def rewind(self):
    if self.boarder:
      self.cursor = [self.margins[0] + self.paddings[0] + 1, self.margins[3] + self.paddings[3] + 1]
    else:
      self.cursor = [self.margins[0] + self.paddings[0], self.margins[3] + self.paddings[3]]

  @property
  def avai_width(self):
    if self.boarder:
      return self.width - (self.margins[1] + self.margins[3] + self.paddings[1] + self.paddings[3] + 2)
    else:
      return self.width - (self.margins[1] + self.margins[3] + self.paddings[1] + self.paddings[3])

  @property
  def avai_height(self):
    if self.boarder:
      return self.height - (self.margins[0] + self.margins[2] + self.paddings[0] + self.paddings[2] + 2)
    else:
      return self.height - (self.margins[0] + self.margins[2] + self.paddings[0] + self.paddings[2])

  def paint_boarder(self):
    # top
    self.win.addstr(self.margins[0], self.margins[3], '_' * (self.avai_width_with_padding + 2))
    # bottom
    self.win.addstr(self.height - 1 - self.margins[2], self.margins[3], '-' * (self.avai_width_with_padding + 2))
    # left & right
    for i in range(self.avai_height_with_padding + 1):
      self.win.addstr(self.margins[0] + 1 + i, self.margins[3], '|')
      self.win.addstr(self.margins[0] + 1 + i, self.width - self.margins[1] - 1, '|')

  def paint_header_footer(self):
    if self.header:
      self._insert(self.header, self.margins[0] - 1, self.margins[3], self.avai_width_with_padding + 2)
    if self.footer:
      self._insert(self.footer, self.height - self.margins[2], self.margins[3], self.avai_width_with_padding + 2)

  def paint_lineno(self):
    length = len(str(self.avai_height + self.start_number))
    for i in range(self.avai_height):
      num = '{{:>{}}}'.format(length).format(self.start_number + i)
      self.win.addstr(self.margins[0] + 1 + i, self.margins[3] - length, num)

  def clear(self):
    self.rewind()
    for i in range(self.avai_height):
      self.insert_text(' ' * self.avai_width)
    self.rewind()

  def _insert(self, s, y, x, max_wdith, centered=True, highlight=None):
    if len(s) > max_wdith:
      s = s[:max_wdith - 3]
      s += '...'
    if centered:
      front_padding = (max_wdith - len(s)) // 2
      s = ' ' * front_padding + s

    if highlight:
      highlight_str = highlight[0]
      highlight_code = highlight[1]
      splitted = s.split(highlight_str)
      offset = 0
      for index, i in enumerate(splitted):
        self.win.addstr(y, x + offset, i)
        offset += len(i)
        if index < len(splitted) - 1:
          self.win.addstr(y, x + offset, highlight_str, curses.color_pair(highlight_code) | curses.A_BOLD)
          offset += len(highlight_str)

    else:
      self.win.addstr(y, x, s)

  def refresh(self):
    self.win.refresh()

  def insert_text(self, s, centered=False):
    lastline = self.height - 1 - self.margins[2] - self.paddings[2]
    if self.boarder:
      lastline -= 1
    if self.cursor[0] > lastline:
      return False
    else:
      highlight = None
      for h, c in self.highlights:
        if h in s:
          highlight = (h, c)
          break
      self._insert(s, *self.cursor, self.avai_width, centered=centered, highlight=highlight)
      self.cursor[0] += 1
      return True


class INFOWin:
  def __init__(self, height, width, y, x):
    self.win = curses.newwin(height, width, y, x)
    self.height, self.width = height, width

  def update_cycle(self, cycle):
    self.win.addstr(0, 0, ' ' * self.width)
    self.win.addstr(0, 0, 'Cycle: {}'.format(cycle), curses.A_REVERSE)

  def add_msg(self, msg):
    self.win.addstr(2, 0, ' ' * self.width)
    self.win.addstr(2, 0, msg)

  def refresh(self):
    self.win.refresh()


class INPUTWin:
  def __init__(self, height, width, y, x, robview):
    self.win = curses.newwin(height, width, y, x)
    self.height, self.width = height, width
    self.robview = robview

  def input(self):
    self.win.clear()
    curses.echo()
    self.win.addstr(1, 0, ':')
    self.win.refresh()
    user_input = self.win.getstr(1, 1, self.width - 1)
    self.process(user_input)

  def process(self, user_input):
    user_input = user_input.strip()
    self.win.addstr(2, 0, 'Executing...')
    self.win.refresh()
    try:
      user_input = user_input.decode('utf-8')
      exec('self.robview.{}'.format(user_input))
      self.win.clear()
    except:
      self.win.clear()
      self.win.addstr(2, 0, 'Invalid command')
    finally:
      curses.noecho()

  def refresh(self):
    self.win.refresh()


class CLIPainter:
  def __init__(self, stdscr, robview, cols=4, highlights=None):
    curses.start_color()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_WHITE)
    curses.init_pair(2, curses.COLOR_BLUE, curses.COLOR_WHITE)
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_MAGENTA, curses.COLOR_BLACK)


    self.robview = robview
    self.stdscr = stdscr
    self.rob_wins = []
    start_counter = 1
    for i in range(cols):
      if i == 0:
        win = ROBWin(curses.LINES - 5, curses.COLS // cols, 0, (curses.COLS // cols) * i, [2, 1, 1, 3], [0, 1, 0 ,1], header='HEAD', footer='--->', start_number=start_counter, highlights=highlights)
      elif i == cols - 1:
        win = ROBWin(curses.LINES - 5, curses.COLS // cols, 0, (curses.COLS // cols) * i, [2, 1, 1, 3], [0, 1, 0 ,1], header='<---', footer='TAIL', start_number=start_counter, highlights=highlights)
      else:
        win = ROBWin(curses.LINES - 5, curses.COLS // cols, 0, (curses.COLS // cols) * i, [2, 1, 1, 3], [0, 1, 0 ,1], header='<---', footer='--->', start_number=start_counter, highlights=highlights)
      start_counter += win.avai_height
      self.rob_wins.append(win)
    self.info_win = INFOWin(4, curses.COLS // 3, curses.LINES - 5, 2 * curses.COLS // 3)
    self.input_win = INPUTWin(4, 2 * curses.COLS // 3 - 1, curses.LINES - 5, 1, self.robview)
    self.main_loop()

  def main_loop(self):
    while True:
      self.draw_rob()
      self.refresh()
      c = self.info_win.win.getch()
      if c == ord('q'):
        break
      elif c == ord(':'):
        self.input_win.input()
      elif c == 67:
        self.robview.next()
      elif c == 68:
        self.robview.prev()
      elif c == 66:
        self.robview.next(100)
      elif c == 65:
        self.robview.prev(100)


  def refresh(self):
    for win in self.rob_wins:
      win.refresh()
    self.info_win.refresh()
    self.input_win.refresh()

  def draw_rob(self):
    for win in self.rob_wins:
      win.clear()

    windex = 0
    for i in self.robview.snapshot_now:
      while windex < len(self.rob_wins) and not self.rob_wins[windex].insert_text(str(i)):
        windex += 1
      if windex == len(self.rob_wins):
        break

    if windex == len(self.rob_wins):
      win = self.rob_wins[-1]
      win.cursor[0] -= 1
      win.insert_text(' ' * win.avai_width)
      win.cursor[0] -= 1
      win.insert_text('...', centered=True)

    self.info_win.update_cycle(self.robview.cycle)



if __name__ == "__main__":
  import sys
  import argparse

  parser = argparse.ArgumentParser('rob.py')
  parser.add_argument('-c', '--cols', type=int, default=3, help='ROB viewer column #')
  parser.add_argument('-H', '--highlights', type=str, nargs='*', help='PCs need to be highlight')
  parser.add_argument('filepath', help='Path to the ROB file')
  args = parser.parse_args()
  AVAILABLE_COLOR_PAIRS = 6

  if args.highlights:
    highlights = [(h, i % AVAILABLE_COLOR_PAIRS + 1) for i, h in enumerate(args.highlights)]

  robview = ROBViewer(args.filepath)
  curses.wrapper(CLIPainter, robview, highlights=highlights, cols=args.cols)
