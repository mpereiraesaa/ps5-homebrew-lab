#include <stdio.h>

#include "../../../../third_party/ps5-payload-hbldr/hbldr.h"
#include "payload.inc"

int sceUserServiceInitialize(void *);
int sceUserServiceTerminate(void);

__attribute__((constructor)) static void
constructor(void) {
  if(sceUserServiceInitialize(0)) {
    perror("[hbldr-early-dmem] sceUserServiceInitialize");
  }
}

__attribute__((destructor)) static void
destructor(void) {
  sceUserServiceTerminate();
}

int
main(void) {
  puts("[hbldr-early-dmem] breakpoint offset=0x2d; passive payload only");
  return hbldr_launch(-1, embedded_payload, embedded_payload_len);
}
