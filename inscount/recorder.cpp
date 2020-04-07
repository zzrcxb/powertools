#include <iostream>
#include <string>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <unordered_map>
#include <map>
#include <vector>
#include <set>
#include <unordered_map>
#include <cstdint>
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>

#include "pin.H"
#include "utils.h"

#define XMM(NUM) REG_XMM##NUM
#define DUMP_REG(NAME) #NAME << ": " << PIN_GetContextReg(ctx, REG_##NAME) << "\n"
#define STRIDE 40960

using namespace std;

typedef uint64_t Addr;
typedef pair<Addr, uint64_t> Brkpt;
typedef pair<Addr, uint64_t> Record;
typedef set<uint64_t> Milestones;

char MEMORY_BUFFER[STRIDE];
unordered_map<Addr, Milestones> Breakpoints;
map<Brkpt, size_t> BrkptID;
unordered_map<Addr, uint64_t> Inscount;

size_t CKPT_CNT = 0, CKPT_GEN = 0;

KNOB<string> KnobInputBRKTFile(KNOB_MODE_WRITEONCE, "pintool",
              "b", "break.txt", "specify input file name");

KNOB<string> KnobRunDir(KNOB_MODE_WRITEONCE, "pintool",
              "r", ".",
              "run directory of the application, this is for saving intermidiate files. PLEASE AVOID conflicts!!!");

KNOB<string> KnobCkptDir(KNOB_MODE_WRITEONCE, "pintool",
              "c", ".",
              "Root of the checkpoint dir");


void dumpIntRegs(CONTEXT* ctx, ofstream &out);
void dumpFloatRegs(CONTEXT* ctx, ofstream &out);
void dumpMiscRegs(CONTEXT* ctx, ofstream &out);
void dumpPC(CONTEXT* ctx, ofstream &out);
void dumpMemory();
void loadMapping(string pmem_path, string mmap);
void createCheckpoint(CONTEXT *ctx, size_t brkptID, ADDRINT pc, ADDRINT npc);


void docount(CONTEXT *ctx, ADDRINT pc, ADDRINT npc) {
    Inscount[pc]++;
    if (IN_SET(Inscount[pc], Breakpoints[pc])) {
        Breakpoints[pc].erase(Inscount[pc]);
        createCheckpoint(ctx, BrkptID[Brkpt(pc, Inscount[pc])], pc, npc);
        cerr << ZINFO << "Checkpoint saved" << endl;
        CKPT_GEN++;
        if (CKPT_GEN == CKPT_CNT) exit(0);
    }
}

VOID Instruction(INS ins, VOID *v) {
    ADDRINT addr = INS_Address(ins);
    if (IN_MAP(addr, Breakpoints)) {
        INS_InsertCall(ins, IPOINT_BEFORE, (AFUNPTR)docount, IARG_CONST_CONTEXT,
                       IARG_ADDRINT, addr, IARG_ADDRINT, INS_NextAddress(ins), IARG_END);
    }
}

