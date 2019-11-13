#ifndef UTILS_H
#define UTILS_H

// #include "pin.H"


#define IN_MAP(KEY, SET) (SET.find(KEY) != SET.end())
#define IN_SET(KEY, SET) (SET.find(KEY) != SET.end())
#define IN_MAPPTR(KEY, SET) (SET->find(KEY) != SET->end())
#define IN_SETPTR(KEY, SET) (SET->find(KEY) != SET->end())

#define BLACK    "\033[30m"
#define RED      "\033[31m"
#define GREEN    "\033[32m"
#define YELLOW   "\033[33m"
#define BLUE     "\033[34m"
#define MAGENTA  "\033[35m"
#define RYAN     "\033[36m"
#define WHITE    "\033[37m"

#define BLACK_B   "\033[30;1m"
#define RED_B     "\033[31;1m"
#define GREEN_B   "\033[32;1m"
#define YELLOW_B  "\033[33;1m"
#define BLUE_B    "\033[34;1m"
#define MAGENTA_B "\033[35;1m"
#define RYAN_B    "\033[36;1m"
#define WHITE_B   "\033[37;1m"

#define RESET    "\033[0m"

#define ZDEBUG "[\033[34mDEBUG\033[0m] "
#define ZINFO  "[\033[32mINFO\033[0m] "
#define ZWARN  "[\033[33mWARN\033[0m] "
#define ZERROR "[\033[31mERROR\033[0m] "

#endif