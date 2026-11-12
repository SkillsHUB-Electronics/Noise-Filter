#pragma once
#include <string>
#include <vector>

#include "core.hpp"

namespace nf {

// ONNX neural denoiser (CPU). Same model contract as noise_filter/core/denoiser_onnx.py:
//   input "frame" float32 [1, kFrameSize] -> output "frame_out" float32 ("frame" accepted for older models) [1, kFrameSize]
//   recurrent state: inputs named "state*" are fed from outputs named "state*" (paired in order).
class OnnxDenoiser {
 public:
  // Returns nullptr and sets err when ONNX support is missing or the model is invalid.
  static OnnxDenoiser* load(const std::string& utf8_path, int threads, std::string* err);
  virtual ~OnnxDenoiser() = default;
  virtual void process(const float* x, float* y) = 0;
};

}  // namespace nf
