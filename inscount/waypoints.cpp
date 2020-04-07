#include <iostream>
#include <cstdio>
#include <fstream>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <cstdint>

#include "pin.H"
#include "utils.h"

using namespace std;


typedef uint64_t Addr;
typedef pair<Addr, uint64_t> Record;
typedef unordered_map<Addr, uint64_t> Environment;


unordered_map<Addr, uint64_t> BBDelta;
unordered_map<Addr, uint64_t> BBCount;
unordered_map<Addr, uint64_t> BBSizes;
unordered_map<Addr, uint64_t> nameTab;

unordered_map<Addr, uint64_t> waypoints;

uint64_t BBid = 1;
uint64_t icounter = 0, oldicounter = 0;
uint64_t SKIP, INTERVAL;
bool SKIPPING, STARTED;

// ====== CallStack related =====
#include "CallStack.H"

const string& Target2RtnName(ADDRINT target);
const string& Target2LibName(ADDRINT target);
CallStack callStack(Target2RtnName, Target2LibName);


bool hasEnding (std::string const &fullString, std::string const &ending) {
    if (fullString.length() >= ending.length()) {
        return (0 == fullString.compare (fullString.length() - ending.length(), ending.length(), ending));
    } else {
        return false;
    }
}

const string& Target2RtnName(ADDRINT target) {
  const string & name = RTN_FindNameByAddress(target);

  if (name == "")
      return *new string("[Unknown routine]");
  else
      return *new string(name);
}

const string& Target2LibName(ADDRINT target) {
    PIN_LockClient();

    const RTN rtn = RTN_FindByAddress(target);
    static const string _invalid_rtn("[Unknown image]");

    string name;

    if( RTN_Valid(rtn) ) {
        name = IMG_Name(SEC_Img(RTN_Sec(rtn)));
    } else {
        name = _invalid_rtn;
    }

    PIN_UnlockClient();

    return *new string(name);
}

void A_ProcessDirectCall(ADDRINT ip, ADDRINT target, ADDRINT sp) {
    // cerr << "----------------------" << endl;
    // cerr << "Direct call: " << Target2RtnName(target) << endl;
    // callStack.DumpStack(&cerr);
    callStack.ProcessCall(sp, target);
    // callStack.DumpEnv(&cerr, 0);
}

void A_ProcessIndirectCall(ADDRINT ip, ADDRINT target, ADDRINT sp) {
    // cerr << "----------------------" << endl;
    // cerr << "Indirect call: " << Target2RtnName(target) << endl;
    // callStack.DumpStack(&cerr);
    callStack.ProcessCall(sp, target);
    // callStack.DumpEnv(&cerr, 0);
}

static void A_ProcessStub(ADDRINT ip, ADDRINT target, ADDRINT sp) {
    // cerr << "----------------------" << endl;
    // cerr << "Instrumenting stub: " << Target2RtnName(target) << endl;
    // callStack.DumpStack(&cerr);
    callStack.ProcessCall(sp, target);
    // callStack.DumpEnv(&cerr, 0);
}

static void A_ProcessReturn(ADDRINT ip, ADDRINT sp, ADDRINT pc) {
    // cerr << "----------------------" << endl;
    // cerr << "Return from 0x" << hex << pc << dec << endl;
    // callStack.DumpStack(&cerr);
    callStack.ProcessReturn(sp, false);
    // callStack.DumpEnv(&cerr, 0);
}

static void A_EnterMainImage(ADDRINT ip, ADDRINT target, ADDRINT sp) {
    cerr << ZINFO
         << "Entered main" << endl;
    STARTED = true;
    callStack.ProcessMainEntry(sp, target);
}

static BOOL IsPLT(TRACE trace) {
    RTN rtn = TRACE_Rtn(trace);

    // All .plt thunks have a valid RTN
    if (!RTN_Valid(rtn))
        return FALSE;

    if (".plt" == SEC_Name(RTN_Sec(rtn)))
        return TRUE;
    return FALSE;
}
// ==============================

KNOB<string> KnobOutputBBVFile(KNOB_MODE_WRITEONCE, "pintool",
              "bbv", "out.bb", "specify output file name");

KNOB<string> KnobOutputBRKFile(KNOB_MODE_WRITEONCE, "pintool",
              "brk", "out.brk", "specify breakpoints file name");

