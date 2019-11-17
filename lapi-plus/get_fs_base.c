//gistsnip:start:fsreghack2
#define _GNU_SOURCE
#include <unistd.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <inttypes.h>


void get_fs_base(uint64_t *ret) {
    register int       syscall_no  asm("rax") = 158;
    register int       arg1        asm("rdi") = 0x1003;
    register uint64_t *arg2        asm("rsi") = ret;
    asm("syscall");
}

void _gdb_expr() {
    char buf[BUFSIZ] = {'\0'};
    uint64_t addr = 0;
    get_fs_base(&addr);
    // printf("fs_base = 0x%" PRIx64 "\n", addr);

    // FILE *file = fopen("fs_base.txt", "w");
    // fprintf("0x%" PRIx64 "\n", addr);
    // fclose(file);

    int fd = open("fs_base.dat", O_CREAT | O_WRONLY, 0666);
    write(fd, &addr, BUFSIZ);
    close(fd);
}
//gistsnip:end:fsreghack2
