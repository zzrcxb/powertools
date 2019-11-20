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
    char buf[BUFSIZ] = {'\0'};
    uint64_t addr = 0;
    addr = (uint64_t)sbrk(0);
    int fd = open("sbrk.dat", O_CREAT | O_WRONLY, 0666);
    write(fd, &addr, BUFSIZ);
}
