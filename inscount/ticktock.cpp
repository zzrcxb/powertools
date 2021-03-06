#include <stdio.h>
#include "pin.H"
#include "utils.h"
#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <map>
#include <set>


using namespace std;

map<uint64_t, uint64_t> tick_count;
map<uint64_t, uint64_t> tock_count;
map<uint64_t, uint64_t> old_tock_count;

uint64_t icounter = 0;

KNOB<string> KnobInputFile(KNOB_MODE_WRITEONCE, "pintool",
              "i", "ticktock.txt", "specify input file name");

KNOB<string> KnobOutputFile(KNOB_MODE_WRITEONCE, "pintool",
              "o", "cnt.csv", "specify output file name");

ofstream outfile;

void counter(ADDRINT addr) {
  tock_count[addr] += 1;
}


void pause_and_print(ADDRINT addr) {
  tick_count[addr]++;
  outfile << "# ===== 0x" << hex << addr << ", " << dec << tick_count[addr] << ", " << icounter << " =====" << endl;
  for (auto &p : tock_count) {
    outfile << "\t0x" << hex << p.first << ", " << dec << p.second - old_tock_count[p.first] << ", " << p.second << endl;
    old_tock_count[p.first] = p.second;
  }
}


void Instruction(INS ins, void *v) {
  ADDRINT addr = INS_Address(ins);
  if (IN_MAP(addr, tock_count)) {
    INS_InsertCall(ins, IPOINT_BEFORE, (AFUNPTR)counter, IARG_ADDRINT, addr, IARG_END);
  }
  if (IN_MAP(addr, tick_count)) {
    INS_InsertCall(ins, IPOINT_BEFORE, (AFUNPTR)pause_and_print, IARG_ADDRINT, addr, IARG_END);
  }
}


void accumulator(uint64_t step) {
  icounter += step;
}


void Trace(TRACE trace, void *v) {
  for (BBL bbl = TRACE_BblHead(trace); BBL_Valid(bbl); bbl = BBL_Next(bbl)) {
    BBL_InsertCall(bbl, IPOINT_BEFORE, (AFUNPTR)accumulator, IARG_UINT64, BBL_NumIns(bbl), IARG_END);
  }
}


void Fini(INT32 code, void *v) {
  outfile.close();
}


void load() {
  ifstream infile(KnobInputFile.Value().c_str());
  uint64_t pc;
  string flag;

  while (infile >> hex >> pc >> flag) {
    if (flag == "TICK" || flag == "tick") {
      tick_count[pc] = 0;
    }
    else if (flag == "TOCK" || flag == "tock") {
      tock_count[pc] = 0;
      old_tock_count[pc] = 0;
    }
    else {
      cerr << "[Error] Invalid flag! \"" << flag << "\"" << endl;
      exit(1);
    }
  }
}


INT32 Usage() {
  PIN_ERROR("This Pintool prints the IPs of every instruction executed\n" + KNOB_BASE::StringKnobSummary() + "\n");
  return -1;
}


int main(int argc, char *argv[]) {
  // Initialize pin
  if (PIN_Init(argc, argv))
  return Usage();

  load();
  cerr << "loads loaded\n";

  outfile.open(KnobOutputFile.Value().c_str(), ios::out | ios::app);

  // Register Instruction to be called to instrument instructions
  INS_AddInstrumentFunction(Instruction, 0);
  TRACE_AddInstrumentFunction(Trace, 0);

  // Register Fini to be called when the application exits
  PIN_AddFiniFunction(Fini, 0);

  // Start the program, never returns
  PIN_StartProgram();

  return 0;
}
