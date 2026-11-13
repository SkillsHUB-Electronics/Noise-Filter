// nf-core: realtime noise filter DSP. 1:1 port of noise_filter/core (Python).
// Contract: every processor takes one mono float frame of kFrameSize samples
// (48 kHz, -1..1) and writes one frame of the same size. No allocation in
// process() except inside the FFT library's scratch buffer.
#pragma once
#include <cstddef>
#include <memory>
#include <string>
#include <vector>

namespace nf {

constexpr int kSampleRate = 48000;
constexpr int kFrameSize = 480;  // 10 ms
constexpr int kAnalyzerSize = 2048;
constexpr int kAnalyzerBins = kAnalyzerSize / 2 + 1;
constexpr int kSpectralBins = kFrameSize + 1;  // rfft of 2*kFrameSize

// Real FFT of fixed length n, numpy-compatible packing (n/2+1 complex bins).
class RealFft {
 public:
  explicit RealFft(int n);
  ~RealFft();
  int size() const { return n_; }
  // in: n reals -> re/im: n/2+1 each
  void forward(const float* in, float* re, float* im);
  // re/im: n/2+1 each -> out: n reals (normalized like numpy.fft.irfft)
  void inverse(const float* re, const float* im, float* out);

 private:
  int n_;
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

class HighPass {
 public:
  explicit HighPass(double cutoff_hz = 80.0, int sample_rate = kSampleRate);
  void process(const float* x, float* y, int n);
  void reset() { z_[0] = z_[1] = 0.0; }

 private:
  double b_[3], a_[3], z_[2];
};

// Parametric EQ (port of noise_filter/core/eq.py). Fixed storage: set() and
// process() never allocate, so set() may run on the audio thread.
enum class EqType { Peak = 0, LowShelf, HighShelf, LowPass, HighPass, BandPass, Notch };
constexpr int kEqMaxBands = 8;
constexpr int kEqMaxSectionsPerBand = 4;

struct EqBand {
  EqType type = EqType::Peak;
  bool on = true;
  double freq_hz = 1000.0, gain_db = 0.0, q = 0.71;
  int slope_db = 12;  // low/high-pass only: 12, 24, 36 or 48 (Butterworth)
};

class Equalizer {
 public:
  void set(bool enabled, const EqBand* bands, int count);
  bool active() const { return enabled_ && nsec_ > 0; }
  void process(const float* x, float* y, int n);
  // Normalized sections (b0 b1 b2 a1 a2) of one band; returns the count (0 = off).
  static int design(const EqBand& b, int sample_rate, double out[][5]);

 private:
  bool enabled_ = false;
  int nsec_ = 0;
  int layout_[kEqMaxBands] = {};
  int nbands_ = 0;
  double sos_[kEqMaxBands * kEqMaxSectionsPerBand][5] = {};
  double z_[kEqMaxBands * kEqMaxSectionsPerBand][2] = {};
};

// Compressor (soft knee, log-domain gain smoothing) and zero-latency peak limiter.
// Port of noise_filter/core/dynamics.py.
class Compressor {
 public:
  Compressor() { set(-24.0, 3.0, 10.0, 150.0, 0.0); }
  void set(double threshold_db, double ratio, double attack_ms, double release_ms, double makeup_db);
  void process(const float* x, float* y, int n);
  double gr_db() const { return -gs_; }
  static double static_curve_db(double x_db, double threshold_db, double ratio);

 private:
  double threshold_ = -24.0, ratio_ = 3.0, makeup_ = 0.0, aa_ = 0.0, ar_ = 0.0, gs_ = 0.0;
};

class Limiter {
 public:
  Limiter();
  void set(double ceiling_db);
  void process(const float* x, float* y, int n);
  double gr_db() const;

 private:
  double ceiling_ = 1.0, ar_ = 0.0, g_ = 1.0;
};

class NoiseGate {
 public:
  explicit NoiseGate(double threshold_db = -55.0, double attack = 0.5,
                     double release = 0.05, double floor_db = -40.0);
  void set_threshold_db(double db);
  void process(const float* x, float* y, int n);
  double gain() const { return gain_; }

