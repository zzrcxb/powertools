#include <iostream>
#include <cstdio>
#include <fstream>
#include <unordered_map>
#include <unordered_set>
#include <set>
#include <vector>
#include <cstdint>

#include "pin.H"
#include "utils.h"

using namespace std;

typedef uint64_t Addr;

class Backtrace {
public:
  vector<Addr> trace;
  unordered_map<Addr, uint64_t> trace_cnt;
  unordered_map<Addr, size_t> index_map;

  Addr tailPC;
  uint64_t expected_cnt, tail_cnt = 0;
  size_t bid;
  uint64_t slice_num;
  bool stopped = false;

  Backtrace(vector<Addr>&trace_in, uint64_t expected_cnt, size_t bid, uint64_t slice_num)
    : expected_cnt(expected_cnt), bid(bid), slice_num(slice_num) {
    size_t index = 0;
    for (auto t : trace_in) {
      if (!IN_MAP(t, trace_cnt)) { // for recursive calls
        trace_cnt.insert(make_pair(t, 0));
        index_map.insert(make_pair(t, index++));
        trace.push_back(t);
      }
    }
    cerr << ZDEBUG
         << "trace-in size: " << trace_in.size() << "; "
         << "trace-cnt size: " << trace_cnt.size() << endl;
    tailPC = trace.back();
  }

  void inc(Addr pc) {
    if (stopped || !IN_MAP(pc, index_map))
      return;

    if (pc == tailPC) {
      tail_cnt++;
    }
    trace_cnt[pc]++;
    for (size_t index = index_map[pc] + 1; index < trace.size(); index++) {
      // reset counters
      trace_cnt[trace[index]] = 0;
    }
    if (tail_cnt >= expected_cnt) {
      stopped = true;
      cerr << ZDEBUG
           << "Backtrace #" << bid << "; slice#: " << slice_num
           << " reached expected count. Stopping... "
           << "target PC: 0x" << hex << tailPC
           << ": " << dec << tail_cnt << "; "
           << "expect: " << expected_cnt
           << endl;
      cerr << ZDEBUG << "Full trace: ";
      dump(cerr);
    }
  }

  void dump(ostream &out) {
    out << bid << " " << slice_num;
    for (auto pc : trace) {
      out << " 0x" << hex << pc
          << ":" << dec << trace_cnt[pc];
    }
    out << endl;
  }

  void dump(ofstream &out) {
    out << bid << " " << slice_num;
    for (auto pc : trace) {
      out << " 0x" << hex << pc
          << ":" << dec << trace_cnt[pc];
    }
    out << endl;
  }
};

set<Backtrace*> BTRS;
set<Addr> BB2monitor;
ofstream btc_out;

KNOB<string> KnobOutputBTCFile(KNOB_MODE_WRITEONCE, "pintool",
              "btc", "backtrace.cnt", "specify input file name");

KNOB<string> KnobInputBTFile(KNOB_MODE_WRITEONCE, "pintool",
              "bt", "backtrace.out", "specify input file name");

KNOB<string> KnobRunDir(KNOB_MODE_WRITEONCE, "pintool",
              "r", ".",
              "run directory of the application, this is for saving intermidiate files. PLEASE AVOID conflicts!!!");

void docount(Addr pc) {
  for (auto *bt : BTRS) {
    bt->inc(pc);
  }
}


void BBTrace(TRACE trace, void *v) {
  for (BBL bbl = TRACE_BblHead(trace); BBL_Valid(bbl); bbl = BBL_Next(bbl)) {
    Addr pc = BBL_Address(bbl);

    if (IN_SET(pc, BB2monitor)) {
      BBL_InsertCall(bbl, IPOINT_BEFORE, (AFUNPTR)docount, IARG_ADDRINT, pc, IARG_END);
    }
  }
}


INT32 Usage() {
  PIN_ERROR("This Pintool generates BBV for simpoints and generate conditional breakpoints for each slice" + KNOB_BASE::StringKnobSummary() + "\n");
  return -1;
}


void Fini(INT32 code, void *v) {
  for (auto *bt : BTRS) {
    bt->dump(btc_out);
    delete bt;
  }
  btc_out.close();
}


void loadBT() {
  auto bt_path = KnobRunDir.Value() + "/" + KnobInputBTFile.Value();
  ifstream bt_in(bt_path.c_str());
  string oneline;

  while (getline(bt_in, oneline)) {
    istringstream iss(oneline);
    size_t id;
    uint64_t slice_num;
    iss >> dec >> id >> slice_num;

    Addr target_pc, target_cnt;
    iss >> hex >> target_pc >> dec >> target_cnt;
    if (target_pc == 0) {
      btc_out << id << " "
              << 0  << endl;
    }
    else {
      BB2monitor.insert(target_pc);

      vector<Addr> bt;
      Addr pc;
      while (iss >> hex >> pc) {
        bt.push_back(pc);
        BB2monitor.insert(pc);
      }
      bt.push_back(target_pc);

      cerr << "bt size: " << bt.size() << endl;

      auto bktrs = new Backtrace(bt, target_cnt, id, slice_num);
      BTRS.insert(bktrs);
    }
  }

  cerr << ZDEBUG
       << BTRS.size()
       << " backtrace(s) loaded!"
       << endl;
}


int main(int argc, char **argv) {
  // initialize pin
  if (PIN_Init(argc, argv))
    return Usage();

  string btc_out_path = KnobRunDir.Value() + "/" + KnobOutputBTCFile.Value();

  btc_out.open(btc_out_path.c_str(), ios::out);

  if (!btc_out.is_open()) {
    cerr << ZERROR << "Failed to open output files" << endl;
    exit(2);
  }

  loadBT();

  TRACE_AddInstrumentFunction(BBTrace, nullptr);
  PIN_AddFiniFunction(Fini, nullptr);
  PIN_StartProgram();

  return 0;
}