KNOB<string> KnobOutputBBIDFile(KNOB_MODE_WRITEONCE, "pintool",
              "bbid", "out.bbid", "specify basicblock id mapping file name");

KNOB<string> KnobRunDir(KNOB_MODE_WRITEONCE, "pintool",
              "r", ".",
              "run directory of the application, this is for saving intermidiate files. PLEASE AVOID conflicts!!!");

KNOB<UINT64> KnobInterval(KNOB_MODE_WRITEONCE, "pintool",
              "i", "50", "interval for each program slice (unit: M instructions)!");

KNOB<UINT64> KnobSkip(KNOB_MODE_WRITEONCE, "pintool",
              "s", "0", "skip first <s> instructions");

ofstream BBVOut, BRKOut, BBIDOut;


void docount(Addr pc, USIZE size);
inline void dump(Addr pc);

bool IsMainExec(ADDRINT target) {
    PIN_LockClient();
    auto rtn = RTN_FindByAddress(target);
    PIN_UnlockClient();
    if (!RTN_Valid(rtn)) return false;
    bool main_exec = IMG_IsMainExecutable(SEC_Img(RTN_Sec(rtn)));
    const string & name = RTN_FindNameByAddress(target);
    if (hasEnding(name, "plt")) {
        main_exec = false;
    }
    return main_exec;
}

bool IsMainExec(RTN rtn) {
    if (!RTN_Valid(rtn)) return false;
    bool main_exec = IMG_IsMainExecutable(SEC_Img(RTN_Sec(rtn)));
    const string & name = RTN_Name(rtn);
    if (hasEnding(name, "plt")) {
        main_exec = false;
    }
    return main_exec;
}

static void I_Trace(TRACE trace, void *v) {
    if (!STARTED) return;

    auto rtn = TRACE_Rtn(trace);
    for(BBL bbl = TRACE_BblHead(trace); BBL_Valid(bbl); bbl = BBL_Next(bbl)) {
        Addr pc = BBL_Address(bbl);
        BBL_InsertCall(bbl, IPOINT_BEFORE, (AFUNPTR)docount, IARG_UINT64, pc, IARG_UINT32, BBL_NumIns(bbl), IARG_END);
        BBDelta.insert(make_pair(pc, 0));
        BBCount.insert(make_pair(pc, 0));
        BBSizes.insert(make_pair(pc, BBL_NumIns(bbl)));
        nameTab.insert(make_pair(pc, BBid++));

        INS tail = BBL_InsTail(bbl);
        // All calls and returns
        if( INS_IsSyscall(tail) ) {
            continue;
        } else {
            if( INS_IsCall(tail) ) {
                if( INS_IsDirectControlFlow(tail) ) {
                    ADDRINT target = INS_DirectControlFlowTargetAddress(tail);
                    // if (IsMainExec(target))
                    INS_InsertPredicatedCall(tail, IPOINT_BEFORE,
                                             (AFUNPTR)A_ProcessDirectCall,
                                             IARG_INST_PTR,
                                             IARG_ADDRINT, target,
                                             IARG_REG_VALUE, REG_STACK_PTR,
                                             IARG_END);
                } else if( !IsPLT(trace) ) {
                    INS_InsertPredicatedCall(tail, IPOINT_BEFORE,
                                             (AFUNPTR)A_ProcessIndirectCall,
                                             IARG_INST_PTR,
                                             IARG_BRANCH_TARGET_ADDR,
                                             IARG_REG_VALUE, REG_STACK_PTR,
                                             IARG_END);
                }
            }
            if( IsPLT(trace) ) {
                INS_InsertCall(tail, IPOINT_BEFORE,
                               (AFUNPTR)A_ProcessStub,
                               IARG_INST_PTR,
                               IARG_BRANCH_TARGET_ADDR,
                               IARG_REG_VALUE, REG_STACK_PTR,
                               IARG_END);
            }
            if( INS_IsRet(tail)) {
                // cerr << "insert";
                INS_InsertPredicatedCall(tail, IPOINT_BEFORE,
                                         (AFUNPTR)A_ProcessReturn,
                                         IARG_INST_PTR,
                                         IARG_REG_VALUE, REG_STACK_PTR,
                                         IARG_ADDRINT, INS_Address(tail),
                                         IARG_END);
            }
        }
    }
}

