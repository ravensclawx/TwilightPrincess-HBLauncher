/*
 * nod-lite: the subset of the nod disc API (nod.h) that Aurora's DVD layer
 * uses, implemented for plain (decompressed) GameCube ISO images.
 *
 * The console build cannot link nod (Rust); the PC converts the user's RVZ to
 * an ISO once (tools/rvz2iso.c) and the Switch reads it over the HBLauncher
 * file server.  GameCube layout (big-endian):
 *   0x000  disc header (game id, title, ...)      boot.bin = 0x000..0x440
 *   0x420  main.dol offset, 0x424 fst offset, 0x428 fst size
 *   0x440  bi2.bin (0x2000)                         0x2440 apploader
 *   fst    12-byte entries: u8 dir, u24 name offset, u32 offset|parent,
 *          u32 length|next; names follow the entries.
 */
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include "nod.h"

enum { KIND_DISC = 1, KIND_PARTITION, KIND_FILE };

struct NodHandle {
    int kind;
    struct NodHandle *disc;        /* partition/file: owning disc */
    /* disc */
    NodDiscStream stream;
    int64_t size;
    uint8_t header[0x440];
    pthread_mutex_t lock;
    /* partition */
    uint8_t *boot, *bi2, *apploader, *dol, *fst;
    size_t apploader_size, dol_size, fst_size;
    uint32_t entries;
    /* file / disc read cursor */
    uint64_t base, length, pos;
};

static const char *g_error = "";

const char *nod_error_message(void) { return g_error; }

static uint32_t be32(const uint8_t *p) {
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}

static int64_t read_at(struct NodHandle *disc, uint64_t offset, void *out, size_t len) {
    int64_t r;
    pthread_mutex_lock(&disc->lock);
    r = disc->stream.read_at(disc->stream.user_data, offset, out, len);
    pthread_mutex_unlock(&disc->lock);
    return r;
}

static uint8_t *read_blob(struct NodHandle *disc, uint64_t offset, size_t size) {
    uint8_t *p = malloc(size ? size : 1);
    if (!p) return NULL;
    if (size && read_at(disc, offset, p, size) != (int64_t)size) { free(p); return NULL; }
    return p;
}

enum NodResult nod_disc_open(const char *path, const struct NodDiscOptions *options, struct NodHandle **out) {
    (void)path; (void)options; (void)out;
    g_error = "nod-lite: open by path is not supported; use nod_disc_open_stream";
    return NOD_RESULT_ERR_OTHER;
}

enum NodResult nod_disc_open_stream(const struct NodDiscStream *stream, const struct NodDiscOptions *options,
                                    struct NodHandle **out) {
    struct NodHandle *h;
    (void)options;
    if (!stream || !out || !stream->read_at || !stream->stream_len) return NOD_RESULT_ERR_INVALID_HANDLE;
    h = calloc(1, sizeof *h);
    if (!h) return NOD_RESULT_ERR_OTHER;
    h->kind = KIND_DISC;
    h->stream = *stream;
    pthread_mutex_init(&h->lock, NULL);
    h->size = stream->stream_len(stream->user_data);
    if (h->size < 0x2440 || read_at(h, 0, h->header, sizeof h->header) != (int64_t)sizeof h->header ||
        be32(h->header + 0x1c) != 0xC2339F3Du) {
        g_error = "nod-lite: not a GameCube ISO (decompress RVZ/WIA/CISO with rvz2iso first)";
        if (h->stream.close) h->stream.close(h->stream.user_data);
        free(h);
        return NOD_RESULT_ERR_FORMAT;
    }
    h->length = (uint64_t)h->size;
    *out = h;
    return NOD_RESULT_OK;
}

static size_t dol_size(const uint8_t *hdr) {
    size_t end = 0x100;
    int i;
    for (i = 0; i < 18; i++) {
        size_t off = be32(hdr + i * 4), len = be32(hdr + 0x90 + i * 4);
        if (off && len && off + len > end) end = off + len;
    }
    return end;
}

