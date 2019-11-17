#include <iostream>
#include <cstdio>
#include <fstream>
#include <set>
#include <unordered_map>
#include <memory>
#include <vector>
#include <deque>
#include <cstdint>

#include "pin.H"
#include "utils.h"

using namespace std;

typedef uint64_t Addr;
typedef pair<Addr, uint64_t> Record;
typedef unordered_map<Addr, uint64_t> Counter;
typedef Counter *CounterPtr;
typedef pair<Addr, CounterPtr> StackFrame;

static uint64_t BBid = 1;
static uint64_t icounter = 0, oldicounter = 0;
static uint64_t SKIP, INTERVAL;


KNOB<string> KnobOutputBBVFile(KNOB_MODE_WRITEONCE, "pintool",
              "bbv", "out.bb", "specify output file name");

KNOB<string> KnobOutputBRKFile(KNOB_MODE_WRITEONCE, "pintool",
              "brk", "out.sbrk", "specify breakpoints file name"); // breakpoints info based on call stack

KNOB<string> KnobInputWLFile(KNOB_MODE_WRITEONCE, "pintool",
              "white", "white.list", "specify output file name");

KNOB<string> KnobRunDir(KNOB_MODE_WRITEONCE, "pintool",
              "r", ".",
              "run directory of the application, this is for saving intermidiate files. PLEASE AVOID conflicts!!!");

KNOB<UINT64> KnobInterval(KNOB_MODE_WRITEONCE, "pintool",
              "i", "50", "interval for each program slice (unit: M instructions)!");

KNOB<UINT64> KnobSkip(KNOB_MODE_WRITEONCE, "pintool",
              "s", "0", "skip first <s> instructions");


class CallS {
private:
  vector<StackFrame*> cs;

  uint64_t get_count(Addr pc, size_t frame_id) {
    auto *sf = cs[frame_id];
    if (IN_MAPPTR(pc, sf->second)) {
      return (*sf->second)[pc];
    }
    else {
      cerr << ZERROR << "fatal error: "
           << "record 0x" << hex << pc
           << " doesn't exist in current stackframe 0x"
           << cur_frame()->first << dec
           << ". size=" << sf->second->size()
           << endl << flush;
      for (auto p : *sf->second) {
        cerr << hex << "0x" << p.first << ": " << dec << p.second << endl;
      }
      exit(2);
    }
  }

public:
  CallS() {
    auto *sf = new StackFrame(0x0, new Counter());
    cs.push_back(sf);
  }

  StackFrame* cur_frame() { return cs.back(); }

  void inc_count(Addr pc) {
    auto counter = cur_frame()->second;
    if (IN_MAPPTR(pc, counter)) {
      (*counter)[pc] += 1;
    }
    else {
      counter->insert(Record(pc, 1));
    }
  }

  void on_call(Addr pc) {
    inc_count(pc);
    auto *sf = new StackFrame(pc, new Counter());
    cs.push_back(sf);
  }

  void on_ret(Addr pc) {
    delete cs.back()->second;
    delete cs.back();
    cs.pop_back();
  }

  size_t size() {
    return cs.size();
  }

  void dump() {
    for (auto *frame : cs) {
      cerr << "================" << endl
           << "Func: 0x" << hex << frame->first << dec << endl;
      for (auto rec : *frame->second) {
        cerr << "\t" << hex << rec.first << ": "
             << dec << rec.second << endl;
      }
      cerr << endl;
    }
  }

  deque<Record> get_records(Addr pc) {
    deque<Record> results;
    // start from the top of the call stack
    auto cur_addr = pc;
    for (size_t index = cs.size(); index > 0; index--) {
      results.push_front(Record(cur_addr, get_count(cur_addr, index - 1)));
      cur_addr = cs[index - 1]->first;
    }
    return results;
  }
};


ofstream bbv_out, brk_out;
Counter BBCounter, BBDelta, nameTab;
vector<vector<Record>> bbv_data;
vector<deque<Record>> brp_data;
CallS CALLSTACK;
set<Addr> WHITELIST;


void dump(Addr pc);
void docount(Addr pc, USIZE size);