static void
I_ImageLoad(IMG img, void *v) {
  static bool main_rtn_instrumented = false;

  if( !main_rtn_instrumented ) {
    RTN rtn = RTN_FindByName(img, "main");
    if( rtn == RTN_Invalid() ) {
      rtn = RTN_FindByName(img, "__libc_start_main");
    }
    // Instrument main
    if( rtn != RTN_Invalid() ) {
      main_rtn_instrumented = true;
      RTN_Open(rtn);
      RTN_InsertCall(rtn, IPOINT_BEFORE,
             (AFUNPTR)A_EnterMainImage,
             IARG_INST_PTR,
             IARG_ADDRINT, RTN_Address(rtn),
             IARG_REG_VALUE, REG_STACK_PTR,
             IARG_END);
      RTN_Close(rtn);
    }
  }
}


inline void dump(Addr pc) {
    if (!STARTED) return;
    if (icounter % 1000000000 < 1000000) {
        cerr << "\r" << ZDEBUG
             << (icounter / 1000000000) << "X1B "
             << BBCount.size() << " BBs"
             << "  stack: " << callStack.Depth();
    }
    // dump bbv
    oldicounter = icounter;
    BBVOut << "T";
    for (auto p : BBDelta) {
        auto thePC = p.first;
        auto theDelta = p.second;
        if (theDelta) {
            BBVOut << ":" << nameTab[thePC] << ":" << theDelta * BBSizes[thePC] << " ";
        }
        BBDelta[thePC] = 0;
    }
    BBVOut << endl;

    // dump breakpoints
    callStack.DumpPath(&BRKOut, pc);
}

void docount(Addr pc, USIZE size) {
  if (!STARTED) return;
  icounter += size;
  if (SKIPPING) {
    if (icounter > SKIP) {
      SKIPPING = false; // stop skipping
      oldicounter = icounter;
    }
  }
  else {
    BBDelta[pc] += 1;
    // BBCount[pc] += 1;
    callStack.UpdateBBCnt(pc);
    if ((icounter - oldicounter) > INTERVAL)
      dump(pc);
  }
}

INT32 Usage() {
  PIN_ERROR("This Pintool generate BBV for simpoints and generate conditional breakpoints for each slice" + KNOB_BASE::StringKnobSummary() + "\n");
  return -1;
}

void Fini(INT32 code, void *v) {
    cerr << ZINFO << "Executed " << icounter\
         << " instructions. Dumping results..."
         << endl;

    for (auto p : nameTab) {
        BBIDOut << p.second << " 0x"
                << hex
                << p.first
                << dec << endl;
    }

    BBVOut.close();
    BRKOut.close();
    BBIDOut.close();
}


int main(int argc, char **argv) {
    // initialize pin
    if (PIN_Init(argc, argv))
        return Usage();
    PIN_InitSymbols();

    SKIP = KnobSkip.Value();
    INTERVAL = KnobInterval.Value() * 1000000;
    SKIPPING = SKIP > 0;
    STARTED = false;

    string BBVOutPath  = KnobRunDir.Value() + "/" + KnobOutputBBVFile.Value();
    string BRKOutPath  = KnobRunDir.Value() + "/" + KnobOutputBRKFile.Value();
    string BBIDOutPath = KnobRunDir.Value() + "/" + KnobOutputBBIDFile.Value();

    BBVOut.open(BBVOutPath.c_str(), ios::out);
    BRKOut.open(BRKOutPath.c_str(), ios::out);
    BBIDOut.open(BBIDOutPath.c_str(), ios::out);

    if (!BBVOut.is_open() || !BRKOut.is_open() || !BBIDOut.is_open()) {
        cerr << ZERROR << "Failed to open output files" << endl;
        exit(2);
    }

    cerr << ZINFO
         << "Skip first: " << SKIP << " insn" << "\t"
         << "Interval: " << INTERVAL << " insn" << endl;

    IMG_AddInstrumentFunction(I_ImageLoad, 0);
    TRACE_AddInstrumentFunction(I_Trace, 0);
    PIN_AddFiniFunction(Fini, nullptr);
    PIN_StartProgram();

    return 0;
}


///////////////////////////////////////////////////////////////////////////////
////////// class Activation
///////////////////////////////////////////////////////////////////////////////


