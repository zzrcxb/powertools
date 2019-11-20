#define _GNU_SOURCE
#include <unistd.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <inttypes.h>

void _gdb_expr() {
    uint64_t addr = 0;
    addr = (uint64_t)sbrk(0);
    FILE* fd = fopen("sbrk.dat", "w+");
    printf("brk_val = 0x%" PRIx64 "\n", addr);
    fprintf(fd, "0x%" PRIx64 "\n", addr);
    fclose(fd);
}
