/*
 * Low-address mapping probe, second pass.
 *
 * The first pass established that the low 4 GiB is nearly empty and that a
 * plain mmap hint is honoured there. Two questions were left open, and both
 * matter before anything relies on this:
 *
 *   1. Is MAP_EXCL honoured? A MAP_FIXED request that overlapped this
 *      payload's own image reported success, which it must not have if
 *      MAP_EXCL worked. If the flag is ignored, MAP_FIXED silently replaces
 *      live mappings and is unusable inside a real process. Tested safely
 *      here by requesting the same free address twice without unmapping.
 *   2. How large a contiguous low region can be obtained? A 32-bit guest
 *      wants as much of the low 4 GiB as it can get.
 */
#include <sys/types.h>

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define FOUR_GIB 0x100000000ull
#define MIB (1024ull * 1024ull)

static void *map_at(uint64_t hint, size_t size, int flags)
{
    return mmap((void *)(uintptr_t)hint, size, PROT_READ | PROT_WRITE,
                MAP_PRIVATE | MAP_ANON | flags, -1, 0);
}

/* Is MAP_EXCL honoured? Ask twice for the same free address. */
static void test_map_excl(void)
{
    const uint64_t hint = 0x30000000ull;
    const size_t size = 64u * 1024u;
    void *first;
    void *second;

    printf("MAP_EXCL honoured?\n");
    first = map_at(hint, size, MAP_FIXED | MAP_EXCL);
    if (first == MAP_FAILED) {
        printf("  first  fixed+excl at 0x%llx -> FAILED errno=%d\n",
               (unsigned long long)hint, errno);
        return;
    }
    printf("  first  fixed+excl at 0x%llx -> 0x%011llx\n",
           (unsigned long long)hint, (unsigned long long)(uintptr_t)first);

    errno = 0;
    second = map_at(hint, size, MAP_FIXED | MAP_EXCL);
    if (second == MAP_FAILED) {
        printf("  second fixed+excl same addr -> FAILED errno=%d"
               "  => MAP_EXCL IS honoured, MAP_FIXED is safe to use\n", errno);
    } else {
        printf("  second fixed+excl same addr -> 0x%011llx"
               "  => MAP_EXCL IGNORED; MAP_FIXED would clobber\n",
               (unsigned long long)(uintptr_t)second);
        (void)munmap(second, size);
    }
    (void)munmap(first, size);

    /* And whether a plain MAP_FIXED over our own live mapping replaces it. */
    first = map_at(hint, size, MAP_FIXED | MAP_EXCL);
    if (first != MAP_FAILED) {
        volatile uint32_t *word = first;

        *word = 0xdeadbeefu;
        second = map_at(hint, size, MAP_FIXED);
        printf("  plain fixed over live mapping -> %s, value now 0x%08x\n",
               second == MAP_FAILED ? "FAILED" : "replaced",
               second == MAP_FAILED ? *word : *(volatile uint32_t *)second);
        (void)munmap(first, size);
    }
}

/* How much contiguous low memory can be had? */
static void test_low_capacity(void)
{
    static const size_t sizes[] = {
        16u * MIB, 64u * MIB, 256u * MIB, 512u * MIB,
        1024u * MIB, 1536u * MIB, 2048u * MIB, 3072u * MIB,
    };

    printf("largest contiguous low mapping (hint 0x%x):\n", 0x10000000u);
    for (unsigned i = 0; i < sizeof(sizes) / sizeof(sizes[0]); ++i) {
        void *got = map_at(0x10000000ull, sizes[i], 0);
        const int captured = errno;

        if (got == MAP_FAILED) {
            printf("  %6llu MiB -> FAILED errno=%d\n",
                   (unsigned long long)(sizes[i] / MIB), captured);
            continue;
        }
        printf("  %6llu MiB -> 0x%011llx %s\n",
               (unsigned long long)(sizes[i] / MIB),
               (unsigned long long)(uintptr_t)got,
               (uintptr_t)got + sizes[i] <= FOUR_GIB ? "entirely below 4 GiB"
                                                     : "crosses/above 4 GiB");
        (void)munmap(got, sizes[i]);
    }
}

/* A low mapping has to be usable, and code pages must be executable. */
static void test_low_usable(void)
{
    const uint64_t hint = 0x20000000ull;
    const size_t size = 1u * MIB;
    void *got = map_at(hint, size, 0);
    volatile uint32_t *words;
    int rc;

    printf("low mapping usable?\n");
    if (got == MAP_FAILED || (uintptr_t)got >= FOUR_GIB) {
        printf("  no low mapping obtained (errno=%d)\n", errno);
        return;
    }
    words = got;
    words[0] = 0xa5a5a5a5u;
    words[(size / 4u) - 1u] = 0x5a5a5a5au;
    printf("  base=0x%011llx write/read %s\n",
           (unsigned long long)(uintptr_t)got,
           (words[0] == 0xa5a5a5a5u &&
            words[(size / 4u) - 1u] == 0x5a5a5a5au) ? "ok" : "MISMATCH");
    errno = 0;
    rc = mprotect(got, size, PROT_READ | PROT_EXEC);
    printf("  mprotect r-x rc=%d errno=%d\n", rc, rc ? errno : 0);
    errno = 0;
    rc = mprotect(got, size, PROT_READ | PROT_WRITE | PROT_EXEC);
    printf("  mprotect rwx rc=%d errno=%d\n", rc, rc ? errno : 0);
    (void)munmap(got, size);
}

int main(void)
{
    printf("lowmem-probe v2\npage size = %ld\n", sysconf(_SC_PAGESIZE));
    test_map_excl();
    test_low_capacity();
    test_low_usable();
    printf("lowmem-probe: done\n");
    fflush(stdout);
    return 0;
}
