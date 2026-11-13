// Compressor and limiter: 1:1 port of noise_filter/core/dynamics.py (float64 state).
#include <algorithm>
#include <cmath>

#include "core.hpp"

namespace nf {

namespace {
constexpr double kKneeDb = 6.0;
constexpr double kLimiterReleaseMs = 60.0;

double coef(double ms) { return std::exp(-1.0 / (std::max(ms, 0.01) * 1e-3 * kSampleRate)); }
}  // namespace

double Compressor::static_curve_db(double x, double t, double r) {
  const double d = x - t;
  if (2 * d < -kKneeDb) return x;
  if (2 * std::fabs(d) <= kKneeDb) return x + (1 / r - 1) * (d + kKneeDb / 2) * (d + kKneeDb / 2) / (2 * kKneeDb);
  return t + d / r;
}

void Compressor::set(double threshold_db, double ratio, double attack_ms, double release_ms, double makeup_db) {
  threshold_ = threshold_db;
  ratio_ = std::max(1.0, ratio);
  makeup_ = makeup_db;
  aa_ = coef(attack_ms);
  ar_ = coef(release_ms);
}

void Compressor::process(const float* x, float* y, int n) {
  double gs = gs_;
  for (int i = 0; i < n; ++i) {
    const double v = x[i];
    const double level = 20.0 * std::log10(std::max(std::fabs(v), 1e-9));
    const double gc = static_curve_db(level, threshold_, ratio_) - level;
    gs = gc < gs ? aa_ * gs + (1 - aa_) * gc : ar_ * gs + (1 - ar_) * gc;
    y[i] = static_cast<float>(v * std::pow(10.0, (gs + makeup_) / 20.0));
  }
  gs_ = gs;
}

Limiter::Limiter() : ar_(coef(kLimiterReleaseMs)) { set(-1.0); }

void Limiter::set(double ceiling_db) { ceiling_ = std::pow(10.0, ceiling_db / 20.0); }

double Limiter::gr_db() const { return -20.0 * std::log10(std::max(g_, 1e-9)); }

void Limiter::process(const float* x, float* y, int n) {
  double g = g_;
  for (int i = 0; i < n; ++i) {
    const double v = x[i];
    const double t = std::min(1.0, ceiling_ / std::max(std::fabs(v), 1e-9));
    g = t < g ? t : ar_ * g + (1 - ar_) * t;
    g = std::min(g, t);
    y[i] = static_cast<float>(v * g);
  }
  g_ = g;
}

}  // namespace nf
