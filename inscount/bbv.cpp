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
unordered_map<Addr, uint64_t> BBSizes;
unordered_map<Addr, uint64_t> nameTab;

uint64_t BBid = 1;
uint64_t icounter = 0, oldicounter = 0;
uint64_t SKIP, INTERVAL, WARMUP;
bool brp_saved = false;

vector<vector<Record>> bbv_data;
vector<Record> brp_data;

KNOB<string> KnobOutputBBVFile(KNOB_MODE_WRITEONCE, "pintool",
              "bbv", "out.bb", "specify output file name");

KNOB<string> KnobOutputBRKFile(KNOB_MODE_WRITEONCE, "pintool",
              "brk", "out.brk", "specify breakpoints file name");

KNOB<string> KnobOutputBBIDFile(KNOB_MODE_WRITEONCE, "pintool",
              "bbid", "out.bbid", "specify basic block id file name");

KNOB<string> KnobRunDir(KNOB_MODE_WRITEONCE, "pintool",
              "r", ".",
              "run directory of the application, this is for saving intermidiate files. PLEASE AVOID conflicts!!!");

KNOB<UINT64> KnobInterval(KNOB_MODE_WRITEONCE, "pintool",
              "i", "50", "interval for each program slice (unit: M instructions)!");

KNOB<UINT64> KnobWarmup(KNOB_MODE_WRITEONCE, "pintool",
              "w", "1000000", "Use <w> instructions for warmup");

KNOB<UINT64> KnobSkip(KNOB_MODE_WRITEONCE, "pintool",
              "s", "0", "skip first <s> instructions");

ofstream bbv_out, brk_out, bbid_out;


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
    if (thedelta) {
      bbv_line.emplace_back(make_pair(nameTab[thepc], thedelta * BBSizes[thepc]));
    }
    BBDelta[thepc] = 0;
  }
  bbv_data.emplace_back(bbv_line);
  brp_saved = false;
}


void docount(Addr pc, USIZE size) {
  icounter += size;
  BBDelta[pc] += 1;
  BBCounter[pc] += 1;
  if ((icounter - oldicounter) > INTERVAL && icounter > SKIP)
    dump(pc);

  if ((icounter - oldicounter) > INTERVAL - 1000000 && icounter > SKIP && !brp_saved) {
    brp_data.emplace_back(make_pair(pc, BBCounter[pc]));
    brp_saved = true;
  }
}


void BBTrace(TRACE trace, void *v) {
  for (BBL bbl = TRACE_BblHead(trace); BBL_Valid(bbl); bbl = BBL_Next(bbl)) {
    Addr pc = BBL_Address(bbl);
    BBL_InsertCall(bbl, IPOINT_BEFORE, (AFUNPTR)docount, IARG_UINT64, pc, IARG_UINT32, BBL_NumIns(bbl), IARG_END);
    BBCounter.insert(make_pair(pc, 0));
    BBDelta.insert(make_pair(pc, 0));
    BBSizes.insert(make_pair(pc, BBL_NumIns(bbl)));
    nameTab.insert(make_pair(pc, BBid++));
  }
}


INT32 Usage() {
  PIN_ERROR("This Pintool generate BBV for simpoints and generate conditional breakpoints for each slice" + KNOB_BASE::StringKnobSummary() + "\n");
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
    brk_out << hex << brp.first << " " << dec << brp.second << endl;
  }

  for (auto p : nameTab) {
    bbid_out << p.second << " 0x"
             << hex
             << p.first
             << dec
             << " "
             << BBSizes[p.first]
             << endl;
  }

  bbv_out.close();
  brk_out.close();
  bbid_out.close();
}


int main(int argc, char **argv) {
  // initialize pin
  if (PIN_Init(argc, argv))
    return Usage();

  SKIP = KnobSkip.Value();
  INTERVAL = KnobInterval.Value() * 1000000;
  WARMUP = KnobWarmup.Value();

  string bbv_out_path = KnobRunDir.Value() + "/" + KnobOutputBBVFile.Value();
  string brk_out_path = KnobRunDir.Value() + "/" + KnobOutputBRKFile.Value();
  string bbid_out_path = KnobRunDir.Value() + "/" + KnobOutputBBIDFile.Value();

  bbv_out.open(bbv_out_path.c_str(), ios::out);
  brk_out.open(brk_out_path.c_str(), ios::out);
  bbid_out.open(bbid_out_path.c_str(), ios::out);

  if (!bbv_out.is_open() || !brk_out.is_open() || !bbid_out.is_open()) {
    cerr << ZERROR << "Failed to open output files" << endl;
    exit(2);
  }

  cerr << ZINFO
       << "skip first: " << SKIP << " insn" << "\t"
       << "interval: " << INTERVAL << " insn"
       << "warmup: " << WARMUP << endl;

  TRACE_AddInstrumentFunction(BBTrace, nullptr);
  PIN_AddFiniFunction(Fini, nullptr);
  PIN_StartProgram();

  return 0;
}
