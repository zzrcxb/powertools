#include <iostream>
#include <cstdint>
#include <unordered_map>
#include <fstream>
#include "pin.H"
#include "utils.h"
#include <sys/types.h>
#include <unistd.h>


using namespace std;

typedef uint64_t Addr;
typedef pair<Addr, uint64_t> Record;

unordered_map<Addr, uint64_t> inscount;
unordered_map<Addr, uint64_t> breakpoints;

KNOB<string> KnobInputFile(KNOB_MODE_WRITEONCE, "pintool",
              "b", "break.txt", "specify input file name");

KNOB<UINT32> KnobTimeout(KNOB_MODE_WRITEONCE, "pintool",
    "timeout", "0",
    "When using -stackbreak, wait for this many seconds for debugger to connect (zero means wait forever)");


void DoBreakpoint(const CONTEXT *, THREADID);
void ConnectDebugger();
void load_breakpoints();

ADDRINT update_counter(ADDRINT addr) {
  inscount[addr] += 1;
  if (inscount[addr] == breakpoints[addr])
    return 1;
  else
    return 0;
}

void Instruction(INS ins, void *v) {
  ADDRINT addr = INS_Address(ins);
  if (IN_MAP(addr, breakpoints)) {
    INS_InsertIfCall(ins, IPOINT_BEFORE, (AFUNPTR)update_counter, IARG_ADDRINT, addr, IARG_END);
    INS_InsertThenCall(ins, IPOINT_BEFORE, (AFUNPTR)DoBreakpoint, IARG_CONST_CONTEXT, IARG_THREAD_ID, IARG_END);
  }
}

void load_breakpoints() {
  ifstream infile(KnobInputFile.Value().c_str());
  if (infile.is_open()) {
    Addr pc; uint64_t cnt;
    while (infile >> hex >> pc >> dec >> cnt) {
      breakpoints.insert(Record(pc, cnt));
      inscount.insert(Record(pc, 0));
    }
    cerr << ZINFO
         << "Loaded " << breakpoints.size() << " breakpoints"
         << endl;
  }
  else {
    cerr << ZERROR
         << "Failed to open breakpoints file. Exiting..."
         << endl;
  }
}

void Fini(INT32 code, void *v) {
  cerr << ZINFO
       << "Execution finished..."
       << endl;
}

INT32 Usage() {
  PIN_ERROR("This Pintool prints the IPs of every instruction executed\n" + KNOB_BASE::StringKnobSummary() + "\n");
  return -1;
}

int main(int argc, char** argv) {
  if (PIN_Init(argc, argv))
    return Usage();

  load_breakpoints();
  INS_AddInstrumentFunction(Instruction, 0);
  PIN_AddFiniFunction(Fini, 0);
  PIN_StartProgram();

  return 0;
}


void ConnectDebugger() {
    if (PIN_GetDebugStatus() != DEBUG_STATUS_UNCONNECTED)
        return;

    DEBUG_CONNECTION_INFO info;
    if (!PIN_GetDebugConnectionInfo(&info) || info._type != DEBUG_CONNECTION_TYPE_TCP_SERVER)
        return;

    cerr << "Triggered inscount breakpoint.\n";
    cerr << "Start GDB and enter this command:\n";
    cerr << "  target remote :" << dec << info._tcpServer._tcpPort << "\n";
    cerr << flush;

    if (PIN_WaitForDebuggerToConnect(1000*KnobTimeout.Value()))
        return;

    cerr << "No debugger attached after " << KnobTimeout.Value() << " seconds.\n";
    cerr << "Resuming application without stopping.\n";
    cerr << flush;
}

void DoBreakpoint(const CONTEXT *ctxt, THREADID tid) {
    ConnectDebugger();  // Ask the user to connect a debugger, if it is not already connected.
    cerr << ZINFO
         << "pid: "
         << getpid()
         << endl;
    PIN_ApplicationBreakpoint(ctxt, tid, FALSE, "TickTok!");
}
