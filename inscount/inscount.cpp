/*BEGIN_LEGAL 
Intel Open Source License 

Copyright (c) 2002-2018 Intel Corporation. All rights reserved.
 
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

Redistributions of source code must retain the above copyright notice,
this list of conditions and the following disclaimer.  Redistributions
in binary form must reproduce the above copyright notice, this list of
conditions and the following disclaimer in the documentation and/or
other materials provided with the distribution.  Neither the name of
the Intel Corporation nor the names of its contributors may be used to
endorse or promote products derived from this software without
specific prior written permission.
 
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE INTEL OR
ITS CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
END_LEGAL */
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
