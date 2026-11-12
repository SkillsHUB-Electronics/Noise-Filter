#include <algorithm>
#include <cmath>
#include <cstring>

#include "core.hpp"

#define POCKETFFT_NO_MULTITHREADING
#include "pocketfft_hdronly.h"

namespace nf {

namespace {
constexpr double kPi = 3.14159265358979323846;
}

// ---------------------------------------------------------------- RealFft
struct RealFft::Impl {
  explicit Impl(int n) : plan(static_cast<size_t>(n)), work(static_cast<size_t>(n)) {}
  pocketfft::detail::pocketfft_r<float> plan;
  std::vector<float> work;
};

RealFft::RealFft(int n) : n_(n), impl_(new Impl(n)) {}
RealFft::~RealFft() = default;

void RealFft::forward(const float* in, float* re, float* im) {
  float* w = impl_->work.data();
  std::memcpy(w, in, sizeof(float) * n_);
  impl_->plan.exec(w, 1.0f, true);  // halfcomplex: r0 r1 i1 r2 i2 ... [r(n/2)]
  const int bins = n_ / 2 + 1;
  re[0] = w[0];
  im[0] = 0.0f;
  for (int k = 1; k < bins; ++k) {
    re[k] = w[2 * k - 1];
    im[k] = (2 * k < n_) ? w[2 * k] : 0.0f;
  }
}

void RealFft::inverse(const float* re, const float* im, float* out) {
  const int bins = n_ / 2 + 1;
  out[0] = re[0];
  for (int k = 1; k < bins; ++k) {
    out[2 * k - 1] = re[k];
    if (2 * k < n_) out[2 * k] = im[k];
  }
  impl_->plan.exec(out, 1.0f / static_cast<float>(n_), false);
}

// ---------------------------------------------------------------- HighPass
HighPass::HighPass(double cutoff_hz, int sample_rate) {
  const double w0 = 2.0 * kPi * cutoff_hz / sample_rate;
  const double cosw = std::cos(w0), alpha = std::sin(w0) / (2.0 * std::sqrt(0.5));
  const double a0 = 1.0 + alpha;
  b_[0] = (1.0 + cosw) / 2.0 / a0;
  b_[1] = -(1.0 + cosw) / a0;
  b_[2] = (1.0 + cosw) / 2.0 / a0;
  a_[0] = 1.0;
  a_[1] = -2.0 * cosw / a0;
  a_[2] = (1.0 - alpha) / a0;
  z_[0] = z_[1] = 0.0;
}

void HighPass::process(const float* x, float* y, int n) {
  for (int i = 0; i < n; ++i) {  // direct form II transposed
    const double s = x[i];
    const double o = b_[0] * s + z_[0];
    z_[0] = b_[1] * s - a_[1] * o + z_[1];
    z_[1] = b_[2] * s - a_[2] * o;
    y[i] = static_cast<float>(o);
  }
}

// ---------------------------------------------------------------- NoiseGate
NoiseGate::NoiseGate(double threshold_db, double attack, double release, double floor_db)
    : threshold_(std::pow(10.0, threshold_db / 20.0)),
      floor_(std::pow(10.0, floor_db / 20.0)),
      attack_(attack),
      release_(release) {}

void NoiseGate::set_threshold_db(double db) { threshold_ = std::pow(10.0, db / 20.0); }

void NoiseGate::process(const float* x, float* y, int n) {
  double acc = 0.0;
  for (int i = 0; i < n; ++i) acc += static_cast<double>(x[i]) * x[i];
  const double rms = std::sqrt(acc / n + 1e-12);
  const double target = rms >= threshold_ ? 1.0 : floor_;
  const double k = target > gain_ ? attack_ : release_;
  const double g0 = gain_;
  gain_ = g0 + k * (target - g0);
  const double step = (gain_ - g0) / n;
  for (int i = 0; i < n; ++i) y[i] = x[i] * static_cast<float>(g0 + step * i);
}

// ---------------------------------------------------------------- SpectralDenoiser
SpectralDenoiser::SpectralDenoiser(float strength_, float floor_, float smoothing_, float rise_)
    : strength(strength_), floor(floor_), smoothing(smoothing_), rise(rise_), fft_(2 * kFrameSize) {
  const int n2 = 2 * kFrameSize;
  win_.resize(n2);
  for (int k = 0; k < n2; ++k)  // periodic sqrt-Hann
    win_[k] = static_cast<float>(std::sqrt(0.5 - 0.5 * std::cos(2.0 * kPi * k / n2)));
  prev_.assign(kFrameSize, 0.0f);
  tail_.assign(kFrameSize, 0.0f);
  buf_.assign(n2, 0.0f);
  out_.assign(n2, 0.0f);
  re_.assign(kSpectralBins, 0.0f);
  im_.assign(kSpectralBins, 0.0f);
  p_.assign(kSpectralBins, 0.0f);
  ps_.assign(kSpectralBins, 0.0f);
  noise_.assign(kSpectralBins, 0.0f);
  gain_prev_.assign(kSpectralBins, 1.0f);
  profile_.assign(kSpectralBins, 0.0f);
  learn_sum_.assign(kSpectralBins, 0.0);
}

void SpectralDenoiser::start_learning() {
  std::fill(learn_sum_.begin(), learn_sum_.end(), 0.0);
  learn_count_ = 0;
  learning_ = true;
}

void SpectralDenoiser::finish_learning() {
  if (learning_ && learn_count_ > 0) {
    for (int k = 0; k < kSpectralBins; ++k)
      profile_[k] = static_cast<float>(learn_sum_[k] / learn_count_);
    has_profile_ = true;
  }
  learning_ = false;
}

void SpectralDenoiser::set_profile(const float* p) {
  std::copy(p, p + kSpectralBins, profile_.begin());
  has_profile_ = true;
}

void SpectralDenoiser::process(const float* x, float* y) {
  const int n = kFrameSize, n2 = 2 * n;
  for (int i = 0; i < n; ++i) {
    buf_[i] = prev_[i] * win_[i];
    buf_[n + i] = x[i] * win_[n + i];
  }
  std::copy(x, x + n, prev_.begin());
  fft_.forward(buf_.data(), re_.data(), im_.data());
  for (int k = 0; k < kSpectralBins; ++k) p_[k] = re_[k] * re_[k] + im_[k] * im_[k];

  if (learning_) {
    for (int k = 0; k < kSpectralBins; ++k) learn_sum_[k] += p_[k];
    ++learn_count_;
  }

  const float* noise;
  float bias;
  if (has_profile_) {
    noise = profile_.data();
    bias = 1.0f;
  } else {
    if (!adaptive_init_) {
      ps_ = p_;
      noise_ = p_;
      adaptive_init_ = true;
    }
    const float up = 1.0f + rise;
    for (int k = 0; k < kSpectralBins; ++k) {
      ps_[k] = 0.9f * ps_[k] + 0.1f * p_[k];  // smooth first: raw bin power is very noisy
      noise_[k] = std::min(ps_[k], noise_[k] * up);
    }
    noise = noise_.data();
    bias = 2.0f;  // min-tracker underestimates the mean
  }

  for (int k = 0; k < kSpectralBins; ++k) {
    float g = std::max(1.0f - strength * (noise[k] * bias) / (p_[k] + 1e-12f), floor);
    g = smoothing * gain_prev_[k] + (1.0f - smoothing) * g;
    gain_prev_[k] = g;
    re_[k] *= g;
    im_[k] *= g;
  }
  fft_.inverse(re_.data(), im_.data(), out_.data());
  for (int i = 0; i < n; ++i) {
    y[i] = tail_[i] + out_[i] * win_[i];
    tail_[i] = out_[n + i] * win_[n + i];
  }
  (void)n2;
}

// ---------------------------------------------------------------- Analyzer
SpectrumAnalyzer::SpectrumAnalyzer(float) : ring_(kAnalyzerSize, 0.0f) {}

void SpectrumAnalyzer::push(const float* frame, int n) {
  for (int i = 0; i < n; ++i) {
    ring_[pos_] = frame[i];
    pos_ = (pos_ + 1) % kAnalyzerSize;
  }
}

void SpectrumAnalyzer::snapshot(float* out) const {
  const int first = kAnalyzerSize - pos_;
  std::memcpy(out, ring_.data() + pos_, sizeof(float) * first);
  std::memcpy(out + first, ring_.data(), sizeof(float) * pos_);
}

float SpectrumAnalyzer::level_db(const float* buf) {
  double acc = 0.0;
  const float* last = buf + kAnalyzerSize - kFrameSize;
  for (int i = 0; i < kFrameSize; ++i) acc += static_cast<double>(last[i]) * last[i];
  return static_cast<float>(20.0 * std::log10(std::sqrt(acc / kFrameSize) + 1e-9));
}

SpectrumView::SpectrumView(float smoothing)
    : smoothing_(smoothing),
      fft_(kAnalyzerSize),
      win_(kAnalyzerSize),
      tmp_(kAnalyzerSize),
      re_(kAnalyzerBins),
      im_(kAnalyzerBins),
      db_(kAnalyzerBins, -120.0f) {
  for (int k = 0; k < kAnalyzerSize; ++k)  // symmetric Hann, like numpy.hanning
    win_[k] = static_cast<float>(0.5 - 0.5 * std::cos(2.0 * kPi * k / (kAnalyzerSize - 1)));
}

void SpectrumView::update(const float* snap, float* db_out) {
  for (int i = 0; i < kAnalyzerSize; ++i) tmp_[i] = snap[i] * win_[i];
  fft_.forward(tmp_.data(), re_.data(), im_.data());
  const float scale = 1.0f / (kAnalyzerSize / 4.0f);
  for (int k = 0; k < kAnalyzerBins; ++k) {
    const float mag = std::sqrt(re_[k] * re_[k] + im_[k] * im_[k]) * scale;
    const float db = 20.0f * std::log10(mag + 1e-9f);
    db_[k] = smoothing_ * db_[k] + (1.0f - smoothing_) * db;
    db_out[k] = db_[k];
  }
}

}  // namespace nf
