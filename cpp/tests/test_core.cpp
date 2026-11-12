// C++ mirror of tests/test_core.py (behaviour), plus FFT and C API checks.
// Bit-level parity with Python is checked in tests/test_native_parity.py.
#include <chrono>
#include <cmath>
#include <cstdio>
#include <random>
#include <vector>

#include "core.hpp"
#include "nf/nf.h"

using namespace nf;

static const double kPi = 3.14159265358979323846;

static int g_fail = 0;
#define CHECK(cond, ...)                                  \
  do {                                                    \
    if (!(cond)) {                                        \
      std::printf("FAIL %s:%d: ", __FILE__, __LINE__);    \
      std::printf(__VA_ARGS__);                           \
      std::printf("\n");                                  \
      ++g_fail;                                           \
    }                                                     \
  } while (0)

static std::vector<float> run(Pipeline& p, const std::vector<float>& x) {
  size_t n = x.size() / kFrameSize;
  std::vector<float> y(n * kFrameSize);
  for (size_t i = 0; i < n; ++i) p.process(&x[i * kFrameSize], &y[i * kFrameSize]);
  return y;
}

static std::vector<float> tone(double f, double secs, double amp = 0.3) {
  std::vector<float> x(static_cast<size_t>(kSampleRate * secs));
  for (size_t i = 0; i < x.size(); ++i) x[i] = static_cast<float>(amp * std::sin(2 * kPi * f * i / kSampleRate));
  return x;
}

static std::vector<float> noise(double secs, double amp, unsigned seed) {
  std::mt19937 rng(seed);
  std::normal_distribution<float> nd(0.0f, 1.0f);
  std::vector<float> x(static_cast<size_t>(kSampleRate * secs));
  for (auto& v : x) v = static_cast<float>(amp) * nd(rng);
  return x;
}

static double rms_db(const float* x, size_t n) {
  double a = 0;
  for (size_t i = 0; i < n; ++i) a += double(x[i]) * x[i];
  return 20 * std::log10(std::sqrt(a / n) + 1e-12);
}
static double rms_db(const std::vector<float>& x) { return rms_db(x.data(), x.size()); }

static void test_fft_roundtrip() {
  RealFft f(960);
  std::vector<float> x(960), y(960), re(481), im(481);
  for (int i = 0; i < 960; ++i) x[i] = std::sin(0.1f * i) + 0.25f * std::cos(0.37f * i);
  f.forward(x.data(), re.data(), im.data());
  f.inverse(re.data(), im.data(), y.data());
  double err = 0;
  for (int i = 0; i < 960; ++i) err = std::max(err, double(std::fabs(x[i] - y[i])));
  CHECK(err < 1e-5, "fft roundtrip err %g", err);
  // DC bin of a constant
  std::vector<float> c(960, 1.0f);
  f.forward(c.data(), re.data(), im.data());
  CHECK(std::fabs(re[0] - 960.0f) < 1e-3 && std::fabs(re[5]) < 1e-3, "fft dc");
}

static void test_bypass_is_identity() {
  Config c;
  c.bypass = true;
  Pipeline p(c);
  auto x = tone(440, 0.2);
  auto y = run(p, x);
  double err = 0;
  for (size_t i = 0; i < y.size(); ++i) err = std::max(err, double(std::fabs(x[i] - y[i])));
  CHECK(err < 1e-6, "bypass err %g", err);
}

static void test_denoise_reduces_noise_keeps_tone() {
  auto nz = noise(3, 0.02, 0);
  Config c;
  c.gate_enabled = false;
  Pipeline p(c);
  auto out = run(p, nz);
  double in_db = rms_db(&nz[nz.size() - kSampleRate], kSampleRate);
  double out_db = rms_db(&out[out.size() - kSampleRate], kSampleRate);
  CHECK(out_db < in_db - 8, "noise only: in %.1f out %.1f dB", in_db, out_db);

  auto t = tone(1000, 2.0);
  std::vector<float> sig(t.size());
  for (size_t i = 0; i < t.size(); ++i) sig[i] = t[i] + nz[i];
  Pipeline p2(c);
  run(p2, std::vector<float>(nz.begin(), nz.begin() + kSampleRate));
  auto o = run(p2, sig);
  double o_db = rms_db(&o[kSampleRate], o.size() - kSampleRate);
  CHECK(o_db > rms_db(tone(1000, 1.0)) - 3, "tone kept: %.1f dB", o_db);
}

static void test_learned_profile() {
  auto nz = noise(2, 0.02, 1);
  Config c;
  c.gate_enabled = false;
  c.highpass_hz = 0;
  Pipeline p(c);
  p.spectral().start_learning();
  run(p, nz);
  p.spectral().finish_learning();
  CHECK(p.spectral().has_profile(), "profile learned");
  auto out = run(p, nz);
  CHECK(rms_db(out) < rms_db(nz) - 8, "learned profile: in %.1f out %.1f", rms_db(nz), rms_db(out));
}