void dump(Addr pc) {
  if (icounter % 1000000000 < 1000000) {
    cerr << "\r" << ZDEBUG << (icounter / 1000000000) << "X1B " << BBCounter.size() << " BBs";
  }

  // ready to dump
  oldicounter = icounter;
  vector<Record> bbv_line;
  for (auto p : BBDelta) {
    auto thepc = p.first;
    auto thedelta = p.second;
    bbv_line.emplace_back(make_pair(nameTab[thepc], thedelta));
    BBDelta[thepc] = 0;
  }
  bbv_data.emplace_back(bbv_line);
  brp_data.emplace_back(CALLSTACK.get_records(pc));
}

void docount(Addr pc, USIZE size) {
  icounter += size;
  BBDelta[pc] += 1;
  CALLSTACK.inc_count(pc);
  if ((icounter - oldicounter) > INTERVAL && icounter > SKIP)
    dump(pc);
}

void before_call(Addr pc, char* name) {
  cerr << "entering " << name << ":0x" << hex << pc << dec << ". size: " << CALLSTACK.size() << endl;
  CALLSTACK.on_call(pc);
}

void after_call(Addr pc, char* name) {
  cerr << "returning " << name  << ":0x" << hex << pc << dec << ". size: " << CALLSTACK.size() << endl;
  CALLSTACK.on_ret(pc);
}

void BBTrace(TRACE trace, void *v) {
  for (BBL bbl = TRACE_BblHead(trace); BBL_Valid(bbl); bbl = BBL_Next(bbl)) {
    Addr pc = BBL_Address(bbl);
    BBDelta.insert(make_pair(pc, 0));
    nameTab.insert(make_pair(pc, BBid++));
    BBL_InsertCall(bbl, IPOINT_BEFORE, (AFUNPTR)docount, IARG_UINT64, pc, IARG_UINT32, BBL_NumIns(bbl), IARG_END);
  }
}

void Routine(RTN rtn, void *v) {
  auto pc = RTN_Address(rtn);
  const char* name = RTN_Name(rtn).c_str();
  if (!IN_SET(pc, WHITELIST) || name[0] == '.' || !RTN_Valid(rtn))
    return;

  RTN_Open(rtn);
  RTN_InsertCall(rtn, IPOINT_BEFORE, (AFUNPTR)before_call, IARG_ADDRINT, pc, IARG_PTR, name, IARG_END);
  RTN_InsertCall(rtn, IPOINT_AFTER, (AFUNPTR)after_call, IARG_ADDRINT, pc, IARG_PTR, name, IARG_END);
  RTN_Close(rtn);
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
    bbv_out << endl << flush;
  }

  for (auto brp : brp_data) {
    for (auto rec : brp) {
      brk_out << hex << rec.first << ":" << dec << rec.second << " ";
    }
    brk_out << endl << flush;
  }

  bbv_out.close();
  brk_out.close();
}


void load_whitelist() {
  string inputFilePath = KnobRunDir.Value() + "/" + KnobInputWLFile.Value();
  ifstream infile(inputFilePath.c_str());
  if (infile.is_open()) {
    Addr pc;
    while (infile >> hex >> pc) {
      WHITELIST.insert(pc);
    }
    cerr << ZINFO << "whitelist loaded: " << WHITELIST.size() << endl;
  }
  else {
    cerr << ZERROR
         << "Failed to open whitelist file at " << inputFilePath
         << ". Exiting..."
         << endl << flush;
  }
}


int main(int argc, char **argv) {
  PIN_InitSymbols();

  // initialize pin
  if (PIN_Init(argc, argv))
    return Usage();

  load_whitelist();

  SKIP = KnobSkip.Value();
  INTERVAL = KnobInterval.Value() * 1000000;

  string bbv_out_path = KnobRunDir.Value() + "/" + KnobOutputBBVFile.Value();
  string brk_out_path = KnobRunDir.Value() + "/" + KnobOutputBRKFile.Value();
  bbv_out.open(bbv_out_path.c_str(), ios::out);
  brk_out.open(brk_out_path.c_str(), ios::out);
  if (!bbv_out.is_open() || !brk_out.is_open()) {
    cerr << ZERROR << "Failed to open output files" << endl;
    exit(2);
  }
  cerr << ZINFO
       << "skip first: " << SKIP << " insn" << "\t"
       << "interval: " << INTERVAL << " insn" << endl;

  RTN_AddInstrumentFunction(Routine, nullptr);
  TRACE_AddInstrumentFunction(BBTrace, nullptr);
  PIN_AddFiniFunction(Fini, nullptr);
  PIN_StartProgram();

  return 0;
}
