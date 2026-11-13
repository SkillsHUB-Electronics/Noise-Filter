// Parametric EQ: 1:1 port of noise_filter/core/eq.py (RBJ cookbook biquads,
// Butterworth cascades for steep low/high-pass), float64 coefficients and state.
#include <algorithm>
#include <cmath>
#include <cstring>

#include "core.hpp"

namespace nf {

namespace {
constexpr double kPi = 3.14159265358979323846;

double clampd(double v, double lo, double hi) { return std::min(hi, std::max(lo, v)); }

int nearest_slope(int s) {
  static const int slopes[] = {12, 24, 36, 48};
  int best = 12;
  for (int c : slopes)
    if (std::abs(c - s) < std::abs(best - s)) best = c;
  return best;
}
}  // namespace

int Equalizer::design(const EqBand& in, int fs, double out[][5]) {
  if (!in.on) return 0;
  const EqType t = in.type;
  const double freq = clampd(in.freq_hz, 20.0, 20000.0);
  const double gain = clampd(in.gain_db, -24.0, 24.0);
  const double qin = clampd(in.q, 0.1, 18.0);
  const double f0 = std::min(freq, 0.45 * fs);
  const double w0 = 2.0 * kPi * f0 / fs;
  const double cosw = std::cos(w0), sinw = std::sin(w0);
  const double A = std::pow(10.0, gain / 40.0);

  auto section = [&](double q, double* o) {
    const double alpha = sinw / (2.0 * q);
    double c[6];
    switch (t) {
      case EqType::Peak:
        c[0] = 1 + alpha * A; c[1] = -2 * cosw; c[2] = 1 - alpha * A;
        c[3] = 1 + alpha / A; c[4] = -2 * cosw; c[5] = 1 - alpha / A;
        break;
      case EqType::LowShelf: {
        const double sa = 2.0 * std::sqrt(A) * alpha;
        c[0] = A * ((A + 1) - (A - 1) * cosw + sa); c[1] = 2 * A * ((A - 1) - (A + 1) * cosw);
        c[2] = A * ((A + 1) - (A - 1) * cosw - sa);
        c[3] = (A + 1) + (A - 1) * cosw + sa; c[4] = -2 * ((A - 1) + (A + 1) * cosw);
        c[5] = (A + 1) + (A - 1) * cosw - sa;
        break;
      }
      case EqType::HighShelf: {
        const double sa = 2.0 * std::sqrt(A) * alpha;
        c[0] = A * ((A + 1) + (A - 1) * cosw + sa); c[1] = -2 * A * ((A - 1) + (A + 1) * cosw);
        c[2] = A * ((A + 1) + (A - 1) * cosw - sa);
        c[3] = (A + 1) - (A - 1) * cosw + sa; c[4] = 2 * ((A - 1) - (A + 1) * cosw);
        c[5] = (A + 1) - (A - 1) * cosw - sa;
        break;
      }
      case EqType::LowPass:
        c[0] = (1 - cosw) / 2; c[1] = 1 - cosw; c[2] = (1 - cosw) / 2;
        c[3] = 1 + alpha; c[4] = -2 * cosw; c[5] = 1 - alpha;
        break;
      case EqType::HighPass:
        c[0] = (1 + cosw) / 2; c[1] = -(1 + cosw); c[2] = (1 + cosw) / 2;
        c[3] = 1 + alpha; c[4] = -2 * cosw; c[5] = 1 - alpha;
        break;
      case EqType::BandPass:  // constant 0 dB peak gain
        c[0] = alpha; c[1] = 0.0; c[2] = -alpha;
        c[3] = 1 + alpha; c[4] = -2 * cosw; c[5] = 1 - alpha;
        break;
      default:  // Notch
        c[0] = 1.0; c[1] = -2 * cosw; c[2] = 1.0;
        c[3] = 1 + alpha; c[4] = -2 * cosw; c[5] = 1 - alpha;
        break;
    }
    const double a0 = c[3];
    o[0] = c[0] / a0; o[1] = c[1] / a0; o[2] = c[2] / a0; o[3] = c[4] / a0; o[4] = c[5] / a0;
  };

  if (t == EqType::LowPass || t == EqType::HighPass) {
    const int order = nearest_slope(in.slope_db) / 6;
    if (order == 2) {  // 12 dB/oct keeps the user's Q (resonance)
      section(qin, out[0]);
      return 1;
    }
    for (int k = 0; k < order / 2; ++k)
      section(1.0 / (2.0 * std::cos(kPi * (2 * k + 1) / (2.0 * order))), out[k]);
    return order / 2;
  }
  section(qin, out[0]);
  return 1;
}

void Equalizer::set(bool enabled, const EqBand* bands, int count) {
  count = std::max(0, std::min(count, kEqMaxBands));
  double sos[kEqMaxBands * kEqMaxSectionsPerBand][5];
  double z[kEqMaxBands * kEqMaxSectionsPerBand][2];
  int layout[kEqMaxBands] = {};
  int n = 0, j = 0;
  for (int k = 0; k < count; ++k) {
    layout[k] = design(bands[k], kSampleRate, sos + n);
    const bool keep = k < nbands_ && layout_[k] == layout[k];  // same shape: no click
    for (int s = 0; s < layout[k]; ++s) {
      z[n + s][0] = keep ? z_[j + s][0] : 0.0;
      z[n + s][1] = keep ? z_[j + s][1] : 0.0;
    }
    n += layout[k];
    j += k < nbands_ ? layout_[k] : 0;
  }
  std::memcpy(sos_, sos, sizeof(double) * 5 * n);
  std::memcpy(z_, z, sizeof(double) * 2 * n);
  std::memcpy(layout_, layout, sizeof(layout));
  nbands_ = count;
  nsec_ = n;
  enabled_ = enabled;
}

void Equalizer::process(const float* x, float* y, int n) {
  if (y != x) std::copy(x, x + n, y);
  for (int s = 0; s < nsec_; ++s) {  // direct form II transposed, section by section
    const double b0 = sos_[s][0], b1 = sos_[s][1], b2 = sos_[s][2], a1 = sos_[s][3], a2 = sos_[s][4];
    double z0 = z_[s][0], z1 = z_[s][1];
    for (int i = 0; i < n; ++i) {
      const double v = y[i];
      const double o = b0 * v + z0;
      z0 = b1 * v - a1 * o + z1;
      z1 = b2 * v - a2 * o;
      y[i] = static_cast<float>(o);
    }
    z_[s][0] = z0;
    z_[s][1] = z1;
  }
}

}  // namespace nf
