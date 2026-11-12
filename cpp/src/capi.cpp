// C API wrapper around nf::Pipeline with lock-free-for-the-audio-thread control.
#include <algorithm>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "core.hpp"
#include "nf/nf.h"
#include "onnx_denoiser.hpp"

using namespace nf;

namespace {

Config to_cpp(const nf_config& c) {
  Config o;
  o.bypass = c.bypass != 0;
  o.highpass_hz = c.highpass_hz;
  o.denoise = static_cast<DenoiseMode>(std::min(2, std::max(0, c.denoise)));
  o.strength = c.strength;
  o.gate_enabled = c.gate_enabled != 0;
  o.gate_threshold_db = c.gate_threshold_db;
  o.output_gain_db = c.output_gain_db;
  return o;
}

nf_config to_c(const Config& c) {
  nf_config o;
  o.bypass = c.bypass;
  o.highpass_hz = c.highpass_hz;
  o.denoise = static_cast<int>(c.denoise);
  o.strength = c.strength;
  o.gate_enabled = c.gate_enabled;
  o.gate_threshold_db = c.gate_threshold_db;
  o.output_gain_db = c.output_gain_db;
  return o;
}

void set_err(char* err, int len, const std::string& msg) {
  if (!err || len <= 0) return;
  size_t n = std::min(static_cast<size_t>(len - 1), msg.size());
  std::memcpy(err, msg.data(), n);
  err[n] = '\0';
}

}  // namespace

struct nf_pipeline {
  explicit nf_pipeline(const Config& c) : pipe(c), ui_cfg(c), pending_cfg(c) {
    pending_profile.assign(kSpectralBins, 0.0f);
    profile_copy.assign(kSpectralBins, 0.0f);
  }
  ~nf_pipeline() {
    delete pending_onnx;
    delete retired_onnx;
  }

  Pipeline pipe;  // audio thread only

  // ---- control, guarded by ctl (audio thread only ever try_locks) ----
  std::mutex ctl;
  Config ui_cfg;  // what the UI last set
  Config pending_cfg;
  bool cfg_dirty = false, learn_start = false, learn_finish = false, clear_profile = false;
  bool profile_dirty = false, spectral_dirty = false;
  float sp_floor = 0.08f, sp_smoothing = 0.6f, sp_rise = 0.003f;
  std::vector<float> pending_profile;
  OnnxDenoiser* pending_onnx = nullptr;  // loaded on the UI thread, swapped in on the audio thread
  OnnxDenoiser* retired_onnx = nullptr;  // freed on the UI thread
  std::vector<float> profile_copy;
  bool has_profile = false;

  // ---- analyzers, guarded by ana ----
  std::mutex ana;
  SpectrumAnalyzer in_ana, out_ana;
  SpectrumView in_view, out_view;

  void apply_pending() {  // audio thread, ctl held
    if (cfg_dirty) {
      pipe.update(pending_cfg);
      cfg_dirty = false;
    }
    if (spectral_dirty) {
      pipe.spectral().floor = sp_floor;
      pipe.spectral().smoothing = sp_smoothing;
      pipe.spectral().rise = sp_rise;
      spectral_dirty = false;
    }
    if (pending_onnx) {
      OnnxDenoiser* old = pipe.exchange_onnx(pending_onnx);
      pending_onnx = nullptr;
      if (old) {
        delete retired_onnx;  // rare; only if UI loaded twice before freeing
        retired_onnx = old;
      }
    }
    if (clear_profile) {
      pipe.spectral().clear_profile();
      has_profile = false;
      clear_profile = false;
    }
    if (profile_dirty) {
      pipe.spectral().set_profile(pending_profile.data());
      profile_copy = pending_profile;
      has_profile = true;
      profile_dirty = false;
    }
    if (learn_start) {
      pipe.spectral().start_learning();
      learn_start = false;
    }
    if (learn_finish) {
      pipe.spectral().finish_learning();
      if (pipe.spectral().has_profile()) {
        profile_copy = pipe.spectral().profile();
        has_profile = true;
      }
      learn_finish = false;
    }
  }
};

