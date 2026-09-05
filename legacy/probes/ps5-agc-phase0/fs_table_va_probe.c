/* Phase 0V: test exact FS-table VA availability; no AGC or GPU work. */
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <sys/mman.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0v-fs-table-va.log"
#define FS_TABLE_VA UINT64_C(0xfe0040000)
#define PAGE_SIZE ((size_t)0x4000)

int sceKernelReserveVirtualRange(void **,size_t,int,size_t);
static int log_fd=-1;
static void watchdog(int sig) { (void)sig; _exit(124); }
static void log_line(const char *format,...)
{
    char line[320]; va_list ap; va_start(ap,format);
    int n=vsnprintf(line,sizeof(line),format,ap); va_end(ap);
    if (n<0) return;
    if ((size_t)n>=sizeof(line)-1) n=(int)sizeof(line)-2;
    line[n++]='\n'; (void)write(log_fd,line,(size_t)n); (void)fsync(log_fd);
}
int main(void)
{
    log_fd=open(LOG_PATH,O_CREAT|O_TRUNC|O_WRONLY,0644);
    (void)signal(SIGALRM,watchdog); alarm(8);
    void *requested=(void *)(uintptr_t)FS_TABLE_VA;
    void *reserved=requested;
    int rc=sceKernelReserveVirtualRange(&reserved,PAGE_SIZE,0,PAGE_SIZE);
    int exact=(rc==0 && reserved==requested);
    log_line("phase0V reserve requested=0x%llx size=0x%zx rc=0x%08x exact=%s",
            (unsigned long long)FS_TABLE_VA,PAGE_SIZE,(unsigned)rc,
            exact?"yes":"no");
    (void)fsync(log_fd);
    int unmap_rc=(rc==0 && reserved)?munmap(reserved,PAGE_SIZE):0;
    log_line("phase0V cleanup unmap_rc=0x%08x complete=yes",(unsigned)unmap_rc);
    log_line("phase0V exit result=%d submitted=no",
            (rc==0 && exact && unmap_rc==0)?0:10);
    (void)fsync(log_fd); alarm(0); sleep(2); close(log_fd);
    _exit((rc==0 && exact && unmap_rc==0)?0:10);
}
