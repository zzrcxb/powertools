# What is Lapi-plus
This tool is based on [Lapidary](https://github.com/efeslab/lapidary), which aims at creating "beautiful" Gem5 simulations. However, due to the slow speed of GDB `stepi`, trying to create a checkpoint after a certain number of instructions is slower than Gem5 **detailed** simulation! **Lapi-plus** uses Intel pintool to fast-forward the program to semantic breakpoints and creates Gem5 checkpoints based on them. Lapi-plus also optimized Lapidary's code and fixed some bugs.

This tool has been slightly tested on Debian Buster with Python 3.7.3.

# Dependencies
Lapi-plus depends on system tools `gdb` and [Intel pintool](https://software.intel.com/en-us/articles/pin-a-binary-instrumentation-tool-downloads).

Lapi-plus also depends on Python 3. Lapi-plus has been tested on Python 3.7.3, it should be compatible with earlier Python 3.x versions.

Python dependencies are listed in the tool's `requirements.txt`

## For Debian/Ubuntu users
```sudo apt install gdb```
`pip3 install -r lapi-plus/requirements.txt --user` or
`sudo pip3 install -r lapi-plus/requirements.txt`

## Attention
Based on my observation, when GDB executes a Python script, it ignores the virtual environment. So, please install Python dependencies to the environment without virtualenv. Maybe there's a way to tell GDB to use virtualenv...

# Run
## Configuration
`config.json` contains necessary information to run the tool.

`run-dir` is the path to the benchmark's run directory.

`cmd` is the command to start the benchmark program **when you are in its run directory**.

`ckpt-prefix` is the path to the checkpoints output directory.

## Setup
Lapi-plus depends `brkpt` in inscount tool. For detailed information about using `brkpt`, please refer to the README in `inscount` directory.

Start the pintool with:
```$PIN_ROOT/pin -appdebug_enable -appdebug_silent -t /path/to/brkpt.so -- <benchmark commands>```
Then start GDB with:
```gdb /path/to/benchmark-application --batch -x GDBDriver.py < config.json```