VOID
CallStack::CreateActivation(ADDRINT current_sp, ADDRINT target) {
    bool main_exec = IsMainExec(target);

    if (main_exec) {
        envs.back()->func_env[target] += 1;
        envs.push_back(new EnvRecord(target));
    }
    // push activation  -- note this is sp at the callsite
    _activations.push_back(new Activation(_activations.size(), current_sp, target, main_exec));
}

//
// roll back stack if we got here from a longjmp
// Note stack grows down and register stack grows up.
//
VOID
CallStack::AdjustStack(ADDRINT current_sp) {
    _stackGeneration += 1;

    if( _activations.size() == 0 ) return;

    // TIP: I changed this from > to >= ...not sure it's right, but works better
    // Note by Neil: actually, it's NOT right
    while( current_sp > _activations.back()->current_sp() && !_activations.empty()) {
        // debug having hit the assertion below...
        if (_activations.size() == 1) {
            cerr << ZWARN
                 << "AdjustStack(" << current_sp << ") bottomed out" << endl
                 << "    last activation at " << _activations.back()->current_sp() << endl;
        }
        if (_activations.back()->isMainExec()) {
            delete envs.back();
            envs.pop_back();
        }
        delete _activations.back();
        _activations.pop_back();    // pop activation
    }
}

///////////////////////////////////////////////////////////////////////////////
////////// class CallStack
///////////////////////////////////////////////////////////////////////////////

static bool
isOpaqueLib(const string& lib) {
    return 0 && (lib == "/lib/tls/libc.so.6"
      || lib == "/lib/ld-linux.so.2");
}

static bool
isOpaqueRtn(const string& rtn) {
    return 0 && (rtn == "malloc@@GLIBC_2.0"
      || rtn.find("GLIBC") != string::npos);
}

// standard call
VOID
CallStack::ProcessCall(ADDRINT current_sp, ADDRINT target) {
  // check if we got here from a longjmp.
  AdjustStack(current_sp);

  CreateActivation(current_sp, target);
}

// standard call
VOID
CallStack::ProcessMainEntry(ADDRINT current_sp, ADDRINT target) {
  // check if we got here from a longjmp.
  AdjustStack(current_sp);

  _main_entry_depth = _activations.size();
  CreateActivation(current_sp, target);
}

// standard return
VOID
CallStack::ProcessReturn(ADDRINT current_sp, bool prevIpDoesPush) {
    // check if we got here from a longjmp.
    AdjustStack(current_sp);

    if (_activations.size()) {
        if (_activations.back()->isMainExec()) {
            delete envs.back();
            envs.pop_back();
        }
        // pop activation
        delete _activations.back();
        _activations.pop_back();
    }
}

VOID
CallStack::DumpStack(ostream *o) {
    vector<Activation*>::reverse_iterator i;
    int level = _activations.size() - 1;
    string last;
    bool repeated = false;
    bool first = true;
    *o << "activation: " << _activations.size() << endl;
    for(i = _activations.rbegin(); i != _activations.rend(); i++) {
        string cur = _Target2RtnName((*i)->target());
        if( cur != last ) {
            if( !first ) { *o << endl; }
            *o << level << ": " << cur << " (0x" << hex << (*i)->target() << dec << ")\t" << (*i)->isMainExec();
        } else {
            if( !repeated ) {
                *o << "(repeated)";
            }
            repeated = true;
        }
        first = false;
        last = cur;
        level--;
    }
    *o << endl;
}

void CallStack::DumpEnv(ostream *out, Addr pc) {
    *out << endl << "ENV: ------" << endl;
    for (auto i = envs.rbegin(); i != envs.rend(); i++) {
        *out << hex << "0x" << pc << ": " << dec << (*i)->func_env[pc] << endl;
        pc = (*i)->pc;
    }
    *out << endl;
}

void CallStack::DumpPath(ofstream *out, Addr pc) {
    *out << hex << "0x" << pc << ":" << dec << envs.back()->bb_env[pc] << " ";
    bool first = true;
    for (auto i = envs.rbegin(); i != envs.rend(); i++) {
        if (first) {
            *out << hex << "0x" << pc << ":" << dec << (*i)->bb_env[pc] << " ";
            first = false;
        }
        else {
            *out << hex << "0x" << pc << ":" << dec << (*i)->func_env[pc] << " ";
        }
        pc = (*i)->pc;
    }
    *out << endl;
}
