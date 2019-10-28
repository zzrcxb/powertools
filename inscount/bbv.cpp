#include <iostream>
#include <cstdio>
#include <fstream>
#include <unordered_map>
#include <vector>
#include <cstdint>

#include "pin.H"
#include "utils.h"

using namespace std;

typedef uint64_t Addr;
typedef pair<uint64_t, uint64_t> Record;

unordered_map<Addr, uint64_t> BBCounter;
unordered_map<Addr, uint64_t> BBDelta;
unordered_map<Addr, uint64_t> nameTab;

uint64_t BBid = 1;
uint64_t icounter = 0, oldicounter = 0;
uint64_t SKIP, INTERVAL;

vector<vector<Record>> bbv_data;
vector<Record> brp_data;

KNOB<string> KnobOutputBBFile(KNOB_MODE_WRITEONCE, "pintool",
              "bbv", "out.bb", "specify output file name");

KNOB<string> KnobOutputBRFile(KNOB_MODE_WRITEONCE, "pintool",
              "brp", "out.br", "specify breakpoints file name");

KNOB<string> KnobInterval(KNOB_MODE_WRITEONCE, "pintool",
              "i", "50", "interval for each program slice (unit: M instructions)");

KNOB<string> KnobSkip(KNOB_MODE_WRITEONCE, "pintool",
              "s", "0", "skip first <s> instructions");

ofstream bbv_out, br_out;


inline void dump(Addr pc) {
  if (icounter % 1000000000 < 1000000) {
    cerr << "\r" << ZDEBUG << (icounter / 1000000000) << "X1B " << BBCounter.size() << " BBs";
  }
  // ready to dump
  oldicounter = icounter;
  vector<Record> bbv_line;
  for (auto p : BBDelta) {
    auto thepc = p.first;
    auto thedelta = p.second;
    BBCounter[thepc] += thedelta;
    if (thedelta) {
      bbv_line.emplace_back(make_pair(nameTab[thepc], thedelta));
      BBDelta[thepc] = 0;
    }
  }
  bbv_data.emplace_back(bbv_line);
  brp_data.emplace_back(make_pair(pc, BBCounter[pc]));
}


void docount(Addr pc, USIZE size) {
  icounter += size;
  if (IN_MAP(pc, BBDelta)) {
    BBDelta[pc] += 1;
  }
  else {
    cerr << ZERROR << "critical error, exiting..." << endl;
    exit(1);
  }
  if ((icounter - oldicounter) > INTERVAL && icounter > SKIP)
    dump(pc);
}


void BBTrace(TRACE trace, void *v) {
  for (BBL bbl = TRACE_BblHead(trace); BBL_Valid(bbl); bbl = BBL_Next(bbl)) {
    Addr pc = BBL_Address(bbl);
    BBL_InsertCall(bbl, IPOINT_BEFORE, (AFUNPTR)docount, IARG_UINT64, pc, IARG_UINT32, BBL_NumIns(bbl), IARG_END);
    BBCounter.insert(make_pair(pc, 0));
    BBDelta.insert(make_pair(pc, 0));
    nameTab.insert(make_pair(pc, BBid++));
  }
}


INT32 Usage() {
  PIN_ERROR("This Pintool generate BBV for simpoints and generate conditional breakpoints for each slice" +
            KNOB_BASE::StringKnobSummary() +
            "\n"
  );
  return -1;
}

void Fini(INT32 code, void *v) {
  cerr << ZINFO << "Executed " << icounter << " instructions. Dumping results..." << endl;
  cerr << ZINFO << bbv_data.size() << " slices in total" << endl;

  for (auto slice : bbv_data) {
    bbv_out << "T";
    for (auto rec : slice) {
      bbv_out << ":" << rec.first << ":" << rec.second << " ";
    }
    bbv_out << endl;
  }

  for (auto brp : brp_data) {
    br_out << hex << brp.first << " " << dec << brp.second << endl;
  }

  bbv_out.close();
  br_out.close();
}


int main(int argc, char **argv) {
  // initialize pin
  if (PIN_Init(argc, argv))
    return Usage();

  SKIP = atoi(KnobSkip.Value().c_str());
  INTERVAL = atoi(KnobInterval.Value().c_str()) * 1000000;

  bbv_out.open(KnobOutputBBFile.Value().c_str(), ios::out);
  br_out.open(KnobOutputBRFile.Value().c_str(), ios::out);
  if (!bbv_out.is_open() || !br_out.is_open()) {
    cerr << ZERROR << "Faield to open output files" << endl;
    exit(2);
  }

  cerr << ZINFO
       << "skip first: " << SKIP << " insn" << "\t"
       << "interval: " << INTERVAL << " insn" << endl;

  TRACE_AddInstrumentFunction(BBTrace, 0);
  PIN_AddFiniFunction(Fini, nullptr);
  PIN_StartProgram();

  return 0;
}
