# What is Inscount
This tool-set contains several Intel pintool plugins to analyze a program's runtime behavior.

# Build
### Download Pintool
[Intel pintool download page.](https://software.intel.com/en-us/articles/pin-a-binary-instrumentation-tool-downloads)

The tool-set has been tested on Pintool 3.11.

### Setup ENV and build
```shell
export PIN_ROOT=/path/to/pin-directory
make -j$(nproc)
```

# Guide for each plugin
### bbv
It generates basic block vector (BBV) files for Simpoint and a breakpoints file for each program slice.

```shell
-r path to the benchmark's run directory
-i save BBV every <i> X 1,000,000 instructions
-s skip first <s> instructions
-bbv BBV filename
-brk breakpoints filename
```



### brkpt
Input breakpoint file `break.txt`'s format is:
```<breakpoint ID> <breakpoint PC> <cnt>```
The tool fast-forwards program until `<breakpoint PC>` has been visited `<cnt>` times (before `<cnt>` time execution) and starts a remote GDB server.

```shell
-b breakpoint filename
-r run directory of the application, this is for saving intermidiate files. PLEASE AVOID conflicts!!!
-timeout wait for this <timeout> seconds for debugger to connect (zero means wait forever)
```



### TBD
