typedef unsigned long usize;

enum {
	SYS_EXIT = 1,
	SYS_WRITE = 4,
	SYS_OPEN = 5,
	SYS_CLOSE = 6,
	SYS_FSYNC = 95,
	SYS_NANOSLEEP = 240,
	SYS_DYNLIB_DLSYM = 591,
	SYS_DYNLIB_LOAD_PRX = 594,
	SYS_DYNLIB_UNLOAD_PRX = 595,
	O_WRONLY = 0x0001,
	O_CREAT = 0x0200,
	O_TRUNC = 0x0400,
	AGC_SYSMODULE_ID = 0x80000094U
};

typedef int (*sysmodule_fn)(unsigned int, ...);

typedef struct {
	long seconds;
	long nanoseconds;
} timespec_t;

/* Keep a real writable PT_LOAD in the fSELF.  The SDK install_app reference
 * has text, rodata and data LOAD segments; an all-const freestanding image was
 * reduced to only two and was rejected before _start on firmware 12.02. */
__attribute__((used)) static volatile unsigned long process_data_anchor =
	0x4147435044415441UL;

static long
raw_syscall(long number, long a1, long a2, long a3, long a4, long a5, long a6) {
	unsigned long result;
	unsigned char error;
	register long r10 __asm__("r10") = a4;
	register long r8 __asm__("r8") = a5;
	register long r9 __asm__("r9") = a6;

	__asm__ __volatile__("syscall"
		: "=a"(result), "=@ccc"(error), "+r"(r10), "+r"(r8), "+r"(r9)
		: "a"(number), "D"(a1), "S"(a2), "d"(a3)
		: "rcx", "r11", "memory");
	return error ? -(long)result : (long)result;
}

static usize
text_length(const char *text) {
	usize length = 0;
	while (text[length] != '\0') {
		length++;
	}
	return length;
}

static void
write_text(int fd, const char *text) {
	(void)raw_syscall(SYS_WRITE, fd, (long)text, (long)text_length(text), 0, 0, 0);
}

static void
write_hex32(int fd, unsigned int value) {
	static const char digits[] = "0123456789abcdef";
	char output[11] = "0x00000000";
	int index;

	for (index = 9; index >= 2; index--) {
		output[index] = digits[value & 15U];
		value >>= 4;
	}
	(void)raw_syscall(SYS_WRITE, fd, (long)output, 10, 0, 0, 0);
}

static void
write_result(int fd, const char *label, int result) {
	write_text(fd, label);
	write_hex32(fd, (unsigned int)result);
	write_text(fd, "\n");
	(void)raw_syscall(SYS_FSYNC, fd, 0, 0, 0, 0, 0);
}

static int
run_probe(void) {
	const char module_path[] = "/system/common/lib/libSceSysmodule.sprx";
	const char log_path[] = "/data/ps5-agc-native-phase0.log";
	int module_handle = -1;
	int fd;
	int result;
	sysmodule_fn load_module = (sysmodule_fn)0;
	sysmodule_fn unload_module = (sysmodule_fn)0;

	fd = (int)raw_syscall(SYS_OPEN, (long)log_path,
		O_WRONLY | O_CREAT | O_TRUNC, 0644, 0, 0, 0);
	if (fd < 0) {
		return 10;
	}
	write_text(fd, "PS5 native AGC phase 0; sysmodule lifecycle only; no submit\n");

	result = (int)raw_syscall(SYS_DYNLIB_LOAD_PRX, (long)module_path, 0,
		(long)&module_handle, 0, 0, 0);
	write_result(fd, "dynlib_load_prx=", result);
	if (result < 0) {
		(void)raw_syscall(SYS_CLOSE, fd, 0, 0, 0, 0, 0);
		return 11;
	}

	result = (int)raw_syscall(SYS_DYNLIB_DLSYM, module_handle,
		(long)"sceSysmoduleLoadModuleInternal", (long)&load_module, 0, 0, 0);
	write_result(fd, "dlsym_load=", result);
	if (result == 0) {
		result = (int)raw_syscall(SYS_DYNLIB_DLSYM, module_handle,
			(long)"sceSysmoduleUnloadModuleInternal", (long)&unload_module, 0, 0, 0);
		write_result(fd, "dlsym_unload=", result);
	}

	if (load_module != (sysmodule_fn)0 && unload_module != (sysmodule_fn)0) {
		result = load_module(AGC_SYSMODULE_ID);
		write_result(fd, "agc_load=", result);
		if (result == 0) {
			result = unload_module(AGC_SYSMODULE_ID);
			write_result(fd, "agc_unload=", result);
		}
	}

	result = (int)raw_syscall(SYS_DYNLIB_UNLOAD_PRX, module_handle, 0, 0, 0, 0, 0);
	write_result(fd, "dynlib_unload_prx=", result);
	(void)raw_syscall(SYS_CLOSE, fd, 0, 0, 0, 0, 0);
	return 0;
}

void
_start(void) {
	int result = run_probe();
	process_data_anchor ^= (unsigned int)result;
	/* Keep the title observable long enough for launch verification. */
	const timespec_t hold = {8, 0};
	(void)raw_syscall(SYS_NANOSLEEP, (long)&hold, 0, 0, 0, 0, 0);
	(void)raw_syscall(SYS_EXIT, result, 0, 0, 0, 0, 0);
	__builtin_trap();
}
