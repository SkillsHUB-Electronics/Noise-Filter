#include <algorithm>
#include <cmath>

#include "core.hpp"
#include "onnx_denoiser.hpp"

namespace nf {

Pipeline::Pipeline(const Config& cfg)
    : cfg_(cfg),
      hp_(cfg.highpass_hz > 0 ? cfg.highpass_hz : 80.0),
      gate_(cfg.gate_threshold_db),
      spectral_(cfg.strength),
      a_(kFrameSize),
      b_(kFrameSize) {
  comp_.set(cfg.comp_threshold_db, cfg.comp_ratio, cfg.comp_attack_ms, cfg.comp_release_ms, cfg.comp_makeup_db);
  limiter_.set(cfg.limiter_ceiling_db);
}

Pipeline::~Pipeline() = default;

void Pipeline::update(const Config& c) {
  if (c.highpass_hz != cfg_.highpass_hz && c.highpass_hz > 0) hp_ = HighPass(c.highpass_hz);
  if (c.strength != cfg_.strength) spectral_.strength = c.strength;
  if (c.gate_threshold_db != cfg_.gate_threshold_db) gate_.set_threshold_db(c.gate_threshold_db);
  if (c.comp_threshold_db != cfg_.comp_threshold_db || c.comp_ratio != cfg_.comp_ratio ||
      c.comp_attack_ms != cfg_.comp_attack_ms || c.comp_release_ms != cfg_.comp_release_ms ||
      c.comp_makeup_db != cfg_.comp_makeup_db)
    comp_.set(c.comp_threshold_db, c.comp_ratio, c.comp_attack_ms, c.comp_release_ms, c.comp_makeup_db);
  if (c.limiter_ceiling_db != cfg_.limiter_ceiling_db) limiter_.set(c.limiter_ceiling_db);
  cfg_ = c;
}

bool Pipeline::load_onnx(const std::string& path, std::string* err) {
  OnnxDenoiser* d = OnnxDenoiser::load(path, 1, err);
  if (!d) return false;
  onnx_.reset(d);
  return true;
}

OnnxDenoiser* Pipeline::exchange_onnx(OnnxDenoiser* d) {
  OnnxDenoiser* old = onnx_.release();
  onnx_.reset(d);
  return old;
}

void Pipeline::process(const float* in, float* out) {
  float* a = a_.data();
  float* b = b_.data();
  std::copy(in, in + kFrameSize, a);
  in_analyzer.push(a, kFrameSize);
  if (!cfg_.bypass) {
    if (cfg_.highpass_hz > 0) {
      hp_.process(a, b, kFrameSize);
      std::swap(a, b);
    }
    if (cfg_.denoise == DenoiseMode::Spectral) {
      spectral_.process(a, b);
      std::swap(a, b);
    } else if (cfg_.denoise == DenoiseMode::Onnx && onnx_) {
      onnx_->process(a, b);
      std::swap(a, b);
    }
    if (eq_.active()) {  // after denoising, so boosted bands do not lift the noise first
      eq_.process(a, b, kFrameSize);
      std::swap(a, b);
    }
    if (cfg_.gate_enabled) {
      gate_.process(a, b, kFrameSize);
      std::swap(a, b);
    }
    if (cfg_.comp_enabled) {
      comp_.process(a, b, kFrameSize);
      std::swap(a, b);
    }
    const float g = static_cast<float>(std::pow(10.0, cfg_.output_gain_db / 20.0));
    for (int i = 0; i < kFrameSize; ++i) a[i] *= g;
    if (cfg_.limiter_enabled) {
      limiter_.process(a, b, kFrameSize);
      std::swap(a, b);
    }
  }
  for (int i = 0; i < kFrameSize; ++i) out[i] = std::min(1.0f, std::max(-1.0f, a[i]));
  out_analyzer.push(out, kFrameSize);
}

}  // namespace nf
