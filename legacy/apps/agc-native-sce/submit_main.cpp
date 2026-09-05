#include <cstddef>
#include <cstdint>
#include <signal.h>
#include <time.h>
#include <unistd.h>

/* Native GPU-visibility gate v2. It submits exactly DMA_DATA(4 bytes) plus
 * RELEASE_MEM(ownership fence), with command, target and fence in one retained
 * Main Direct Memory BatchMap matching the observed AGC command-pool policy.
 * Any ambiguous post-submit state parks without cleanup. */
extern "C" {
int open(const char*,int,...); long write(int,const void*,std::size_t); int fsync(int); int close(int);
void *memset(void*,int,std::size_t);
int sceKernelReserveVirtualRange(void**,std::size_t,int,std::size_t);
int sceKernelAllocateMainDirectMemory(std::size_t,std::size_t,int,std::int64_t*);
int sceKernelBatchMap(void*,int,int*);
int sceKernelMunmap(void*,std::size_t);
int sceKernelReleaseDirectMemory(std::int64_t,std::size_t);
int sceSysmoduleLoadModuleInternal(unsigned,...); int sceSysmoduleUnloadModuleInternal(unsigned,...);
std::int32_t sceAgcDriverSubmitDcb(void*);
std::int32_t sceAgcInit(void*,std::uint32_t);
}

namespace {
constexpr int W=1,C=0x200,T=0x400; constexpr unsigned AGC=0x80000094U;
constexpr std::size_t ARENA=0x20000,ALIGN=0x10000,TARGET=0x1000,FENCE=0x1100;
constexpr char LOG[]="/download0/agc-native-sce-phase0.log";
int fd=-1; volatile sig_atomic_t submitted=0;
std::size_t len(const char*s){std::size_t n=0;while(s[n])++n;return n;}
void text(const char*s){if(fd>=0){write(fd,s,len(s));fsync(fd);}}
void hex(const char*l,int r){static constexpr char x[]="0123456789abcdef";char b[11]="0x00000000";auto v=std::uint32_t(r);for(int i=9;i>=2;i--){b[i]=x[v&15];v>>=4;}text(l);if(fd>=0)write(fd,b,10);text("\n");}
[[noreturn]]void park(const char*why){text("PARKED_NATIVE_LABEL reason=");text(why);text("; retain process, driver and direct mapping; DO_NOT_CLOSE_PPSA99998\n");alarm(0);for(;;)pause();}
void watchdog(int){if(submitted)park("watchdog after submit");text("watchdog before submit; safe failure\n");_exit(124);}
std::uint64_t now(){timespec t{};clock_gettime(CLOCK_MONOTONIC,&t);return std::uint64_t(t.tv_sec)*1000000000ULL+std::uint64_t(t.tv_nsec);}
void flush_gpu_data(const void*address,std::size_t bytes){auto at=static_cast<const std::uint8_t*>(address),end=at+bytes;for(;at<end;at+=64)__asm__ volatile("clflush (%0)"::"r"(at):"memory");__asm__ volatile("mfence":::"memory");}
struct Submit { const std::uint32_t *words; std::uint32_t count; std::uint8_t flag; std::uint8_t pad[3]; };
struct BatchEntry { void *address; std::int64_t physical; std::size_t length; std::uint8_t protection; std::uint8_t memory_type; std::uint16_t reserved; std::uint32_t operation; };
static_assert(sizeof(Submit)==0x10);
static_assert(sizeof(BatchEntry)==0x20);
static_assert(offsetof(BatchEntry,protection)==0x18);
static_assert(offsetof(BatchEntry,memory_type)==0x19);
static_assert(offsetof(BatchEntry,operation)==0x1c);
}

