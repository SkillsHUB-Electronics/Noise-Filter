// Placeholder engine for platforms without a native backend yet (Linux CI, macOS).
// Android (Oboe) and iOS (AVAudioEngine) backends are planned.
#ifndef _WIN32
#include <cstdio>

#include "nf/nf.h"

extern "C" {
int nf_device_count(int) { return 0; }
int nf_device_get(int, int, nf_device_info*) { return -1; }
nf_engine* nf_engine_create(nf_pipeline*, const char*, const char*, int, char* err, int err_len) {
  if (err && err_len > 0) std::snprintf(err, err_len, "no realtime audio backend on this platform yet");
  return nullptr;
}
int nf_engine_start(nf_engine*, char* err, int err_len) {
  if (err && err_len > 0) std::snprintf(err, err_len, "no realtime audio backend on this platform yet");
  return -1;
}
void nf_engine_stop(nf_engine*) {}
void nf_engine_destroy(nf_engine*) {}
void nf_engine_get_stats(nf_engine*, nf_engine_stats* s) {
  if (s) *s = nf_engine_stats{0, 0, 0.0f, 0.0f, 0.0f};
}
}
#endif