enum NodResult nod_disc_open_partition_kind(struct NodHandle *disc, uint32_t kind,
                                            const struct NodPartitionOptions *options,
                                            struct NodHandle **out) {
    struct NodHandle *p;
    uint8_t app[0x20], dolh[0x100];
    uint32_t dol_off, fst_off;
    (void)options;
    if (!disc || disc->kind != KIND_DISC || !out) return NOD_RESULT_ERR_INVALID_HANDLE;
    if (kind != NOD_PARTITION_KIND_DATA) return NOD_RESULT_ERR_NOT_FOUND;
    p = calloc(1, sizeof *p);
    if (!p) return NOD_RESULT_ERR_OTHER;
    p->kind = KIND_PARTITION;
    p->disc = disc;
    dol_off = be32(disc->header + 0x420);
    fst_off = be32(disc->header + 0x424);
    p->fst_size = be32(disc->header + 0x428);
    if (read_at(disc, 0x2440, app, sizeof app) != (int64_t)sizeof app ||
        read_at(disc, dol_off, dolh, sizeof dolh) != (int64_t)sizeof dolh) goto io;
    p->apploader_size = 0x20 + be32(app + 0x14) + be32(app + 0x18);
    p->dol_size = dol_size(dolh);
    p->boot = read_blob(disc, 0, 0x440);
    p->bi2 = read_blob(disc, 0x440, 0x2000);
    p->apploader = read_blob(disc, 0x2440, p->apploader_size);
    p->dol = read_blob(disc, dol_off, p->dol_size);
    p->fst = read_blob(disc, fst_off, p->fst_size);
    if (!p->boot || !p->bi2 || !p->apploader || !p->dol || !p->fst || p->fst_size < 12) goto io;
    p->entries = be32(p->fst + 8);
    if ((uint64_t)p->entries * 12 > p->fst_size) goto io;
    *out = p;
    return NOD_RESULT_OK;
io:
    g_error = "nod-lite: could not read the partition metadata";
    free(p->boot); free(p->bi2); free(p->apploader); free(p->dol); free(p->fst);
    free(p);
    return NOD_RESULT_ERR_IO;
}

enum NodResult nod_disc_open_partition(struct NodHandle *disc, uint32_t index,
                                       const struct NodPartitionOptions *options, struct NodHandle **out) {
    if (index != 0) return NOD_RESULT_ERR_NOT_FOUND;
    return nod_disc_open_partition_kind(disc, NOD_PARTITION_KIND_DATA, options, out);
}

enum NodResult nod_partition_open_file(struct NodHandle *partition, uint32_t index, struct NodHandle **out) {
    struct NodHandle *f;
    const uint8_t *e;
    if (!partition || partition->kind != KIND_PARTITION || !out) return NOD_RESULT_ERR_INVALID_HANDLE;
    if (index == 0 || index >= partition->entries) return NOD_RESULT_ERR_NOT_FOUND;
    e = partition->fst + (size_t)index * 12;
    if (e[0] & 1) return NOD_RESULT_ERR_NOT_FOUND;               /* a directory */
    f = calloc(1, sizeof *f);
    if (!f) return NOD_RESULT_ERR_OTHER;
    f->kind = KIND_FILE;
    f->disc = partition->disc;
    f->base = be32(e + 4);
    f->length = be32(e + 8);
    *out = f;
    return NOD_RESULT_OK;
}

void nod_free(struct NodHandle *h) {
    if (!h) return;
    if (h->kind == KIND_DISC) {
        if (h->stream.close) h->stream.close(h->stream.user_data);
        pthread_mutex_destroy(&h->lock);
    } else if (h->kind == KIND_PARTITION) {
        free(h->boot); free(h->bi2); free(h->apploader); free(h->dol); free(h->fst);
    }
    free(h);
}

int64_t nod_read(struct NodHandle *h, uint8_t *buf, size_t len) {
    struct NodHandle *disc;
    int64_t r;
    if (!h || (h->kind != KIND_DISC && h->kind != KIND_FILE)) return -1;
    disc = h->kind == KIND_DISC ? h : h->disc;
    if (h->pos >= h->length) return 0;
    if (len > h->length - h->pos) len = (size_t)(h->length - h->pos);
    r = read_at(disc, h->base + h->pos, buf, len);
    if (r > 0) h->pos += (uint64_t)r;
    return r;
}

int64_t nod_seek(struct NodHandle *h, int64_t offset, int32_t whence) {
    int64_t base;
    if (!h || (h->kind != KIND_DISC && h->kind != KIND_FILE)) return -1;
    base = whence == 1 ? (int64_t)h->pos : whence == 2 ? (int64_t)h->length : 0;
    if (base + offset < 0) return -1;
    h->pos = (uint64_t)(base + offset);
    return (int64_t)h->pos;
}