int main(){
 fd=open(LOG,W|C|T,0644);if(fd<0)for(;;)pause();signal(SIGALRM,watchdog);signal(SIGSEGV,watchdog);signal(SIGBUS,watchdog);alarm(12);
 text("AGC native label v5; separate target/fence cache lines; sceAgcInit state_bytes=8; pre-submit clflush64+mfence; BatchMap protection=f2 memory_type=0c; DMA_DATA bytes=4; RELEASE_MEM ownership fence; no VideoOut, shaders, draw or flip\n");
 std::uint64_t agc_state=0;std::int64_t phys=-1;void*map=nullptr;int load=-1,init=-1,reserve=-1,alloc=-1,mapping=-1,processed=-1,submit_rc=-1,batch_unmap=-1,unmap_processed=-1,unmap=-1,release=-1,unload=-1;
 load=sceSysmoduleLoadModuleInternal(AGC);hex("agc_load=",load);if(load)goto pre_submit_cleanup;
 init=sceAgcInit(&agc_state,sizeof(agc_state));hex("agc_init=",init);if(init)goto pre_submit_cleanup;
 reserve=sceKernelReserveVirtualRange(&map,ARENA,0,ALIGN);hex("virtual_reserve=",reserve);if(reserve||!map)goto pre_submit_cleanup;
 alloc=sceKernelAllocateMainDirectMemory(ARENA,ALIGN,0x0c,&phys);hex("main_direct_allocate=",alloc);if(alloc)goto pre_submit_cleanup;
 { BatchEntry e{map,phys,ARENA,0xf2,0x0c,0,0}; processed=-1;mapping=sceKernelBatchMap(&e,1,&processed);hex("batch_map=",mapping);hex("batch_map_processed=",processed); }
 if(mapping||processed!=1)park("BatchMap result ambiguous or rejected before submit; retain reservation and physical allocation");
 if((reinterpret_cast<std::uintptr_t>(map)&(ALIGN-1))!=0)park("mapping alignment contradiction before submit");
 {
  auto b=static_cast<std::uint8_t*>(map);memset(b,0,ARENA);auto target=reinterpret_cast<volatile std::uint32_t*>(b+TARGET);auto fence=reinterpret_cast<volatile std::uint64_t*>(b+FENCE);auto ta=reinterpret_cast<std::uintptr_t>(target),fa=reinterpret_cast<std::uintptr_t>(fence);
  const std::uint32_t stream[15]={0xc0055000,0xc0300000,0,0,std::uint32_t(ta),std::uint32_t(ta>>32),4,0xc0064900,0x06000528,0x42010000,std::uint32_t(fa),std::uint32_t(fa>>32),0,0,0};
  for(unsigned i=0;i<15;i++)reinterpret_cast<std::uint32_t*>(b)[i]=stream[i];__atomic_store_n(target,0xa5a55a5aU,__ATOMIC_RELEASE);__atomic_store_n(fence,1ULL,__ATOMIC_RELEASE);flush_gpu_data(b,ARENA);
 text("pre_submit_layout=true target_offset=1000 fence_offset=1100 cache_lines_separate=true cache_publication=clflush64+mfence batch_policy=f2/0c target_initial=a5a55a5a fence_initial=1 stream_dwords=15\n");Submit info{reinterpret_cast<const std::uint32_t*>(b),15,0,{0,0,0}};submitted=1;submit_rc=sceAgcDriverSubmitDcb(&info);hex("submit_dcb=",submit_rc);if(submit_rc)park("nonzero submit return is ambiguous");
  auto deadline=now()+2000000000ULL;while(__atomic_load_n(fence,__ATOMIC_ACQUIRE)!=0&&now()<deadline){timespec d{0,1000000};nanosleep(&d,nullptr);}if(__atomic_load_n(fence,__ATOMIC_ACQUIRE)!=0)park("ownership fence timeout");auto observed_target=__atomic_load_n(target,__ATOMIC_ACQUIRE);hex("target_after_fence=",int(observed_target));if(observed_target!=0)park("fence complete but target mismatch");
  submitted=0;text("GPU ownership complete fence=0 target=0\n");memset(b,0,ARENA);text("direct_arena_scrubbed=true\n");
 }
 alarm(0);{BatchEntry e{map,0,ARENA,0xf2,0x0c,0,1};unmap_processed=-1;batch_unmap=sceKernelBatchMap(&e,1,&unmap_processed);hex("batch_unmap=",batch_unmap);hex("batch_unmap_processed=",unmap_processed);}if(batch_unmap||unmap_processed!=1)park("completed submit but BatchMap unmap ambiguous");release=sceKernelReleaseDirectMemory(phys,ARENA);hex("direct_release=",release);if(release)park("completed submit but physical release failed");phys=-1;unmap=sceKernelMunmap(map,ARENA);hex("virtual_release=",unmap);if(unmap)park("completed submit but virtual release failed");map=nullptr;unload=sceSysmoduleUnloadModuleInternal(AGC);hex("agc_unload=",unload);if(unload)park("completed submit but AGC unload failed");text("probe_complete=true\ncleanup complete; parked-safe; close exact title PPSA99998\n");close(fd);for(;;)pause();
pre_submit_cleanup:
 alarm(0);if(phys>=0){release=sceKernelReleaseDirectMemory(phys,ARENA);hex("direct_release=",release);}if(map){unmap=sceKernelMunmap(map,ARENA);hex("virtual_release=",unmap);}if(!load){unload=sceSysmoduleUnloadModuleInternal(AGC);hex("agc_unload=",unload);}text("pre-submit clean failure; parked-safe; close exact title PPSA99998\n");close(fd);for(;;)pause();
}
