#include <iostream>
#include <string>
#include <cstdio>
#include <cstdint>
#include <unordered_map>
#include <map>
#include <fstream>
#include "pin.H"
#include "utils.h"
#include <sys/types.h>
#include <unistd.h>    // for sbrk and getpid


#define MSGFILE ".pininfo"
#define PORTFILE ".portinfo"

using namespace std;

typedef uint64_t Addr;
typedef pair<Addr, uint64_t> Breakpoint;
typedef pair<Addr, uint64_t> Record;

unordered_map<Addr, uint64_t> inscount;
map<Breakpoint, int> brkIDMap;
map<Breakpoint, bool> visited;
int CUR_ID = -1;

KNOB<string> KnobInputFile(KNOB_MODE_WRITEONCE, "pintool",
              "b", "break.txt", "specify input file name");

KNOB<string> KnobRunDir(KNOB_MODE_WRITEONCE, "pintool",
              "r", ".",
              "run directory of the application, this is for saving intermidiate files. PLEASE AVOID conflicts!!!");

KNOB<UINT32> KnobTimeout(KNOB_MODE_WRITEONCE, "pintool",
    "timeout", "0",
    "wait for this <timeout> seconds for debugger to connect (zero means wait forever)");


void DoBreakpoint(const CONTEXT *, THREADID);
void ConnectDebugger();
void load_breakpoints();


ADDRINT update_counter(ADDRINT addr) {
  // update counter for PCs that are set as breakpoints
  // return 1 if the breakpoint is triggered
  inscount[addr] += 1;
  auto record = Breakpoint(addr, inscount[addr]);
  if (IN_MAP(record, brkIDMap)) {
    CUR_ID = brkIDMap[record];
    cerr << ZINFO
         << "Triggered breakpoint #" << CUR_ID << "; "
         << "PC: 0x" << hex << addr
         << ", CNT: " << dec << inscount[addr]
         << ", PID: " << getpid() << endl;
    if (visited[record]) {
      cerr << ZWARN
           << "Trying to re-visit a breakpoint, something is wrong! Breakpoint PC: "
           << hex << addr << ", CNT:"
           << dec << inscount[addr]
           << endl;
    }
    visited[record] = true;
    return 1;
  }
  else
    return 0;
}

void Instruction(INS ins, void *v) {
  // instrument instructions
  ADDRINT addr = INS_Address(ins);
  if (IN_MAP(addr, inscount)) {
    INS_InsertIfCall(ins, IPOINT_BEFORE, (AFUNPTR)update_counter, IARG_ADDRINT, addr, IARG_END);
    INS_InsertThenCall(ins, IPOINT_BEFORE, (AFUNPTR)DoBreakpoint, IARG_CONST_CONTEXT, IARG_THREAD_ID, IARG_END);
  }
}

void load_breakpoints() {
  // load break.txt
  string inputFilePath = KnobRunDir.Value() + "/" + KnobInputFile.Value();
  ifstream infile(inputFilePath.c_str());
  if (infile.is_open()) {
    Addr pc; uint64_t cnt; size_t brkID;
    while (infile >> brkID >> hex >> pc >> dec >> cnt) {
      inscount.insert(Record(pc, 0));
      brkIDMap.insert(make_pair(Breakpoint(pc, cnt), brkID));
      visited.insert(make_pair(Breakpoint(pc, cnt), false));
    }
    cerr << ZINFO
         << "Loaded " << brkIDMap.size() << " breakpoints"
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
  auto allVisited = true;
  for (auto p : visited) {
    // check completenesss of the break.txt
    if (!p.second)
      allVisited = false;
  }
  if (allVisited) {
    cerr << ZINFO
         << "Breakpoints clean, every one has been visited and its checkpoint has been created (hopefully)..."
         << endl << flush;
  }
  else {
    cerr << ZWARN
         << "Failed to reached some of breakpoints, please double check your break.txt file!" << endl
         << "List of unreached breakpints:" << endl
         << "PC, CNT" << endl;
    for (auto p : visited) {
      if (!p.second) {
        cerr << "0x" << hex << p.first.first << ", " << dec << p.first.second << endl;
      }
    }
    cerr << flush;
  }

  string infoFilePath = KnobRunDir.Value() + "/" + MSGFILE;
  remove(infoFilePath.c_str());

  if (allVisited)
    exit(0);
  else
    exit(1);
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

  cerr << ZINFO << "Start GDB and enter this command:" << endl
       << ZINFO << " target remote :" << dec << info._tcpServer._tcpPort << "\n";

  ofstream outfile;
  string portFilePath = KnobRunDir.Value() + "/" + PORTFILE;
  outfile.open(portFilePath.c_str(), ios::out);
  if (outfile.is_open()) {
    outfile << "{"
            << "\"port\": " << info._tcpServer._tcpPort
            << "}" << endl << flush;
    outfile.close();
  }
  else {
    cerr << ZERROR
         << "Failed to pass the port information for further steps, exiting..."
         << endl << flush;
    exit(1);
  }

  // start gdb server
  if (PIN_WaitForDebuggerToConnect(1000 * KnobTimeout.Value())) {
    remove(portFilePath.c_str()); // delete port file
    return;
  }

  cerr << ZERROR
       << "No debugger attached after " << KnobTimeout.Value() << " seconds. Exiting..."
       << endl;
  exit(2);
}

void DoBreakpoint(const CONTEXT *ctxt, THREADID tid) {
    ConnectDebugger();  // Ask the user to connect a debugger, if it is not already connected.

    // save necessary information
    auto brkPoint = (uint64_t)sbrk(0);
    auto fsBase = PIN_GetContextReg(ctxt, REG_SEG_FS_BASE);
    cerr << ZINFO
         << "brkID: #" << CUR_ID
         << ", pid: " << getpid() << hex
         << ", brkPoint: 0x" << brkPoint
         << ", fsBase: 0x" << fsBase
         << dec << endl << flush;

    auto allVisited = true;
    for (auto p : visited) {
      // check completenesss of the break.txt
      if (!p.second)
        allVisited = false;
    }

    string infoFilePath = KnobRunDir.Value() + "/" + MSGFILE;
    ofstream outfile;
    outfile.open(infoFilePath.c_str(), ios::out);
    if (outfile.is_open()) {
      outfile << "{"
              << "\"brkID\": " << CUR_ID << ", "
              << "\"pid\": " << getpid() << ", "
              << "\"brkPoint\": " << brkPoint << ", "
              << "\"fsBase\": " << fsBase << ", "
              << "\"allVisited\": " << allVisited
              << "}" << endl << flush;
      outfile.close();
    }
    else {
      cerr << ZERROR
           << "Failed to pass the runtime information for further steps, exiting..."
           << endl << flush;
      exit(0);
    }

    PIN_ApplicationBreakpoint(ctxt, tid, FALSE, "TickTok!");
}
