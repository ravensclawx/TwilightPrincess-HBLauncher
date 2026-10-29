#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nod.h"
static int64_t rd(void *u, uint64_t off, void *out, size_t len) { FILE *f = u; if (fseeko(f, (off_t)off, SEEK_SET)) return -1; return (int64_t)fread(out, 1, len, f); }
static int64_t ln(void *u) { FILE *f = u; fseeko(f, 0, SEEK_END); return ftello(f); }
static void cl(void *u) { fclose(u); }
static struct NodHandle *part; static int files; static unsigned long long total_hash;
static uint32_t cb(uint32_t i, enum NodNodeKind k, const char *name, uint32_t size, void *u) {
  (void)u; printf("%u %d %s %u\n", i, (int)k, name, size);
  if (k == NOD_NODE_KIND_FILE && (i % 7 == 0)) {
    struct NodHandle *f; static unsigned char buf[1 << 20]; unsigned long long h = 1469598103934665603ull; int64_t n, got = 0;
    if (nod_partition_open_file(part, i, &f) != NOD_RESULT_OK) { printf("open fail %u\n", i); return i + 1; }
    nod_seek(f, size / 3, 0); nod_seek(f, 0, 0);
    while ((n = nod_read(f, buf, sizeof buf)) > 0) { for (int64_t j = 0; j < n; j++) h = (h ^ buf[j]) * 1099511628211ull; got += n; }
    printf("  hash %016llx len %lld\n", h, (long long)got); total_hash ^= h; files++; nod_free(f);
  }
  return i + 1;
}
int main(int argc, char **argv) {
  struct NodHandle *disc; NodDiscStream s = { fopen(argv[1], "rb"), rd, ln, cl }; NodDiscOptions o = {0};
  if (nod_disc_open_stream(&s, &o, &disc) != NOD_RESULT_OK) { printf("open: %s\n", nod_error_message()); return 1; }
  NodDiscHeader h; nod_disc_header(disc, &h); printf("id %.6s title %.40s disc %d ver %d\n", h.game_id, h.game_title, h.disc_num, h.disc_version);
  if (nod_disc_open_partition_kind(disc, NOD_PARTITION_KIND_DATA, NULL, &part) != NOD_RESULT_OK) { printf("part: %s\n", nod_error_message()); return 1; }
  NodPartitionMeta m; nod_partition_meta(part, &m);
  printf("boot %zu bi2 %zu app %zu dol %zu fst %zu\n", m.raw_boot.size, m.raw_bi2.size, m.raw_apploader.size, m.raw_dol.size, m.raw_fst.size);
  unsigned long long dh = 1469598103934665603ull; for (size_t j = 0; j < m.raw_dol.size; j++) dh = (dh ^ m.raw_dol.data[j]) * 1099511628211ull; printf("dol hash %016llx\n", dh);
  nod_partition_iterate_fst(part, cb, NULL);
  enum NodNodeKind k; uint32_t len; printf("find res/Object: %u\n", nod_partition_find_file(part, "res/Object", &k, &len));
  printf("files %d xor %016llx\n", files, total_hash);
  nod_free(part); nod_free(disc); return 0;
}