extern "C" {

int nf_api_version(void) { return NF_API_VERSION; }
int nf_sample_rate(void) { return kSampleRate; }
int nf_frame_size(void) { return kFrameSize; }
int nf_analyzer_bins(void) { return kAnalyzerBins; }
int nf_profile_bins(void) { return kSpectralBins; }
int nf_has_onnx(void) {
#ifdef NF_WITH_ONNX
  return 1;
#else
  return 0;
#endif
}

void nf_default_config(nf_config* cfg) {
  if (cfg) *cfg = to_c(Config());
}

nf_pipeline* nf_pipeline_create(const nf_config* cfg) {
  try {
    return new nf_pipeline(cfg ? to_cpp(*cfg) : Config());
  } catch (...) {
    return nullptr;
  }
}

void nf_pipeline_destroy(nf_pipeline* p) { delete p; }

void nf_pipeline_set_config(nf_pipeline* p, const nf_config* cfg) {
  std::lock_guard<std::mutex> g(p->ctl);
  p->ui_cfg = p->pending_cfg = to_cpp(*cfg);
  p->cfg_dirty = true;
}

void nf_pipeline_get_config(nf_pipeline* p, nf_config* cfg) {
  std::lock_guard<std::mutex> g(p->ctl);
  *cfg = to_c(p->ui_cfg);
}

void nf_pipeline_set_spectral_params(nf_pipeline* p, float floor, float smoothing, float rise) {
  std::lock_guard<std::mutex> g(p->ctl);
  p->sp_floor = floor;
  p->sp_smoothing = smoothing;
  p->sp_rise = rise;
  p->spectral_dirty = true;
}

int nf_pipeline_load_onnx(nf_pipeline* p, const char* path, char* err, int err_len) {
  std::string msg;
  OnnxDenoiser* d = OnnxDenoiser::load(path ? path : "", 1, &msg);  // slow: outside the lock
  if (!d) {
    set_err(err, err_len, msg);
    return -1;
  }
  OnnxDenoiser* to_free[2] = {nullptr, nullptr};
  {
    std::lock_guard<std::mutex> g(p->ctl);
    to_free[0] = p->pending_onnx;  // never picked up: replace
    to_free[1] = p->retired_onnx;
    p->pending_onnx = d;
    p->retired_onnx = nullptr;
  }
  delete to_free[0];
  delete to_free[1];
  return 0;
}

int nf_pipeline_process(nf_pipeline* p, const float* in, float* out) {
  if (p->ctl.try_lock()) {  // never block the audio thread
    p->apply_pending();
    p->ctl.unlock();
  }
  // The analyzers need the input after `out` may have overwritten it (in == out).
  float in_copy[kFrameSize];
  std::memcpy(in_copy, in, sizeof(in_copy));
  p->pipe.process(in_copy, out);
  if (p->ana.try_lock()) {
    p->in_ana.push(in_copy, kFrameSize);
    p->out_ana.push(out, kFrameSize);
    p->ana.unlock();
  }
  return 0;
}

void nf_pipeline_learn_start(nf_pipeline* p) {
  std::lock_guard<std::mutex> g(p->ctl);
  p->learn_start = true;
  p->learn_finish = false;
}

void nf_pipeline_learn_finish(nf_pipeline* p) {
  std::lock_guard<std::mutex> g(p->ctl);
  p->learn_finish = true;
}

void nf_pipeline_clear_profile(nf_pipeline* p) {
  std::lock_guard<std::mutex> g(p->ctl);
  p->clear_profile = true;
  p->profile_dirty = false;
}

int nf_pipeline_get_profile(nf_pipeline* p, float* out) {
  std::lock_guard<std::mutex> g(p->ctl);
  if (out) std::copy(p->profile_copy.begin(), p->profile_copy.end(), out);
  return p->has_profile ? 1 : 0;
}

void nf_pipeline_set_profile(nf_pipeline* p, const float* profile) {
  std::lock_guard<std::mutex> g(p->ctl);
  std::copy(profile, profile + kSpectralBins, p->pending_profile.begin());
  p->profile_dirty = true;
  p->clear_profile = false;
}

void nf_pipeline_spectrum_db(nf_pipeline* p, int which, float* db_out) {
  std::vector<float> snap(kAnalyzerSize);
  {
    std::lock_guard<std::mutex> g(p->ana);  // short: copy only, FFT runs outside the lock
    (which == NF_OUTPUT ? p->out_ana : p->in_ana).snapshot(snap.data());
  }
  (which == NF_OUTPUT ? p->out_view : p->in_view).update(snap.data(), db_out);  // UI thread state
}

float nf_pipeline_level_db(nf_pipeline* p, int which) {
  std::vector<float> snap(kAnalyzerSize);
  {
    std::lock_guard<std::mutex> g(p->ana);
    (which == NF_OUTPUT ? p->out_ana : p->in_ana).snapshot(snap.data());
  }
  return SpectrumAnalyzer::level_db(snap.data());
}

}  // extern "C"
