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
#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <map>
#include <set>
#include <sys/time.h>


using namespace std;

map<uint64_t, uint64_t> stop_target_count;
map<uint64_t, uint64_t> stop_count;

uint64_t icounter = 0;
uint64_t start, end;

uint64_t rdtsc(){
    unsigned int lo,hi;
    __asm__ __volatile__ ("rdtsc" : "=a" (lo), "=d" (hi));
    return ((uint64_t)hi << 32) | lo;
}

KNOB<string> KnobInputFile(KNOB_MODE_WRITEONCE, "pintool",
              "i", "load.txt", "specify input file name");

KNOB<string> KnobOutputFile(KNOB_MODE_WRITEONCE, "pintool",
              "o", "cnt.csv", "specify output file name");

ofstream outfile;

void counter(ADDRINT addr) {
  stop_count[addr] += 1;
  if (stop_count[addr] == stop_target_count[addr]) {
    end = rdtsc();
    uint64_t delta_us = end - start;
    outfile << "0x" << hex << addr << ", " << dec << stop_count[addr] << ", " << icounter << ", " << delta_us << " cycles" << endl;
  }
}

void Instruction(INS ins, void *v) {
  ADDRINT addr = INS_Address(ins);
  if (IN_MAP(addr, stop_count)) {
    INS_InsertCall(ins, IPOINT_BEFORE, (AFUNPTR)counter, IARG_ADDRINT, addr, IARG_END);
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
  outfile << "----------" << endl;
  outfile.close();
}


void load() {
  ifstream infile(KnobInputFile.Value().c_str());
  uint64_t pc, cnt;

  while (infile >> hex >> pc >> dec >> cnt) {
    stop_target_count[pc] = cnt;
    stop_count[pc] = 0;
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

  start = rdtsc();
  // Start the program, never returns
  PIN_StartProgram();

  return 0;
}
