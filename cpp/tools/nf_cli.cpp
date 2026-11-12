// nf-cli: command line front end for nf-core.
//   nf-cli devices
//   nf-cli run --in <index|name part> --out <index|name part> [--exclusive] [--bypass]
//              [--mode off|spectral|onnx] [--onnx model.onnx] [--strength 1.0] [--no-gate]
//   nf-cli process in.wav out.wav [--learn-seconds 2] [same filter options]
//   nf-cli bench
#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

#include "nf/nf.h"

#ifdef _WIN32
#include <windows.h>
#endif

namespace {

std::atomic<bool> g_stop{false};
void on_signal(int) { g_stop = true; }

struct Args {
  std::vector<std::string> pos;
  std::string in, out, mode = "spectral", onnx;
  bool exclusive = false, bypass = false, no_gate = false;
  float strength = 1.0f, hp = 80.0f, learn_seconds = 0.0f, gain_db = 0.0f;
};

Args parse(int argc, char** argv) {
  Args a;
  for (int i = 2; i < argc; ++i) {
    std::string s = argv[i];
    auto next = [&]() -> std::string { return i + 1 < argc ? argv[++i] : ""; };
    if (s == "--in") a.in = next();
    else if (s == "--out") a.out = next();
    else if (s == "--mode") a.mode = next();
    else if (s == "--onnx") { a.onnx = next(); a.mode = "onnx"; }
    else if (s == "--strength") a.strength = std::stof(next());
    else if (s == "--highpass") a.hp = std::stof(next());
    else if (s == "--gain") a.gain_db = std::stof(next());
    else if (s == "--learn-seconds") a.learn_seconds = std::stof(next());
    else if (s == "--exclusive") a.exclusive = true;
    else if (s == "--bypass") a.bypass = true;
    else if (s == "--no-gate") a.no_gate = true;
    else a.pos.push_back(s);
  }
  return a;
}

nf_pipeline* make_pipeline(const Args& a) {
  nf_config c;
  nf_default_config(&c);
  c.bypass = a.bypass;
  c.highpass_hz = a.hp;
  c.denoise = a.mode == "off" ? NF_DENOISE_OFF : a.mode == "onnx" ? NF_DENOISE_ONNX : NF_DENOISE_SPECTRAL;
  c.strength = a.strength;
  c.gate_enabled = !a.no_gate;
  c.output_gain_db = a.gain_db;
  nf_pipeline* p = nf_pipeline_create(&c);
  if (!a.onnx.empty()) {
    char err[512];
    if (nf_pipeline_load_onnx(p, a.onnx.c_str(), err, sizeof(err)) != 0) {
      std::fprintf(stderr, "ONNX load failed: %s\n", err);
      nf_pipeline_destroy(p);
      return nullptr;
    }
  }
  return p;
}

std::string lower(std::string s) {
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
  return s;
}

// Resolve "3" (index) or "cable input" (case-insensitive name part) to a device id.
bool resolve(int kind, const std::string& q, std::string* id) {
  if (q.empty()) { id->clear(); return true; }
  int n = nf_device_count(kind);
  bool numeric = !q.empty() && std::all_of(q.begin(), q.end(), [](unsigned char ch) { return std::isdigit(ch) != 0; });
  for (int i = 0; i < n; ++i) {
    nf_device_info d;
    if (nf_device_get(kind, i, &d) != 0) continue;
    if ((numeric && std::stoi(q) == i) || (!numeric && lower(d.name).find(lower(q)) != std::string::npos)) {
      *id = d.id;
      return true;
    }
  }
  return false;
}

int cmd_devices() {
  for (int kind : {NF_INPUT, NF_OUTPUT}) {
    std::printf("[%s]\n", kind == NF_INPUT ? "input" : "output");
    int n = nf_device_count(kind);
    for (int i = 0; i < n; ++i) {
      nf_device_info d;
      if (nf_device_get(kind, i, &d) == 0) std::printf("  %3d  %s%s\n", i, d.name, d.is_default ? "  (default)" : "");
    }
    if (n == 0) std::printf("  (none)\n");
  }
  return 0;
}

int cmd_run(const Args& a) {
  std::string in_id, out_id;
  if (!resolve(NF_INPUT, a.in, &in_id)) { std::fprintf(stderr, "input device not found: %s\n", a.in.c_str()); return 2; }
  if (!resolve(NF_OUTPUT, a.out, &out_id)) { std::fprintf(stderr, "output device not found: %s\n", a.out.c_str()); return 2; }
  nf_pipeline* p = make_pipeline(a);
  if (!p) return 1;
  char err[512] = {0};
  nf_engine* e = nf_engine_create(p, in_id.c_str(), out_id.c_str(), a.exclusive, err, sizeof(err));
  if (!e || nf_engine_start(e, err, sizeof(err)) != 0) {
    std::fprintf(stderr, "engine error: %s\n", err);
    nf_engine_destroy(e);
    nf_pipeline_destroy(p);
    return 1;
  }
  std::signal(SIGINT, on_signal);
  std::printf("Running (%s mode). 10 ms frames @ 48 kHz. Ctrl+C to stop.\n", a.exclusive ? "exclusive" : "shared");
  while (!g_stop) {
    std::this_thread::sleep_for(std::chrono::seconds(1));
    nf_engine_stats s;
    nf_engine_get_stats(e, &s);
    std::printf("\rframes %lld  xruns %lld  dsp avg %.0f us / max %.0f us  latency ~%.1f ms   ", s.frames, s.xruns,
                s.dsp_avg_us, s.dsp_max_us, s.latency_ms);
    std::fflush(stdout);
  }
  std::printf("\n");
  nf_engine_destroy(e);
  nf_pipeline_destroy(p);
  return 0;
}

// ---- minimal WAV I/O (PCM16 / PCM24 / PCM32 / float32, any channel count, mixed to mono) ----
bool read_wav(const std::string& path, std::vector<float>* out, int* rate) {
  std::ifstream f(path, std::ios::binary);
  if (!f) return false;
  char riff[12];
  f.read(riff, 12);
  if (std::memcmp(riff, "RIFF", 4) || std::memcmp(riff + 8, "WAVE", 4)) return false;
  uint16_t fmt = 0, ch = 0, bits = 0;
  uint32_t sr = 0;
  for (;;) {
    char id[4];
    uint32_t sz;
    if (!f.read(id, 4) || !f.read(reinterpret_cast<char*>(&sz), 4)) return false;
    if (!std::memcmp(id, "fmt ", 4)) {
      std::vector<char> b(sz);
      f.read(b.data(), sz);
      std::memcpy(&fmt, &b[0], 2);
      std::memcpy(&ch, &b[2], 2);
      std::memcpy(&sr, &b[4], 4);
      std::memcpy(&bits, &b[14], 2);
      if (fmt == 0xFFFE && sz >= 26) std::memcpy(&fmt, &b[24], 2);  // extensible: subformat tag
    } else if (!std::memcmp(id, "data", 4)) {
      std::vector<unsigned char> b(sz);
      f.read(reinterpret_cast<char*>(b.data()), sz);
      const int bps = bits / 8;
      if (!ch || !bps) return false;
      const size_t n = sz / (bps * ch);
      out->assign(n, 0.0f);
      for (size_t i = 0; i < n; ++i) {
        float acc = 0;
        for (int c = 0; c < ch; ++c) {
          const unsigned char* p = &b[(i * ch + c) * bps];
          float v = 0;
          if (fmt == 3 && bits == 32) std::memcpy(&v, p, 4);
          else if (bits == 16) v = static_cast<int16_t>(p[0] | (p[1] << 8)) / 32768.0f;
          else if (bits == 24) v = static_cast<int32_t>((p[0] << 8) | (p[1] << 16) | (p[2] << 24)) / 2147483648.0f;
          else if (bits == 32) { int32_t x; std::memcpy(&x, p, 4); v = x / 2147483648.0f; }
          acc += v;
        }
        (*out)[i] = acc / ch;
      }
      *rate = static_cast<int>(sr);
      return true;
    } else {
      f.seekg(sz + (sz & 1), std::ios::cur);
    }
  }
}

bool write_wav(const std::string& path, const std::vector<float>& x, int rate) {
  std::ofstream f(path, std::ios::binary);
  if (!f) return false;
  auto u32 = [&](uint32_t v) { f.write(reinterpret_cast<char*>(&v), 4); };
  auto u16 = [&](uint16_t v) { f.write(reinterpret_cast<char*>(&v), 2); };
  const uint32_t data = static_cast<uint32_t>(x.size() * 2);
  f.write("RIFF", 4); u32(36 + data); f.write("WAVE", 4);
  f.write("fmt ", 4); u32(16); u16(1); u16(1); u32(rate); u32(rate * 2); u16(2); u16(16);
  f.write("data", 4); u32(data);
  for (float v : x) u16(static_cast<uint16_t>(static_cast<int16_t>(std::lrint(std::max(-1.0f, std::min(1.0f, v)) * 32767.0f))));
  return true;
}

int cmd_process(const Args& a) {
  if (a.pos.size() < 2) { std::fprintf(stderr, "usage: nf-cli process in.wav out.wav [options]\n"); return 2; }
  std::vector<float> x;
  int rate = 0;
  if (!read_wav(a.pos[0], &x, &rate)) { std::fprintf(stderr, "cannot read %s\n", a.pos[0].c_str()); return 1; }
  if (rate != nf_sample_rate()) { std::fprintf(stderr, "need a 48 kHz file (got %d Hz)\n", rate); return 1; }
  nf_pipeline* p = make_pipeline(a);
  if (!p) return 1;
  const int n = nf_frame_size();
  const size_t frames = x.size() / n;
  if (a.learn_seconds > 0) {  // learn the noise profile from the start of the file
    std::vector<float> tmp(n);
    nf_pipeline_learn_start(p);
    const size_t lf = std::min(frames, static_cast<size_t>(a.learn_seconds * rate / n));
    for (size_t i = 0; i < lf; ++i) nf_pipeline_process(p, &x[i * n], tmp.data());
    nf_pipeline_learn_finish(p);
  }
  std::vector<float> y(frames * n);
  auto t0 = std::chrono::steady_clock::now();
  for (size_t i = 0; i < frames; ++i) nf_pipeline_process(p, &x[i * n], &y[i * n]);
  double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
  nf_pipeline_destroy(p);
  if (!write_wav(a.pos[1], y, rate)) { std::fprintf(stderr, "cannot write %s\n", a.pos[1].c_str()); return 1; }
  std::printf("%zu frames, %.3f ms per 10 ms frame (%.0fx realtime)\n", frames, ms / std::max<size_t>(frames, 1),
              frames * 10.0 / std::max(ms, 1e-9));
  return 0;
}

int cmd_bench(const Args& a) {
  nf_pipeline* p = make_pipeline(a);
  if (!p) return 1;
  const int n = nf_frame_size();
  std::vector<float> x(n), y(n);
  uint32_t seed = 1;
  for (auto& v : x) { seed = seed * 1664525u + 1013904223u; v = ((seed >> 8) / 16777216.0f - 0.5f) * 0.1f; }
  for (int i = 0; i < 200; ++i) nf_pipeline_process(p, x.data(), y.data());
  const int iters = 5000;
  double worst = 0;
  auto t0 = std::chrono::steady_clock::now();
  for (int i = 0; i < iters; ++i) {
    auto a0 = std::chrono::steady_clock::now();
    nf_pipeline_process(p, x.data(), y.data());
    worst = std::max(worst, std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - a0).count());
  }
  double us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count() / iters;
  std::printf("mode=%s  avg %.1f us  worst %.1f us per 10 ms frame (budget 10000 us)\n", a.mode.c_str(), us, worst);
  nf_pipeline_destroy(p);
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
#ifdef _WIN32
  SetConsoleOutputCP(CP_UTF8);
#endif
  if (argc < 2) {
    std::printf("nf-cli (nf-core API %d, ONNX %s)\n"
                "  devices\n"
                "  run --in <index|name> --out <index|name> [--exclusive] [--mode off|spectral|onnx] [--onnx m.onnx]\n"
                "      [--strength 1.0] [--highpass 80] [--gain 0] [--no-gate] [--bypass]\n"
                "  process in.wav out.wav [--learn-seconds 2] [filter options]\n"
                "  bench [filter options]\n",
                nf_api_version(), nf_has_onnx() ? "yes" : "no");
    return 0;
  }
  std::string cmd = argv[1];
  Args a = parse(argc, argv);
  if (cmd == "devices") return cmd_devices();
  if (cmd == "run") return cmd_run(a);
  if (cmd == "process") return cmd_process(a);
  if (cmd == "bench") return cmd_bench(a);
  std::fprintf(stderr, "unknown command: %s\n", cmd.c_str());
  return 2;
}
