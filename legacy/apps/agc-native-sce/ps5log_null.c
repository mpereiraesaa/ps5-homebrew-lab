#include "../../projects/logging_server/client/ps5log.h"

#include <string.h>

void ps5log_config_defaults(ps5log_config *config) {
    if (config) memset(config, 0, sizeof(*config));
}

int ps5log_load_config(const char *const *paths, size_t count,
                       ps5log_config *config, const char **used_path) {
    (void)paths;
    (void)count;
    if (config) ps5log_config_defaults(config);
    if (used_path) *used_path = NULL;
    return 1;
}

int ps5log_init(const ps5log_config *config, const char *title,
                const char *app, uint64_t boot_token) {
    (void)config;
    (void)title;
    (void)app;
    (void)boot_token;
    return 1;
}

int ps5log_line(const char *level, const char *line) {
    (void)level;
    (void)line;
    return -1;
}

void ps5log_close(const char *reason) {
    (void)reason;
}
