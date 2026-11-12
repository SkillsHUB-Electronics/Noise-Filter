#include "onnx_denoiser.hpp"

#ifndef NF_WITH_ONNX

namespace nf {
OnnxDenoiser* OnnxDenoiser::load(const std::string&, int, std::string* err) {
  if (err) *err = "nf-core was built without ONNX Runtime (configure with -DNF_WITH_ONNX=ON)";
  return nullptr;
}
}  // namespace nf

#else

#include <onnxruntime_cxx_api.h>

#include <algorithm>
#include <cstring>
#include <memory>

#ifdef _WIN32
#include <windows.h>
#endif

namespace nf {
namespace {

Ort::Env& env() {
  static Ort::Env e(ORT_LOGGING_LEVEL_WARNING, "nf-core");
  return e;
}

#ifdef _WIN32
std::wstring widen(const std::string& s) {
  int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, nullptr, 0);
  std::wstring w(n > 0 ? n - 1 : 0, L'\0');
  if (n > 1) MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, &w[0], n);
  return w;
}
#endif

struct Tensor {
  std::string name;
  std::vector<int64_t> shape;
  std::vector<float> data;
};

class OrtDenoiser final : public OnnxDenoiser {
 public:
  OrtDenoiser(const std::string& path, int threads) {
    Ort::SessionOptions opts;
    opts.SetIntraOpNumThreads(threads);
    opts.SetInterOpNumThreads(1);
    opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
#ifdef _WIN32
    session_ = std::make_unique<Ort::Session>(env(), widen(path).c_str(), opts);
#else
    session_ = std::make_unique<Ort::Session>(env(), path.c_str(), opts);
#endif
    Ort::AllocatorWithDefaultOptions alloc;
    bool has_frame_in = false;
    std::string frame_out_name;
    for (size_t i = 0; i < session_->GetInputCount(); ++i) {
      std::string name = session_->GetInputNameAllocated(i, alloc).get();
      auto shape = session_->GetInputTypeInfo(i).GetTensorTypeAndShapeInfo().GetShape();
      if (name == "frame") {
        has_frame_in = true;
      } else if (name.rfind("state", 0) == 0) {
        for (auto& d : shape) d = d > 0 ? d : 1;
        size_t count = 1;
        for (auto d : shape) count *= static_cast<size_t>(d);
        state_in_.push_back({name, shape, std::vector<float>(count, 0.0f)});
      } else {
        throw std::runtime_error("unexpected model input: " + name);
      }
    }
    for (size_t i = 0; i < session_->GetOutputCount(); ++i) {
      std::string name = session_->GetOutputNameAllocated(i, alloc).get();
      if (name == "frame_out" || (name == "frame" && frame_out_name.empty())) frame_out_name = name;
      else if (name.rfind("state", 0) == 0) state_out_.push_back({name, {}, {}});
    }
    if (!has_frame_in || frame_out_name.empty())
      throw std::runtime_error("model needs an input named 'frame' and an output named 'frame_out'");
    if (state_in_.size() != state_out_.size()) throw std::runtime_error("state inputs/outputs count mismatch");
    for (size_t i = 0; i < state_out_.size(); ++i) {
      state_out_[i].shape = state_in_[i].shape;
      state_out_[i].data.assign(state_in_[i].data.size(), 0.0f);
    }

    frame_in_.assign(kFrameSize, 0.0f);
    frame_out_.assign(kFrameSize, 0.0f);
    auto mem = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    const int64_t fshape[2] = {1, kFrameSize};
    in_names_.push_back("frame");
    in_vals_.push_back(Ort::Value::CreateTensor<float>(mem, frame_in_.data(), kFrameSize, fshape, 2));
    for (auto& t : state_in_) {
      in_names_.push_back(t.name.c_str());
      in_vals_.push_back(Ort::Value::CreateTensor<float>(mem, t.data.data(), t.data.size(), t.shape.data(), t.shape.size()));
    }
    out_name_ = frame_out_name;
    out_names_.push_back(out_name_.c_str());
    out_vals_.push_back(Ort::Value::CreateTensor<float>(mem, frame_out_.data(), kFrameSize, fshape, 2));
    for (auto& t : state_out_) {
      out_names_.push_back(t.name.c_str());
      out_vals_.push_back(Ort::Value::CreateTensor<float>(mem, t.data.data(), t.data.size(), t.shape.data(), t.shape.size()));
    }
  }

  void process(const float* x, float* y) override {
    std::memcpy(frame_in_.data(), x, sizeof(float) * kFrameSize);
    session_->Run(run_opts_, in_names_.data(), in_vals_.data(), in_vals_.size(), out_names_.data(),
                  out_vals_.data(), out_vals_.size());
    for (size_t i = 0; i < state_in_.size(); ++i) state_in_[i].data = state_out_[i].data;  // same size: no realloc
    std::memcpy(y, frame_out_.data(), sizeof(float) * kFrameSize);
  }

 private:
  std::unique_ptr<Ort::Session> session_;
  std::string out_name_;
  Ort::RunOptions run_opts_;
  std::vector<Tensor> state_in_, state_out_;
  std::vector<float> frame_in_, frame_out_;
  std::vector<const char*> in_names_, out_names_;
  std::vector<Ort::Value> in_vals_, out_vals_;
};

}  // namespace

OnnxDenoiser* OnnxDenoiser::load(const std::string& path, int threads, std::string* err) {
  try {
    return new OrtDenoiser(path, threads);
  } catch (const std::exception& e) {
    if (err) *err = e.what();
    return nullptr;
  }
}

}  // namespace nf

#endif
