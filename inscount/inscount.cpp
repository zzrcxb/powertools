#include <stdio.h>
#include "pin.H"
#include "utils.h"
#include <map>
#include <vector>
#include <fstream>
#include <iostream>


using namespace std;


map<uint64_t, vector<uint64_t>> inscount;
vector<uint64_t> pcs;

uint64_t icounter = 0;
uint64_t oldcounter = 0;

KNOB<string> KnobInputFile(KNOB_MODE_WRITEONCE, "pintool",
              "i", "load.txt", "specify input file name");

KNOB<string> KnobOutputFile(KNOB_MODE_WRITEONCE, "pintool",
              "o", "cnt.csv", "specify output file name");

KNOB<string> KnobInterval(KNOB_MODE_WRITEONCE, "pintool",
              "I", "1000000", "interval");


void counter(ADDRINT addr) {
  inscount[addr][1] += 1;
}


void Instruction(INS ins, void *v) {
  ADDRINT addr = INS_Address(ins);
  if (IN_MAP(addr, inscount)) {
  INS_InsertCall(ins, IPOINT_BEFORE, (AFUNPTR)counter, IARG_ADDRINT, addr, IARG_END);
  }
}


void save_res() {
  ofstream outfile;
  outfile.open (KnobOutputFile.Value().c_str(), ios::out | ios::app);

  oldcounter = icounter;
  outfile << "#" << icounter / 1000000 << "M" << endl;
  for (auto &p : pcs) {
    outfile << "\t0x" << hex << p << dec << ", " << inscount[p][0] << ", " << inscount[p][1] << endl;
  }
  outfile << endl;
}


void accumulator(uint64_t step, uint64_t interval) {
  icounter += step;
  if (icounter - oldcounter > interval) {
    oldcounter = icounter;
    save_res();
    for (auto &p : inscount) {
      p.second[0] += p.second[1];
      p.second[1] = 0;
    }
  }
}


void Trace(TRACE trace, void *v) {
  for (BBL bbl = TRACE_BblHead(trace); BBL_Valid(bbl); bbl = BBL_Next(bbl)) {
    BBL_InsertCall(bbl, IPOINT_BEFORE, (AFUNPTR)accumulator, IARG_UINT64, BBL_NumIns(bbl), IARG_UINT64, atoi(KnobInterval.Value().c_str()), IARG_END);
  }
}


void Fini(INT32 code, void *v) {
  save_res();
}


void load_res() {
  ifstream infile(KnobInputFile.Value().c_str());
  uint64_t tmp;
  while (infile >> hex >> tmp) {
    vector<uint64_t> v(2, 0);
    inscount[tmp] = v;
    pcs.emplace_back(tmp);
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

  load_res();
  cout << "loads loaded\n";

  // Register Instruction to be called to instrument instructions
  INS_AddInstrumentFunction(Instruction, 0);
  TRACE_AddInstrumentFunction(Trace, 0);

  // Register Fini to be called when the application exits
  PIN_AddFiniFunction(Fini, 0);

  // Start the program, never returns
  PIN_StartProgram();

  return 0;
}