 private:
  double threshold_, floor_, attack_, release_, gain_ = 1.0;
};

class SpectralDenoiser {
 public:
  explicit SpectralDenoiser(float strength = 1.0f, float floor = 0.08f,
                            float smoothing = 0.6f, float rise = 0.003f);
  void process(const float* x, float* y);  // kFrameSize in/out

  void start_learning();
  void finish_learning();
  bool learning() const { return learning_; }
  void clear_profile() { has_profile_ = false; }
  bool has_profile() const { return has_profile_; }
  const std::vector<float>& profile() const { return profile_; }
  void set_profile(const float* p);  // kSpectralBins values

  float strength, floor, smoothing, rise;

 private:
  RealFft fft_;
  std::vector<float> win_, prev_, tail_, buf_, re_, im_, p_, ps_, noise_,
      gain_prev_, out_, profile_;
  std::vector<double> learn_sum_;
  int learn_count_ = 0;
  bool learning_ = false, has_profile_ = false, adaptive_init_ = false;
};

// Rolling analyzer. push() is cheap (audio thread); spectrum is computed by
// the reader (UI thread) from a snapshot of the buffer.
class SpectrumAnalyzer {
 public:
  explicit SpectrumAnalyzer(float smoothing = 0.7f);
  void push(const float* frame, int n);
  void snapshot(float* out) const;  // kAnalyzerSize samples, oldest first
  // Stateless helpers used by the reader:
  static float level_db(const float* buf);  // RMS of last frame of a snapshot

 private:
  std::vector<float> ring_;
  int pos_ = 0;  // next write index
};

// Reader-side spectrum with smoothing (matches Python spectrum_db()).
class SpectrumView {
 public:
  explicit SpectrumView(float smoothing = 0.7f);
  void update(const float* snapshot, float* db_out);  // kAnalyzerBins

 private:
  float smoothing_;
  RealFft fft_;
  std::vector<float> win_, tmp_, re_, im_, db_;
};

class OnnxDenoiser;  // defined in onnx_denoiser.cpp (optional)

enum class DenoiseMode { Off = 0, Spectral = 1, Onnx = 2 };

struct Config {
  bool bypass = false;
  float highpass_hz = 80.0f;
  DenoiseMode denoise = DenoiseMode::Spectral;
  float strength = 1.0f;
  bool gate_enabled = true;
  float gate_threshold_db = -55.0f;
  float output_gain_db = 0.0f;
  bool comp_enabled = false;
  float comp_threshold_db = -24.0f;
  float comp_ratio = 3.0f;
  float comp_attack_ms = 10.0f;
  float comp_release_ms = 150.0f;
  float comp_makeup_db = 0.0f;
  bool limiter_enabled = true;
  float limiter_ceiling_db = -1.0f;
};

struct EqConfig {
  bool enabled = false;
  int count = 0;
  EqBand bands[kEqMaxBands];
};

// mic frame -> highpass -> denoise -> EQ -> gate -> compressor -> gain -> limiter (single-threaded).
class Pipeline {
 public:
  explicit Pipeline(const Config& cfg = Config());
  ~Pipeline();
  // Live update: keeps learned profile and filter states (like Python update()).
  void update(const Config& cfg);
  void set_eq(const EqConfig& eq) { eq_.set(eq.enabled, eq.bands, eq.count); }
  const Config& config() const { return cfg_; }
  // Returns false with err set if ONNX support is not compiled in or load fails.
  bool load_onnx(const std::string& path, std::string* err);
  bool has_onnx() const { return onnx_ != nullptr; }
  // Swap in an already-loaded model (takes ownership); returns the previous one.
  OnnxDenoiser* exchange_onnx(OnnxDenoiser* d);
  void process(const float* in, float* out);  // in may equal out

  SpectralDenoiser& spectral() { return spectral_; }
  double comp_gr_db() const { return cfg_.comp_enabled ? comp_.gr_db() : 0.0; }
  double limiter_gr_db() const { return cfg_.limiter_enabled ? limiter_.gr_db() : 0.0; }
  SpectrumAnalyzer in_analyzer, out_analyzer;

 private:
  Config cfg_;
  HighPass hp_;
  NoiseGate gate_;
  Equalizer eq_;
  Compressor comp_;
  Limiter limiter_;
  SpectralDenoiser spectral_;
  std::unique_ptr<OnnxDenoiser> onnx_;
  std::vector<float> a_, b_;
};

}  // namespace nf
