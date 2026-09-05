#include <stdio.h>

int sceAppInstUtilInitialize(void);
int sceAppInstUtilTerminate(void);
int sceAppInstUtilAppInstallAll(void);

int
main(void) {
	int result;

	result = sceAppInstUtilInitialize();
	if (result != 0) {
		fprintf(stderr, "appinst initialize=0x%x\n", result);
		fflush(stderr);
		return 10;
	}

	result = sceAppInstUtilAppInstallAll();
	fprintf(stderr, "install %s=0x%x\n", TITLE_ID, result);
	fflush(stderr);
	(void)sceAppInstUtilTerminate();
	return result == 0 ? 0 : 11;
}
