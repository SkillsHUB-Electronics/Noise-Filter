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
};

// mic frame -> highpass -> denoise -> gate -> gain (single-threaded).
class Pipeline {
 public:
  explicit Pipeline(const Config& cfg = Config());
  ~Pipeline();
  // Live update: keeps learned profile and filter states (like Python update()).
  void update(const Config& cfg);
  const Config& config() const { return cfg_; }
  // Returns false with err set if ONNX support is not compiled in or load fails.
  bool load_onnx(const std::string& path, std::string* err);
  bool has_onnx() const { return onnx_ != nullptr; }
  // Swap in an already-loaded model (takes ownership); returns the previous one.
  OnnxDenoiser* exchange_onnx(OnnxDenoiser* d);
  void process(const float* in, float* out);  // in may equal out

  SpectralDenoiser& spectral() { return spectral_; }
  SpectrumAnalyzer in_analyzer, out_analyzer;

 private:
  Config cfg_;
  HighPass hp_;
  NoiseGate gate_;
  SpectralDenoiser spectral_;
  std::unique_ptr<OnnxDenoiser> onnx_;
  std::vector<float> a_, b_;
};

}  // namespace nf
