/* Phase 0W: relocate a private FS-table page to the ABI VA, then bootstrap; never submit. */
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0w-fixed-fs-bootstrap.log"
#define DRIVER_ID 0x80000080u
#define DRIVER_NAME "libSceAgcDriver.sprx"
#define AGC_NAME "libSceAgc.sprx"
#define AGC_CONTEXT_BOOTSTRAP_NID "23LRUSvYu1M"
#define FS_TABLE_VA UINT64_C(0xfe0040000)
#define RELOCATED_FS_TABLE_VA UINT64_C(0xff0040000)
#define FS_TABLE_COPY_SIZE ((size_t)0x4000)
#define FS_TABLE_MAPPING_SIZE ((size_t)0x10000)
#define AGC_FS_POINTER_OFFSET UINT64_C(0x45f90)
#define QUEUE_OFFSET UINT64_C(0x228b8)
#define STATE_OFFSET UINT64_C(0x22908)

int sceSysmoduleLoadModuleInternal(unsigned int);
int sceKernelGetModuleList(int *,int,int *);
int sceKernelGetModuleInfo(int,void *);
int sceKernelReserveVirtualRange(void **,size_t,int,size_t);
int sceKernelAllocateMainDirectMemory(size_t,size_t,int,intptr_t *);
int sceKernelMapDirectMemory(void **,size_t,int,int,intptr_t,size_t);

struct segment { void *address; uint32_t size; int32_t prot; };
struct module_info {
    size_t size; char name[256]; struct segment segments[4];
    uint32_t segment_count; uint8_t fingerprint[20];
};
_Static_assert(sizeof(struct module_info)==0x160,"module ABI");
typedef int (*agc_context_bootstrap_fn)(void *,uint32_t);
static int log_fd=-1;

static void log_line(const char *format,...)
{
    char line[512]; va_list ap; va_start(ap,format);
    int n=vsnprintf(line,sizeof(line),format,ap); va_end(ap);
    if (n<0) return;
    if ((size_t)n>=sizeof(line)-1) n=(int)sizeof(line)-2;
    line[n++]='\n';
    if (log_fd>=0) { (void)write(log_fd,line,(size_t)n); (void)fsync(log_fd); }
    (void)write(STDOUT_FILENO,line,(size_t)n);
}
static void watchdog(int sig)
{
    static const char text[]="phase0W watchdog; submitted=no; process resources retained\n";
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
    void *reserved=(void *)(uintptr_t)FS_TABLE_VA;
    void *mapping=reserved;
    intptr_t physical=0;
    log_fd=open(LOG_PATH,O_CREAT|O_TRUNC|O_WRONLY,0644);
    (void)signal(SIGALRM,watchdog); (void)signal(SIGSEGV,watchdog);
    (void)signal(SIGBUS,watchdog); alarm(15);
    log_line("phase0W start; private fixed FS page plus AGC bootstrap v8; no submit or VideoOut");

    int rc=sceKernelReserveVirtualRange(&reserved,FS_TABLE_MAPPING_SIZE,0,FS_TABLE_MAPPING_SIZE);
    log_line("reserve rc=0x%08x exact=%s",(unsigned)rc,
             (!rc && reserved==(void *)(uintptr_t)FS_TABLE_VA)?"yes":"no");
    if (rc || reserved!=(void *)(uintptr_t)FS_TABLE_VA) goto fail10;
    rc=sceKernelAllocateMainDirectMemory(FS_TABLE_MAPPING_SIZE,FS_TABLE_MAPPING_SIZE,0x0c,&physical);
    log_line("allocate rc=0x%08x",(unsigned)rc); if (rc) goto fail11;
    rc=sceKernelMapDirectMemory(&mapping,FS_TABLE_MAPPING_SIZE,0x0f2,0x10,physical,0);
    log_line("map rc=0x%08x exact=%s",(unsigned)rc,
             (!rc && mapping==(void *)(uintptr_t)FS_TABLE_VA)?"yes":"no");
    if (rc || mapping!=(void *)(uintptr_t)FS_TABLE_VA) goto fail12;

    rc=sceSysmoduleLoadModuleInternal(DRIVER_ID);
    log_line("AgcDriver load rc=0x%08x",(unsigned)rc); if (rc) goto fail13;
    void *driver=dlopen(DRIVER_NAME,RTLD_NOW|RTLD_LOCAL);
    uintptr_t driver_base=find_unique_module(DRIVER_NAME);
    if (!driver||!driver_base) goto fail14;
    record_queue("before-bootstrap",driver_base);
    void *agc=dlopen(AGC_NAME,RTLD_NOW|RTLD_LOCAL);
    uintptr_t agc_base=find_unique_module(AGC_NAME);
    log_line("dlopen libSceAgc=%s base_nonzero=%s",agc?"success":"failed",agc_base?"yes":"no");
    if (!agc||!agc_base) goto fail15;

    uintptr_t *fs_pointer=(uintptr_t *)(agc_base+AGC_FS_POINTER_OFFSET);
    uintptr_t original=*fs_pointer;
    log_line("FS pointer before=0x%llx expected_relocated=%s",
             (unsigned long long)original,
             original==RELOCATED_FS_TABLE_VA?"yes":"no");
    if (original!=RELOCATED_FS_TABLE_VA) goto fail16;
    memset(mapping,0,FS_TABLE_MAPPING_SIZE);
    memcpy(mapping,(const void *)original,FS_TABLE_COPY_SIZE);
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    *fs_pointer=(uintptr_t)mapping;
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    log_line("FS page copied and pointer redirected exact=%s",
             *fs_pointer==FS_TABLE_VA?"yes":"no");
    if (*fs_pointer!=FS_TABLE_VA) goto fail17;

    agc_context_bootstrap_fn bootstrap=(agc_context_bootstrap_fn)dlsym(
        agc,AGC_CONTEXT_BOOTSTRAP_NID);
    if (!bootstrap) goto fail18;
    uint32_t context_word=0;
    rc=bootstrap(&context_word,8);
    log_line("context bootstrap rc=0x%08x context_word=0x%08x",
             (unsigned)rc,(unsigned)context_word);
    record_queue("after-bootstrap",driver_base);
    log_line("phase0W exit result=%d submitted=no mapping_lifetime=process",rc?19:0);
    alarm(0); sleep(2); close(log_fd); _exit(rc?19:0);

fail18: log_line("phase0W exit result=18 submitted=no mapping_lifetime=process"); goto done;
fail17: log_line("phase0W exit result=17 submitted=no mapping_lifetime=process"); goto done;
fail16: log_line("phase0W exit result=16 submitted=no mapping_lifetime=process"); goto done;
fail15: log_line("phase0W exit result=15 submitted=no mapping_lifetime=process"); goto done;
fail14: log_line("phase0W exit result=14 submitted=no mapping_lifetime=process"); goto done;
fail13: log_line("phase0W exit result=13 submitted=no mapping_lifetime=process"); goto done;
fail12: log_line("phase0W exit result=12 submitted=no mapping_lifetime=process"); goto done;
fail11: log_line("phase0W exit result=11 submitted=no mapping_lifetime=process"); goto done;
fail10: log_line("phase0W exit result=10 submitted=no mapping_lifetime=process");
done:
    alarm(0); sleep(2); if (log_fd>=0) close(log_fd); _exit(1);
}
