#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#define PORT 6969
#define REQUEST_MAX (2 * 1024 * 1024)
#define REPORT_PATH "/data/ps5-webkit-probe-report.json"

#ifdef __cplusplus
extern "C" {
#endif
int sceUserServiceInitialize(void *);
int sceUserServiceTerminate(void);
int sceSystemServiceLaunchWebBrowser(const char *, void *);
#ifdef __cplusplus
}
#endif

static const char probe_html[] =
#include "probe.html"
;

static void send_all(int fd, const void *buf, size_t len) {
    const char *p = (const char *)buf;
    while (len) {
        ssize_t n = send(fd, p, len, 0);
        if (n <= 0) return;
        p += n;
        len -= (size_t)n;
    }
}

static void respond(int fd, const char *status, const char *type,
                    const void *body, size_t len) {
    char h[512];
    int n = snprintf(h, sizeof(h),
        "HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %zu\r\n"
        "Cache-Control: no-store\r\nAccess-Control-Allow-Origin: *\r\n"
        "Cross-Origin-Opener-Policy: same-origin\r\n"
        "Cross-Origin-Embedder-Policy: require-corp\r\nConnection: close\r\n\r\n",
        status, type, len);
    send_all(fd, h, (size_t)n);
    send_all(fd, body, len);
}

static long content_length(const char *request) {
    const char *p = strcasestr(request, "Content-Length:");
    return p ? strtol(p + 15, NULL, 10) : 0;
}

static char *read_request(int fd, size_t *used_out) {
    char *buf = (char *)calloc(1, REQUEST_MAX + 1);
    if (!buf) return NULL;
    size_t used = 0, target = 0;
    while (used < REQUEST_MAX) {
        ssize_t n = recv(fd, buf + used, REQUEST_MAX - used, 0);
        if (n <= 0) break;
        used += (size_t)n;
        buf[used] = 0;
        char *sep = strstr(buf, "\r\n\r\n");
        if (sep && !target) target = (size_t)(sep + 4 - buf) + (size_t)content_length(buf);
        if (target && used >= target) break;
    }
    *used_out = used;
    return buf;
}

static void handle_client(int fd) {
    size_t used = 0;
    char *req = read_request(fd, &used);
    if (!req) return;

    if (!strncmp(req, "GET / ", 6) || !strncmp(req, "GET /index.html ", 16)) {
        respond(fd, "200 OK", "text/html; charset=utf-8", probe_html, strlen(probe_html));
    } else if (!strncmp(req, "GET /report ", 12)) {
        int f = open(REPORT_PATH, O_RDONLY);
        if (f < 0) {
            const char *none = "{\"status\":\"no report saved yet\"}";
            respond(fd, "404 Not Found", "application/json", none, strlen(none));
        } else {
            struct stat st;
            fstat(f, &st);
            char *data = (char *)malloc((size_t)st.st_size + 1);
            ssize_t n = data ? read(f, data, (size_t)st.st_size) : -1;
            close(f);
            if (n >= 0) respond(fd, "200 OK", "application/json", data, (size_t)n);
            free(data);
        }
    } else if (!strncmp(req, "POST /report ", 13)) {
        char *body = strstr(req, "\r\n\r\n");
        long len = content_length(req);
        if (body && len >= 0 && (size_t)len <= used - (size_t)(body + 4 - req)) {
            body += 4;
            int f = open(REPORT_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
            if (f >= 0) {
                ssize_t n = write(f, body, (size_t)len);
                close(f);
                fprintf(stderr, "[webkit-probe] saved %zd bytes to %s\n", n, REPORT_PATH);
                const char *ok = "{\"saved\":true}";
                respond(fd, "200 OK", "application/json", ok, strlen(ok));
            } else {
                const char *fail = "{\"saved\":false}";
                respond(fd, "500 Internal Server Error", "application/json", fail, strlen(fail));
            }
        }
    } else {
        const char *no = "not found";
        respond(fd, "404 Not Found", "text/plain", no, strlen(no));
    }
    free(req);
}

int main(void) {
    signal(SIGPIPE, SIG_IGN);
    int s = socket(AF_INET, SOCK_STREAM, 0);
    int yes = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons(PORT);
    a.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(s, (struct sockaddr *)&a, sizeof(a)) || listen(s, 8)) {
        fprintf(stderr, "[webkit-probe] server failed: %s\n", strerror(errno));
        return 1;
    }
    fprintf(stderr, "[webkit-probe] listening on :%d\n", PORT);
    sceUserServiceInitialize(NULL);
    sleep(1);
    int rc = sceSystemServiceLaunchWebBrowser("http://127.0.0.1:6969/", NULL);
    fprintf(stderr, "[webkit-probe] browser launch rc=%d\n", rc);
    for (;;) {
        int c = accept(s, NULL, NULL);
        if (c >= 0) { handle_client(c); close(c); }
    }
    sceUserServiceTerminate();
    return 0;
}