const void *nod_buf_read(struct NodHandle *handle, size_t *out_len) {
    (void)handle;
    if (out_len) *out_len = 0;
    return NULL;
}

void nod_buf_consume(struct NodHandle *handle, size_t n) { (void)handle; (void)n; }

enum NodResult nod_disc_header(const struct NodHandle *disc, struct NodDiscHeader *out) {
    if (!disc || disc->kind != KIND_DISC || !out) return NOD_RESULT_ERR_INVALID_HANDLE;
    memcpy(out, disc->header, sizeof *out);
    return NOD_RESULT_OK;
}

enum NodResult nod_disc_meta(const struct NodHandle *disc, struct NodDiscMeta *out) {
    if (!disc || disc->kind != KIND_DISC || !out) return NOD_RESULT_ERR_INVALID_HANDLE;
    memset(out, 0, sizeof *out);
    return NOD_RESULT_OK;
}

uint64_t nod_disc_size(const struct NodHandle *disc) {
    return disc && disc->kind == KIND_DISC ? (uint64_t)disc->size : 0;
}

size_t nod_disc_partitions(const struct NodHandle *disc, struct NodPartitionInfo *out, size_t cap) {
    (void)disc; (void)out; (void)cap;
    return 0;
}

bool nod_partition_is_wii(const struct NodHandle *partition) { (void)partition; return false; }

enum NodResult nod_partition_meta(const struct NodHandle *p, struct NodPartitionMeta *out) {
    if (!p || p->kind != KIND_PARTITION || !out) return NOD_RESULT_ERR_INVALID_HANDLE;
    memset(out, 0, sizeof *out);
    out->raw_boot.data = p->boot;           out->raw_boot.size = 0x440;
    out->raw_bi2.data = p->bi2;             out->raw_bi2.size = 0x2000;
    out->raw_apploader.data = p->apploader; out->raw_apploader.size = p->apploader_size;
    out->raw_dol.data = p->dol;             out->raw_dol.size = p->dol_size;
    out->raw_fst.data = p->fst;             out->raw_fst.size = p->fst_size;
    return NOD_RESULT_OK;
}

static const char *entry_name(const struct NodHandle *p, uint32_t i) {
    uint32_t off = be32(p->fst + (size_t)i * 12) & 0xffffffu;
    size_t names = (size_t)p->entries * 12;
    if (names + off >= p->fst_size) return "";
    return (const char *)p->fst + names + off;
}

void nod_partition_iterate_fst(const struct NodHandle *p, NodFstCallback callback, void *user_data) {
    uint32_t i = 1;
    if (!p || p->kind != KIND_PARTITION || !callback) return;
    while (i < p->entries) {
        const uint8_t *e = p->fst + (size_t)i * 12;
        int dir = e[0] & 1;
        uint32_t next = callback(i, dir ? NOD_NODE_KIND_DIRECTORY : NOD_NODE_KIND_FILE,
                                 entry_name(p, i), be32(e + 8), user_data);
        if (next == NOD_FST_STOP) break;
        i = next > i ? next : i + 1;
    }
}

uint32_t nod_partition_find_file(const struct NodHandle *p, const char *path, enum NodNodeKind *out_kind,
                                 uint32_t *out_length) {
    uint32_t dir_end, i = 1;
    if (!p || p->kind != KIND_PARTITION || !path) return NOD_FST_STOP;
    dir_end = p->entries;
    while (*path == '/') path++;
    while (*path) {
        const char *slash = strchr(path, '/');
        size_t n = slash ? (size_t)(slash - path) : strlen(path);
        uint32_t found = NOD_FST_STOP;
        while (i < dir_end) {
            const uint8_t *e = p->fst + (size_t)i * 12;
            const char *name = entry_name(p, i);
            if (strlen(name) == n && !strncasecmp(name, path, n)) { found = i; break; }
            i = (e[0] & 1) ? be32(e + 8) : i + 1;
        }
        if (found == NOD_FST_STOP) return NOD_FST_STOP;
        path += n;
        while (*path == '/') path++;
        if (!*path) {
            const uint8_t *e = p->fst + (size_t)found * 12;
            if (out_kind) *out_kind = (e[0] & 1) ? NOD_NODE_KIND_DIRECTORY : NOD_NODE_KIND_FILE;
            if (out_length) *out_length = be32(e + 8);
            return found;
        }
        dir_end = be32(p->fst + (size_t)found * 12 + 8);
        i = found + 1;
    }
    return NOD_FST_STOP;
}
