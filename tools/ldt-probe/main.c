/*
 * LDT capability probe.
 *
 * Runs the sysarch(I386_SET_LDT, ...) argument matrix and reports each
 * result separately, because a single EINVAL says nothing about whether the
 * operation is unavailable or the arguments were wrong. FreeBSD's amd64
 * amd64_set_ldt() honours LDT_AUTO_ALLOC only for a single descriptor; ask
 * for two in one call and it takes the range-check path, where
 * start=0xffffffff is rejected as EINVAL regardless of kernel policy.
 *
 * Built for elfldr, which runs with more privilege than a title, so a
 * difference between this and the title result localises the restriction to
 * the sandbox rather than the kernel.
 */
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/sysctl.h>
#include <unistd.h>

extern int sysarch(int number, void *args);

#define I386_GET_LDT 0
#define I386_SET_LDT 1
#define LDT_AUTO_ALLOC 0xffffffffu
#define I386_GET_FSBASE 7
#define AMD64_GET_FSBASE 128

/* FreeBSD packs the descriptor pointer at offset 4 on amd64. */
struct ldt_args {
    uint32_t start;
    uint64_t descs __attribute__((packed));
    uint32_t num;
};

_Static_assert(sizeof(struct ldt_args) == 16, "layout");
_Static_assert(offsetof(struct ldt_args, descs) == 4, "packed pointer");

/* Canonical 32-bit ring-3 segments: L clear, D/B set, page granular. */
static uint64_t descriptors[4] = {
    0x00cffb000000ffffull,      /* code, execute/read, accessed */
    0x00cff3000000ffffull,      /* data, read/write, accessed   */
    0x00cffb000000ffffull,
    0x00cff3000000ffffull,
};

static void attempt(const char *label, int op, uint32_t start, uint32_t num,
                    void *descs)
{
    struct ldt_args args;
    int rc;
    int captured;

    memset(&args, 0, sizeof(args));
    args.start = start;
    args.descs = (uint64_t)(uintptr_t)descs;
    args.num = num;
    errno = 0;
    rc = sysarch(op, &args);
    captured = errno;
    printf("  %-34s op=%d start=0x%08x num=%u -> rc=%d errno=%d\n",
           label, op, start, num, rc, rc < 0 ? captured : 0);
}

int main(void)
{
    uint64_t readback[8];
    void *fsbase = NULL;
    long value = -1;
    size_t length = sizeof(value);
    int rc;

    printf("ldt-probe: sysarch LDT capability matrix\n");

    /* Control: does sysarch work at all from here? */
    errno = 0;
    rc = sysarch(AMD64_GET_FSBASE, &fsbase);
    printf("  %-34s op=%d                       -> rc=%d errno=%d fsbase=%p\n",
           "AMD64_GET_FSBASE (control)", AMD64_GET_FSBASE, rc,
           rc < 0 ? errno : 0, fsbase);

    /* Is the policy knob visible, and what is it set to? */
    errno = 0;
    rc = sysctlbyname("machdep.max_ldt_segment", &value, &length, NULL, 0);
    printf("  %-34s -> rc=%d errno=%d value=%ld\n",
           "machdep.max_ldt_segment", rc, rc < 0 ? errno : 0, value);

    /* Reading the LDT tells us whether the op exists before we write. */
    memset(readback, 0, sizeof(readback));
    attempt("I386_GET_LDT num=1", I386_GET_LDT, 0u, 1u, readback);

    /* The call the title made: two descriptors with AUTO_ALLOC. Expected to
     * fail as EINVAL on argument grounds alone. */
    attempt("I386_SET_LDT auto num=2 (as title)", I386_SET_LDT,
            LDT_AUTO_ALLOC, 2u, descriptors);

    /* The correct auto-allocation: one descriptor at a time. */
    attempt("I386_SET_LDT auto num=1 code", I386_SET_LDT,
            LDT_AUTO_ALLOC, 1u, &descriptors[0]);
    attempt("I386_SET_LDT auto num=1 data", I386_SET_LDT,
            LDT_AUTO_ALLOC, 1u, &descriptors[1]);

    /* Explicit indices, which take a different path in the kernel. */
    attempt("I386_SET_LDT start=0 num=1", I386_SET_LDT, 0u, 1u,
            &descriptors[0]);
    attempt("I386_SET_LDT start=0 num=2", I386_SET_LDT, 0u, 2u,
            descriptors);
    attempt("I386_SET_LDT start=1 num=1", I386_SET_LDT, 1u, 1u,
            &descriptors[1]);

    /* And read back whatever stuck. */
    memset(readback, 0, sizeof(readback));
    attempt("I386_GET_LDT num=4 (readback)", I386_GET_LDT, 0u, 4u, readback);
    for (int i = 0; i < 4; ++i)
        printf("  ldt[%d]=0x%016llx\n", i, (unsigned long long)readback[i]);

    printf("ldt-probe: done\n");
    fflush(stdout);
    return 0;
}