void loadBreakpoints() {
    string brktFilePath = KnobRunDir.Value() + "/" + KnobInputBRKTFile.Value();
    ifstream infile(brktFilePath.c_str());
    if (infile.is_open()) {
        Addr pc; uint64_t cnt; size_t brkID;
        while (infile >> brkID >> hex >> pc >> dec >> cnt) {
            Inscount.insert(Record(pc, 0));
            BrkptID.insert(make_pair(Brkpt(pc, cnt), brkID));
            Breakpoints[pc].insert(cnt);
        }
        cerr << ZINFO
             << "Loaded " << BrkptID.size() << " breakpoints"
             << endl;
        CKPT_CNT = BrkptID.size();
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
}

INT32 Usage() {
  PIN_ERROR("This Pintool prints the IPs of every instruction executed\n" + KNOB_BASE::StringKnobSummary() + "\n");
  return -1;
}

int main(int argc, char** argv) {
    if (PIN_Init(argc, argv))
        return Usage();

    loadBreakpoints();
    mkdir(KnobCkptDir.Value().c_str(), 0755);
    INS_AddInstrumentFunction(Instruction, 0);
    PIN_AddFiniFunction(Fini, 0);
    PIN_StartProgram();

    return 0;
}


void createCheckpoint(CONTEXT *ctx, size_t brkptID, ADDRINT pc, ADDRINT npc) {
    stringstream ss;
    ss << KnobCkptDir.Value() << "/cpt.None.SIMP-" << brkptID;
    string rootDir = ss.str();
    string pmem = rootDir + "/system.physmem.store0.pmem";
    string mmap = rootDir + "/maps";
    string regs = rootDir + "/m5.cpt.regs";

    cerr << ZINFO << "Creating checkpoint #" << brkptID
         << " in " << rootDir << endl;

    mkdir(rootDir.c_str(), 0755);

    ofstream regsOut(regs.c_str(), ios::out);
    if (regsOut.is_open()) {
        dumpIntRegs(ctx, regsOut);
        dumpFloatRegs(ctx, regsOut);
        dumpMiscRegs(ctx, regsOut);
        regsOut << "PC: " << pc << "\n"
                << "NPC: " << npc << "\n"
                << "SBRK: " << (uint64_t)sbrk(0) << "\n"
                << "SEG_FS_BASE: " << PIN_GetContextReg(ctx, REG_SEG_FS_BASE) << "\n";
    }
    loadMapping(pmem, mmap);
}


void dumpIntRegs(CONTEXT* ctx, ofstream &out) {
    out << DUMP_REG(RAX)
        << DUMP_REG(RCX)
        << DUMP_REG(RDX)
        << DUMP_REG(RBX)
        << DUMP_REG(RSP)
        << DUMP_REG(RBP)
        << DUMP_REG(RSI)
        << DUMP_REG(RDI)
        << DUMP_REG(R8)
        << DUMP_REG(R9)
        << DUMP_REG(R10)
        << DUMP_REG(R11)
        << DUMP_REG(R12)
        << DUMP_REG(R13)
        << DUMP_REG(R14)
        << DUMP_REG(R15);
}


void dumpFloatRegs(CONTEXT* ctx, ofstream &out) {
    uint64_t xmm[2];
    REG XMMs[32] = {
        REG_XMM0, REG_XMM1, REG_XMM2, REG_XMM3, REG_XMM4,
        REG_XMM5, REG_XMM6, REG_XMM7, REG_XMM8, REG_XMM9,
        REG_XMM10, REG_XMM11, REG_XMM12, REG_XMM13, REG_XMM14,
        REG_XMM15, REG_XMM16, REG_XMM17, REG_XMM18, REG_XMM19,
        REG_XMM20, REG_XMM21, REG_XMM22, REG_XMM23, REG_XMM24,
        REG_XMM25, REG_XMM26, REG_XMM27, REG_XMM28, REG_XMM29,
        REG_XMM30, REG_XMM31
    };
    for (auto id = 0; id < 32; id += 1) {
        PIN_GetContextRegval(ctx, XMMs[id], (UINT8*)xmm);
        out << "XMM" << id << "_HIGH: " << xmm[0] << "\n";
        out << "XMM" << id << "_LOW: "  << xmm[1] << "\n";
    }
}


void dumpMiscRegs(CONTEXT* ctx, ofstream &out) {
    out << DUMP_REG(RFLAGS)
        << DUMP_REG(SEG_CS)
        << DUMP_REG(SEG_SS)
        << DUMP_REG(SEG_DS)
        << DUMP_REG(SEG_ES)
        << DUMP_REG(SEG_FS)
        << DUMP_REG(SEG_GS)
        << DUMP_REG(MXCSR)
        << DUMP_REG(FPTAG)
        << DUMP_REG(FPOPCODE);
}


void dumpPC(CONTEXT* ctx, ofstream &out) {
}


void loadMapping(string pmem_path, string mmap) {
    auto pid = getpid();
    stringstream ss;
    ss << pid;
    // string cmd = "python3 /home/neil/powertools/inscount/recorder.py /home/neil/pg map " + ss.str();
    // cerr << cmd << endl;
    // cerr << "ret: " << system(cmd.c_str());
    // cerr << system("ls > 1.out");

    string map_path = "/proc/" + ss.str() + "/maps";
    ifstream infile(map_path.c_str());
    ofstream mmapout(mmap.c_str(), ios::out);
    ofstream outfile(pmem_path.c_str(), ios::binary);
    vector<uint64_t*> mappings;
    if (infile.is_open() && mmapout.is_open() && outfile.is_open()) {
        ADDRINT start, end;
        string oneline;
        char addresses[40], path[512];
        while (getline(infile, oneline)) {
            size_t stage = 0;
            size_t addr_cursor = 0, path_cursor = 0, addr_cnt = 0, space_cnt = 0;
            bool in_space = false;
            for (char c : oneline) {
                switch (stage){
                case 0:
                    if ((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) {
                        addresses[addr_cursor++] = c;
                    }
                    else {
                        if (addr_cnt == 0) {
                            addresses[addr_cursor++] = ' ';
                            addr_cnt++;
                        }
                        else {
                            addresses[addr_cursor++] = '\0';
                            stage = 1;
                        }
                    }
                    break;
                case 1:
                    if (in_space) {
                        if (c != ' ' && c != '\n') {
                            if (space_cnt == 4)
                                path[path_cursor++] = c;
                            in_space = false;
                        }
                    }
                    else {
                        if (c == ' ') {
                            in_space = true;
                            space_cnt++;
                        }
                        else if (space_cnt == 4) path[path_cursor++] = c;
                    }
                    break;
                default:
                    break;
                }
            }
            path[path_cursor++] = '\0';
            string name(path);
            istringstream iss(addresses);
            iss >> hex >> start >> end;
            // if (end < 0x7fff00000000 ||
                // name.compare("[heap]") == 0 ||
                // name.compare("[vvar]") == 0 ||
                // name.compare("[vdso]") == 0 ||
                // name.compare("[stack]") == 0
            // ) { // filter to remove pintool segments
                cerr << ZINFO
                     << hex << start << "-"
                     << end << " " << name
                     << dec << endl;
                uint64_t* entry = new uint64_t[2];
                entry[0] = start;
                entry[1] = end;
                mappings.push_back(entry);
                mmapout << hex << start << " "
                        << end << " "
                        << name << endl;
            // }
        }
        mmapout.close();

        for (auto entry : mappings) {
            ADDRINT start = entry[0], end = entry[1];
            while (start < end) {
                ADDRINT size = STRIDE;
                if (start + size > end) size = end - start;
                PIN_SafeCopy(MEMORY_BUFFER, (void*)start, size);
                outfile.write(MEMORY_BUFFER, size);
                start += size;
            }
        }
        outfile.close();

        for (size_t idx = 0; idx < mappings.size(); idx++) {
            delete [] mappings[idx];
        }
    }
}
