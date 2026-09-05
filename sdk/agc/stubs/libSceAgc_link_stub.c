/* Host-link facade only. Runtime imports are resolved from libSceAgc. */
#include "ps5_agc.h"

#define UNUSED(x) ((void)(x))

int32_t sceAgcInit(void *s, uint32_t n) { UNUSED(s); UNUSED(n); return -1; }
int32_t sceAgcCreateShader(void **s, void *h, void *c) { UNUSED(s); UNUSED(h); UNUSED(c); return -1; }
int32_t sceAgcLinkShaders(void *cx, void *uc, void *r, void *v, void *p, uint32_t prim) { UNUSED(cx); UNUSED(uc); UNUSED(r); UNUSED(v); UNUSED(p); UNUSED(prim); return -1; }
void *sceAgcGetRegisterDefaults(void) { return 0; }
uint32_t *sceAgcDcbSetCxRegistersIndirect(void *w, const void *r, uint32_t n) { UNUSED(w); UNUSED(r); UNUSED(n); return 0; }
uint32_t *sceAgcDcbSetUcRegistersIndirect(void *w, const void *r, uint32_t n) { UNUSED(w); UNUSED(r); UNUSED(n); return 0; }
uint32_t *sceAgcDcbSetShRegistersIndirect(void *w, const void *r, uint32_t n) { UNUSED(w); UNUSED(r); UNUSED(n); return 0; }
uint32_t *sceAgcCbSetShRegisterRangeDirect(void *w, uint32_t o, const uint32_t *v, uint32_t n) { UNUSED(w); UNUSED(o); UNUSED(v); UNUSED(n); return 0; }
uint32_t *sceAgcDcbDrawIndexAuto(void *w, uint32_t n, uint64_t m) { UNUSED(w); UNUSED(n); UNUSED(m); return 0; }
uint32_t *sceAgcDcbDrawIndex(void *w, uint32_t n, const void *a, uint64_t m) { UNUSED(w); UNUSED(n); UNUSED(a); UNUSED(m); return 0; }
uint32_t *sceAgcDcbSetFlip(void *w, uint32_t h, int32_t b, uint32_t m, int64_t a) { UNUSED(w); UNUSED(h); UNUSED(b); UNUSED(m); UNUSED(a); return 0; }
uint32_t *sceAgcDcbDmaData(void *w, uint32_t a2, uint32_t ds, uint32_t a4, uint64_t d, uint32_t ss, uint32_t a7, uint64_t s, uint32_t n, uint32_t rw, uint32_t dwc, uint32_t sync) { UNUSED(w); UNUSED(a2); UNUSED(ds); UNUSED(a4); UNUSED(d); UNUSED(ss); UNUSED(a7); UNUSED(s); UNUSED(n); UNUSED(rw); UNUSED(dwc); UNUSED(sync); return 0; }
int32_t sceAgcSuspendPoint(void) { return -1; }
