/* Phase 0U: reproduce the native AGC v8 context bootstrap; never submit. */
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0u-context-bootstrap.log"
#define DRIVER_ID 0x80000080u
#define DRIVER_NAME "libSceAgcDriver.sprx"
#define AGC_NAME "libSceAgc.sprx"
#define AGC_CONTEXT_BOOTSTRAP_NID "23LRUSvYu1M"
#define QUEUE_OFFSET UINT64_C(0x228b8)
#define STATE_OFFSET UINT64_C(0x22908)

int sceSysmoduleLoadModuleInternal(unsigned int);
int sceKernelGetModuleList(int *, int, int *);
int sceKernelGetModuleInfo(int, void *);

struct segment { void *address; uint32_t size; int32_t prot; };
struct module_info {
    size_t size; char name[256]; struct segment segments[4];
    uint32_t segment_count; uint8_t fingerprint[20];
};
_Static_assert(sizeof(struct module_info) == 0x160, "module ABI");

typedef int (*agc_context_bootstrap_fn)(void *context, uint32_t version);
static int log_fd = -1;

static void log_line(const char *format, ...)
{
    char line[512]; va_list ap; va_start(ap, format);
    int n=vsnprintf(line,sizeof(line),format,ap); va_end(ap);
    if (n<0) return;
    if ((size_t)n>=sizeof(line)-1) n=(int)sizeof(line)-2;
    line[n++]='\n';
    if (log_fd>=0) { (void)write(log_fd,line,(size_t)n); (void)fsync(log_fd); }
    (void)write(STDOUT_FILENO,line,(size_t)n);
}
static void watchdog(int sig)
{
    static const char text[]="phase0U watchdog; no submit occurred\n";
    (void)sig; if (log_fd>=0) (void)write(log_fd,text,sizeof(text)-1); _exit(124);
}
static uint32_t read32(const void *p) { uint32_t v; memcpy(&v,p,4); return v; }
static uint64_t read64(const void *p) { uint64_t v; memcpy(&v,p,8); return v; }

static uintptr_t find_unique_module(const char *wanted)
{
    int handles[256],count=0,matches=0; uintptr_t base=0;
    if (sceKernelGetModuleList(handles,256,&count)||count<1||count>256) return 0;
    for (int i=0;i<count;++i) {
        struct module_info info; memset(&info,0,sizeof(info)); info.size=sizeof(info);
        if (sceKernelGetModuleInfo(handles[i],&info)) continue;
        info.name[255]='\0';
        if (!strcmp(info.name,wanted)) { ++matches; base=(uintptr_t)info.segments[0].address; }
    }
    return matches==1?base:0;
}
static void record_queue(const char *stage,uintptr_t base)
{
    const uint8_t *q=(const uint8_t *)(base+QUEUE_OFFSET);
    const uint8_t *s=(const uint8_t *)(base+STATE_OFFSET);
    log_line("%s queue size=0x%x index=%u flags_08=0x%x mode_0c=0x%x counter_20=%u counter_28=%u lock=%s sentinel=%u class=%u async=%u registered=%u",
             stage,read32(q),read32(q+4),read32(q+8),read32(q+0xc),
             read32(q+0x20),read32(q+0x28),read64(q+0x38)?"yes":"no",
             q[0x48],read32(s+8),read32(s+0x1c0),read32(s+0x1cc));
}

int main(void)
{
    log_fd=open(LOG_PATH,O_CREAT|O_TRUNC|O_WRONLY,0644);
    (void)signal(SIGALRM,watchdog); alarm(15);
    log_line("phase0U start; AGC context bootstrap v8; no mapping, submit or VideoOut");
    int rc=sceSysmoduleLoadModuleInternal(DRIVER_ID);
    log_line("AgcDriver load rc=0x%08x",(unsigned)rc);
    if (rc) { log_line("phase0U exit result=10 submitted=no"); _exit(10); }
    void *driver=dlopen(DRIVER_NAME,RTLD_NOW|RTLD_LOCAL);
    uintptr_t base=find_unique_module(DRIVER_NAME);
    if (!driver||!base) { log_line("phase0U exit result=11 submitted=no"); _exit(11); }
    record_queue("before-bootstrap",base);
    void *agc=dlopen(AGC_NAME,RTLD_NOW|RTLD_LOCAL);
    log_line("dlopen libSceAgc=%s",agc?"success":"failed");
    if (!agc) { log_line("phase0U exit result=12 submitted=no"); _exit(12); }
    agc_context_bootstrap_fn bootstrap=(agc_context_bootstrap_fn)dlsym(
        agc,AGC_CONTEXT_BOOTSTRAP_NID);
    log_line("resolve context bootstrap=%s",bootstrap?"success":"failed");
    if (!bootstrap) { log_line("phase0U exit result=13 submitted=no"); _exit(13); }
    uint32_t context_word=0;
    rc=bootstrap(&context_word,8);
    log_line("context bootstrap rc=0x%08x context_word=0x%08x",
             (unsigned)rc,(unsigned)context_word);
    record_queue("after-bootstrap",base);
    log_line("phase0U exit result=%d submitted=no",rc?14:0);
    alarm(0);
    /* Keep the identified FAKE host observable long enough for the supervisor. */
    sleep(2);
    if (log_fd>=0) close(log_fd);
    _exit(rc?14:0);
}
