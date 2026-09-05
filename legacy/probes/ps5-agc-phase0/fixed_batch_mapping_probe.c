/* Phase 0X: fixed-VA BatchMap lifecycle only; no AGC, queue or submit. */
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0x-fixed-batch-map.log"
#define FIXED_VA UINT64_C(0xfe0040000)
#define REGION_SIZE ((size_t)0x20000)
#define REGION_ALIGN ((size_t)0x10000)

int sceKernelReserveVirtualRange(void **,size_t,int,size_t);
int sceKernelAllocateMainDirectMemory(size_t,size_t,int,int64_t *);
int sceKernelBatchMap(void *,int,int *);
int sceKernelReleaseDirectMemory(int64_t,size_t);

struct batch_entry {
    void *start; int64_t physical; size_t length;
    uint8_t protection; uint8_t memory_type; uint16_t padding;
    uint32_t operation;
};
_Static_assert(sizeof(struct batch_entry)==0x20,"BatchMap entry size");
_Static_assert(__builtin_offsetof(struct batch_entry,protection)==0x18,"protection offset");
_Static_assert(__builtin_offsetof(struct batch_entry,memory_type)==0x19,"type offset");
_Static_assert(__builtin_offsetof(struct batch_entry,operation)==0x1c,"operation offset");
static int log_fd=-1;
static void log_line(const char *format,...)
{
    char line[384]; va_list ap; va_start(ap,format);
    int n=vsnprintf(line,sizeof(line),format,ap); va_end(ap);
    if (n<0) return; if ((size_t)n>=sizeof(line)-1) n=(int)sizeof(line)-2;
    line[n++]='\n'; if (log_fd>=0) { (void)write(log_fd,line,(size_t)n); (void)fsync(log_fd); }
}
static void park(const char *reason)
{
    log_line("PARKED_PHASE0X reason=%s; no AGC or submit; retain mapping state",reason);
    alarm(0); for (;;) (void)pause();
}
static void watchdog(int sig) { (void)sig; park("watchdog"); }

int main(void)
{
    void *va=(void *)(uintptr_t)FIXED_VA; int64_t physical=0;
    int reserved=0,allocated=0,mapped=0,result=10,processed=-1;
    log_fd=open(LOG_PATH,O_CREAT|O_TRUNC|O_WRONLY,0644);
    (void)signal(SIGALRM,watchdog); (void)signal(SIGSEGV,watchdog);
    (void)signal(SIGBUS,watchdog); alarm(10);
    log_line("phase0X start; exact fixed VA plus BatchMap 0xf2/0x0c; no AGC or submit");
    int rc=sceKernelReserveVirtualRange(&va,REGION_SIZE,0,REGION_ALIGN);
    log_line("reserve rc=0x%08x exact=%s",(unsigned)rc,
             (!rc && va==(void *)(uintptr_t)FIXED_VA)?"yes":"no");
    if (rc||va!=(void *)(uintptr_t)FIXED_VA) goto cleanup;
    reserved=1;
    rc=sceKernelAllocateMainDirectMemory(REGION_SIZE,REGION_ALIGN,0x0c,&physical);
    log_line("allocate rc=0x%08x",(unsigned)rc); if (rc) goto cleanup;
    allocated=1;
    struct batch_entry entry={va,physical,REGION_SIZE,0xf2,0x0c,0,0};
    rc=sceKernelBatchMap(&entry,1,&processed);
    log_line("batch map rc=0x%08x processed=%d",(unsigned)rc,processed);
    if (rc||processed!=1) { if (processed!=0) park("ambiguous map result"); goto cleanup; }
    mapped=1;
    volatile uint64_t *first=(volatile uint64_t *)va;
    volatile uint64_t *last=(volatile uint64_t *)((uint8_t *)va+REGION_SIZE-8);
    *first=UINT64_C(0x0123456789abcdef); *last=UINT64_C(0xfedcba9876543210);
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    int canaries=*first==UINT64_C(0x0123456789abcdef) &&
                  *last==UINT64_C(0xfedcba9876543210);
    log_line("cpu_canaries=%s",canaries?"yes":"no"); result=canaries?0:20;
cleanup:
    if (mapped) {
        struct batch_entry entry={va,0,REGION_SIZE,0xf2,0x0c,0,1}; processed=-1;
        rc=sceKernelBatchMap(&entry,1,&processed);
        log_line("batch unmap rc=0x%08x processed=%d",(unsigned)rc,processed);
        if (rc||processed!=1) park("ambiguous unmap result");
    }
    int release_rc=allocated?sceKernelReleaseDirectMemory(physical,REGION_SIZE):0;
    int unmap_rc=reserved?munmap(va,REGION_SIZE):0;
    log_line("cleanup release_rc=0x%08x unmap_rc=0x%08x complete=%s",
             (unsigned)release_rc,(unsigned)unmap_rc,
             (!release_rc&&!unmap_rc)?"yes":"no");
    if (release_rc||unmap_rc) park("cleanup failed");
    log_line("phase0X exit result=%d submitted=no",result);
    alarm(0); sleep(2); close(log_fd); return result;
}