static void test_latency_one_frame() {
  Config c;
  c.gate_enabled = false;
  c.highpass_hz = 0;
  Pipeline p(c);
  p.spectral().strength = 0.0f;
  p.spectral().floor = 1.0f;
  std::vector<float> x(kFrameSize * 6, 0.0f);
  const int at = kFrameSize * 2 + 10;
  x[at] = 1.0f;
  auto y = run(p, x);
  int peak = 0;
  for (size_t i = 0; i < y.size(); ++i)
    if (std::fabs(y[i]) > std::fabs(y[peak])) peak = static_cast<int>(i);
  CHECK(peak - at <= kFrameSize && peak >= at, "latency %d samples", peak - at);
  CHECK(std::fabs(y[peak] - 1.0f) < 1e-3, "unity path amplitude %f", y[peak]);
}

static void test_analyzer_peak() {
  nf_pipeline* p = nf_pipeline_create(nullptr);
  nf_config c;
  nf_pipeline_get_config(p, &c);
  c.bypass = 1;
  nf_pipeline_set_config(p, &c);
  auto x = tone(1000, 0.1);
  std::vector<float> y(kFrameSize), db(nf_analyzer_bins());
  for (size_t i = 0; i + kFrameSize <= x.size(); i += kFrameSize) nf_pipeline_process(p, &x[i], y.data());
  for (int i = 0; i < 10; ++i) nf_pipeline_spectrum_db(p, NF_OUTPUT, db.data());
  int k = 0;
  for (int i = 0; i < nf_analyzer_bins(); ++i)
    if (db[i] > db[k]) k = i;
  double f = k * double(kSampleRate) / kAnalyzerSize;
  CHECK(std::fabs(f - 1000) < 30, "analyzer peak at %.0f Hz", f);
  float lvl = nf_pipeline_level_db(p, NF_INPUT);
  CHECK(std::fabs(lvl - 20 * std::log10(0.3 / std::sqrt(2.0))) < 0.5, "level %.2f dB", lvl);
  nf_pipeline_destroy(p);
}

static void test_capi_profile_roundtrip() {
  nf_pipeline* p = nf_pipeline_create(nullptr);
  auto nz = noise(1, 0.02, 2);
  std::vector<float> y(kFrameSize), prof(nf_profile_bins());
  CHECK(nf_pipeline_get_profile(p, prof.data()) == 0, "no profile at start");
  nf_pipeline_learn_start(p);
  for (size_t i = 0; i + kFrameSize <= nz.size(); i += kFrameSize) nf_pipeline_process(p, &nz[i], y.data());
  nf_pipeline_learn_finish(p);
  nf_pipeline_process(p, &nz[0], y.data());  // finish is applied at a frame boundary
  CHECK(nf_pipeline_get_profile(p, prof.data()) == 1 && prof[100] > 0, "profile learned via C API");
  nf_pipeline* q = nf_pipeline_create(nullptr);
  nf_pipeline_set_profile(q, prof.data());
  nf_pipeline_process(q, &nz[0], y.data());
  std::vector<float> prof2(nf_profile_bins());
  CHECK(nf_pipeline_get_profile(q, prof2.data()) == 1 && prof2[100] == prof[100], "profile restored");
  char err[256];
  int rc = nf_pipeline_load_onnx(q, "does-not-exist.onnx", err, sizeof(err));
  CHECK(rc != 0, "loading a missing model fails cleanly");
  nf_pipeline_destroy(p);
  nf_pipeline_destroy(q);
}

static void test_realtime_cost() {
  Pipeline p;
  auto x = noise(0.01, 0.05, 3);
  std::vector<float> y(kFrameSize);
  for (int i = 0; i < 100; ++i) p.process(x.data(), y.data());
  const int iters = 2000;
  auto t0 = std::chrono::steady_clock::now();
  for (int i = 0; i < iters; ++i) p.process(x.data(), y.data());
  double us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count() / iters;
  std::printf("per-frame cost: %.1f us of 10000 us budget\n", us);
  CHECK(us < 2000, "too slow: %.1f us", us);
}

int main() {
  test_fft_roundtrip();
  test_bypass_is_identity();
  test_denoise_reduces_noise_keeps_tone();
  test_learned_profile();
  test_latency_one_frame();
  test_analyzer_peak();
  test_capi_profile_roundtrip();
  test_realtime_cost();
  if (g_fail) {
    std::printf("%d check(s) failed\n", g_fail);
    return 1;
  }
  std::printf("all nf-core tests passed\n");
  return 0;
}
