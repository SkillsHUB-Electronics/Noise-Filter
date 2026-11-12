// Realtime engine for Windows: WASAPI capture -> nf_pipeline -> WASAPI render.
//
// One MMCSS "Pro Audio" thread waits on both device events. Captured audio is
// converted to mono float 48 kHz, cut into 10 ms frames, processed, and queued
// for the render device (for example "CABLE Input" of VB-Cable). The output queue
// is kept near one frame; clock drift between two devices is absorbed by
// dropping or padding a few samples (counted as xruns).
#ifdef _WIN32

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <initguid.h>
#include <audioclient.h>
#include <avrt.h>
#include <mmdeviceapi.h>

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cmath>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include "nf/nf.h"

namespace {

constexpr int kRate = 48000;
// Defined here so MSVC and MinGW link the same way (ksmedia.h GUIDs need ksguid.lib on some toolchains).
const GUID kSubtypePcm = {0x00000001, 0x0000, 0x0010, {0x80, 0x00, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71}};
// PKEY_Device_FriendlyName (functiondiscoverykeys_devpkey.h needs extra headers on MSVC).
const PROPERTYKEY kFriendlyName = {{0xa45c254e, 0xdf1c, 0x4efd, {0x80, 0x20, 0x67, 0xd1, 0x46, 0xa8, 0x50, 0xe0}}, 14};
const GUID kSubtypeFloat = {0x00000003, 0x0000, 0x0010, {0x80, 0x00, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71}};
constexpr int kFrame = 480;

template <class T>
void release(T*& p) {
  if (p) {
    p->Release();
    p = nullptr;
  }
}

std::string narrow(const wchar_t* w) {
  if (!w) return {};
  int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr, nullptr);
  std::string s(n > 0 ? n - 1 : 0, '\0');
  if (n > 1) WideCharToMultiByte(CP_UTF8, 0, w, -1, &s[0], n, nullptr, nullptr);
  return s;
}

std::wstring widen(const char* s) {
  if (!s || !*s) return {};
  int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, nullptr, 0);
  std::wstring w(n > 0 ? n - 1 : 0, L'\0');
  if (n > 1) MultiByteToWideChar(CP_UTF8, 0, s, -1, &w[0], n);
  return w;
}

std::string hr_msg(const char* what, HRESULT hr) {
  char buf[160];
  std::snprintf(buf, sizeof(buf), "%s failed (HRESULT 0x%08lX)", what, static_cast<unsigned long>(hr));
  return buf;
}

struct ComScope {  // works whether the thread is already STA (Qt) or not
  HRESULT hr;
  ComScope() : hr(CoInitializeEx(nullptr, COINIT_MULTITHREADED)) {}
  ~ComScope() {
    if (SUCCEEDED(hr)) CoUninitialize();
  }
};

IMMDeviceEnumerator* make_enumerator() {
  IMMDeviceEnumerator* e = nullptr;
  CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator),
                   reinterpret_cast<void**>(&e));
  return e;
}

struct DevEntry {
  std::string id, name;
  bool is_default;
};

std::vector<DevEntry> enumerate(int kind) {
  std::vector<DevEntry> out;
  ComScope com;
  IMMDeviceEnumerator* en = make_enumerator();
  if (!en) return out;
  EDataFlow flow = kind == NF_INPUT ? eCapture : eRender;
  std::wstring def_id;
  IMMDevice* def = nullptr;
  if (SUCCEEDED(en->GetDefaultAudioEndpoint(flow, eConsole, &def))) {
    LPWSTR id = nullptr;
    if (SUCCEEDED(def->GetId(&id))) {
      def_id = id;
      CoTaskMemFree(id);
    }
    release(def);
  }
  IMMDeviceCollection* col = nullptr;
  if (SUCCEEDED(en->EnumAudioEndpoints(flow, DEVICE_STATE_ACTIVE, &col))) {
    UINT n = 0;
    col->GetCount(&n);
    for (UINT i = 0; i < n; ++i) {
      IMMDevice* d = nullptr;
      if (FAILED(col->Item(i, &d))) continue;
      DevEntry e;
      LPWSTR id = nullptr;
      if (SUCCEEDED(d->GetId(&id))) {
        e.id = narrow(id);
        e.is_default = def_id == id;
        CoTaskMemFree(id);
      }
      IPropertyStore* ps = nullptr;
      if (SUCCEEDED(d->OpenPropertyStore(STGM_READ, &ps))) {
        PROPVARIANT v;
        PropVariantInit(&v);
        if (SUCCEEDED(ps->GetValue(kFriendlyName, &v)) && v.vt == VT_LPWSTR) e.name = narrow(v.pwszVal);
        PropVariantClear(&v);
        release(ps);
      }
      out.push_back(e);
      release(d);
    }
    release(col);
  }
  release(en);
  return out;
}

enum class SampleType { F32, I16, I24, I32 };

// Simple single-thread FIFO of mono floats.
struct Fifo {
  std::vector<float> buf;
  size_t r = 0, w = 0;
  explicit Fifo(size_t cap = kRate) : buf(cap) {}
  size_t size() const { return w - r; }
  void push(const float* x, size_t n) {
    for (size_t i = 0; i < n; ++i) buf[(w + i) % buf.size()] = x[i];
    w += n;
    if (size() > buf.size()) r = w - buf.size();
  }
  void push_zeros(size_t n) {
    for (size_t i = 0; i < n; ++i) buf[(w + i) % buf.size()] = 0.0f;
    w += n;
    if (size() > buf.size()) r = w - buf.size();
  }
  size_t pop(float* x, size_t n) {
    n = std::min(n, size());
    for (size_t i = 0; i < n; ++i) x[i] = buf[(r + i) % buf.size()];
    r += n;
    return n;
  }
  void drop(size_t n) { r += std::min(n, size()); }
};

struct Endpoint {
  IMMDevice* dev = nullptr;
  IAudioClient* client = nullptr;
  IAudioCaptureClient* cap = nullptr;
  IAudioRenderClient* ren = nullptr;
  HANDLE event = nullptr;
  WAVEFORMATEXTENSIBLE fmt{};
  SampleType type = SampleType::F32;
  int channels = 1, bytes = 4;
  UINT32 buffer_frames = 0;
  bool exclusive = false;

  ~Endpoint() { close(); }
  void close() {
    if (client) client->Stop();
    release(cap);
    release(ren);
    release(client);
    release(dev);
    if (event) CloseHandle(event);
    event = nullptr;
  }
};

WAVEFORMATEXTENSIBLE make_format(int channels, SampleType t) {
  WAVEFORMATEXTENSIBLE f{};
  int bits = t == SampleType::I16 ? 16 : t == SampleType::I24 ? 24 : 32;
  f.Format.wFormatTag = WAVE_FORMAT_EXTENSIBLE;
  f.Format.nChannels = static_cast<WORD>(channels);
  f.Format.nSamplesPerSec = kRate;
  f.Format.wBitsPerSample = static_cast<WORD>(bits);
  f.Format.nBlockAlign = static_cast<WORD>(channels * bits / 8);
  f.Format.nAvgBytesPerSec = kRate * f.Format.nBlockAlign;
  f.Format.cbSize = sizeof(WAVEFORMATEXTENSIBLE) - sizeof(WAVEFORMATEX);
  f.Samples.wValidBitsPerSample = static_cast<WORD>(bits);
  f.dwChannelMask = channels == 1 ? SPEAKER_FRONT_CENTER : (SPEAKER_FRONT_LEFT | SPEAKER_FRONT_RIGHT);
  f.SubFormat = t == SampleType::F32 ? kSubtypeFloat : kSubtypePcm;
  return f;
}

std::string open_endpoint(Endpoint& ep, IMMDeviceEnumerator* en, const std::wstring& id, bool capture,
                          bool exclusive) {
  HRESULT hr;
  EDataFlow flow = capture ? eCapture : eRender;
  hr = id.empty() ? en->GetDefaultAudioEndpoint(flow, eConsole, &ep.dev) : en->GetDevice(id.c_str(), &ep.dev);
  if (FAILED(hr)) return hr_msg(capture ? "open input device" : "open output device", hr);
  ep.exclusive = exclusive;
  ep.event = CreateEventW(nullptr, FALSE, FALSE, nullptr);

  auto activate = [&]() {
    release(ep.client);
    return ep.dev->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, reinterpret_cast<void**>(&ep.client));
  };
  if (FAILED(hr = activate())) return hr_msg("IAudioClient activate", hr);

  if (!exclusive) {
    // Shared mode: let Windows convert to mono float 48 kHz for us.
    ep.fmt = make_format(1, SampleType::F32);
    DWORD flags = AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM |
                  AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY;
    hr = ep.client->Initialize(AUDCLNT_SHAREMODE_SHARED, flags, 0, 0,
                               reinterpret_cast<WAVEFORMATEX*>(&ep.fmt), nullptr);
    if (FAILED(hr)) return hr_msg("IAudioClient::Initialize (shared)", hr);
  } else {
    // Exclusive mode: pick a 48 kHz format the hardware accepts.
    const struct { int ch; SampleType t; } cands[] = {
        {1, SampleType::F32}, {2, SampleType::F32}, {1, SampleType::I16}, {2, SampleType::I16},
        {1, SampleType::I32}, {2, SampleType::I32}, {1, SampleType::I24}, {2, SampleType::I24}};
    bool found = false;
    for (auto& c : cands) {
      WAVEFORMATEXTENSIBLE f = make_format(c.ch, c.t);
      if (ep.client->IsFormatSupported(AUDCLNT_SHAREMODE_EXCLUSIVE, reinterpret_cast<WAVEFORMATEX*>(&f),
                                       nullptr) == S_OK) {
        ep.fmt = f;
        found = true;
        break;
      }
    }
    if (!found) return "device does not support 48 kHz in exclusive mode";
    REFERENCE_TIME def_period = 0, min_period = 0;
    ep.client->GetDevicePeriod(&def_period, &min_period);
    REFERENCE_TIME period = std::max<REFERENCE_TIME>(min_period, 30000);  // >= 3 ms
    DWORD flags = AUDCLNT_STREAMFLAGS_EVENTCALLBACK;
    hr = ep.client->Initialize(AUDCLNT_SHAREMODE_EXCLUSIVE, flags, period, period,
                               reinterpret_cast<WAVEFORMATEX*>(&ep.fmt), nullptr);
    if (hr == AUDCLNT_E_BUFFER_SIZE_NOT_ALIGNED) {
      UINT32 frames = 0;
      ep.client->GetBufferSize(&frames);
      period = static_cast<REFERENCE_TIME>(10000.0 * 1000 * frames / kRate + 0.5);
      if (FAILED(hr = activate())) return hr_msg("IAudioClient re-activate", hr);
      hr = ep.client->Initialize(AUDCLNT_SHAREMODE_EXCLUSIVE, flags, period, period,
                                 reinterpret_cast<WAVEFORMATEX*>(&ep.fmt), nullptr);
    }
    if (FAILED(hr)) return hr_msg("IAudioClient::Initialize (exclusive)", hr);
  }
  ep.channels = ep.fmt.Format.nChannels;
  ep.bytes = ep.fmt.Format.wBitsPerSample / 8;
  ep.type = IsEqualGUID(ep.fmt.SubFormat, kSubtypeFloat) ? SampleType::F32
            : ep.bytes == 2                                                ? SampleType::I16
            : ep.bytes == 3                                                ? SampleType::I24
                                                                           : SampleType::I32;
  if (FAILED(hr = ep.client->SetEventHandle(ep.event))) return hr_msg("SetEventHandle", hr);
  if (FAILED(hr = ep.client->GetBufferSize(&ep.buffer_frames))) return hr_msg("GetBufferSize", hr);
  if (capture)
    hr = ep.client->GetService(__uuidof(IAudioCaptureClient), reinterpret_cast<void**>(&ep.cap));
  else
    hr = ep.client->GetService(__uuidof(IAudioRenderClient), reinterpret_cast<void**>(&ep.ren));
  if (FAILED(hr)) return hr_msg("GetService", hr);
  return {};
}

float read_sample(const BYTE* p, SampleType t) {
  switch (t) {
    case SampleType::F32: { float v; std::memcpy(&v, p, 4); return v; }
    case SampleType::I16: { int16_t v; std::memcpy(&v, p, 2); return v / 32768.0f; }
    case SampleType::I24: { int32_t v = (p[0] << 8) | (p[1] << 16) | (p[2] << 24); return v / 2147483648.0f; }
    default: { int32_t v; std::memcpy(&v, p, 4); return v / 2147483648.0f; }
  }
}

void write_sample(BYTE* p, SampleType t, float x) {
  x = std::min(1.0f, std::max(-1.0f, x));
  switch (t) {
    case SampleType::F32: std::memcpy(p, &x, 4); break;
    case SampleType::I16: { int16_t v = static_cast<int16_t>(std::lrint(x * 32767.0f)); std::memcpy(p, &v, 2); break; }
    case SampleType::I24: { int32_t v = static_cast<int32_t>(std::lrint(x * 8388607.0f));
      p[0] = v & 0xFF; p[1] = (v >> 8) & 0xFF; p[2] = (v >> 16) & 0xFF; break; }
    default: { int32_t v = static_cast<int32_t>(std::lrint(static_cast<double>(x) * 2147483647.0)); std::memcpy(p, &v, 4); }
  }
}

}  // namespace

struct nf_engine {
  nf_pipeline* pipe;
  std::wstring in_id, out_id;
  bool exclusive;
  std::thread th;
  HANDLE stop_event = nullptr;
  std::atomic<bool> running{false};
  std::atomic<long long> frames{0}, xruns{0};
  std::atomic<float> dsp_avg_us{0}, dsp_max_us{0}, latency_ms{0};

  void run(HANDLE ready, std::string* err);
};

void nf_engine::run(HANDLE ready, std::string* err) {
  ComScope com;
  DWORD task_idx = 0;
  HANDLE mmcss = AvSetMmThreadCharacteristicsW(L"Pro Audio", &task_idx);
  if (mmcss) AvSetMmThreadPriority(mmcss, AVRT_PRIORITY_HIGH);

  Endpoint in, out;
  IMMDeviceEnumerator* en = make_enumerator();
  if (!en) *err = "cannot create device enumerator";
  if (err->empty()) *err = open_endpoint(in, en, in_id, true, exclusive);
  if (err->empty()) *err = open_endpoint(out, en, out_id, false, exclusive);
  release(en);

  Fifo infifo, outfifo;
  std::vector<float> frame_in(kFrame), frame_out(kFrame), tmp(kRate);
  LARGE_INTEGER qpf;
  QueryPerformanceFrequency(&qpf);
  REFERENCE_TIME in_lat = 0, out_lat = 0;

  if (err->empty()) {
    // Prime the render buffer with silence, then start both streams.
    BYTE* data = nullptr;
    if (SUCCEEDED(out.ren->GetBuffer(out.buffer_frames, &data)))
      out.ren->ReleaseBuffer(out.buffer_frames, AUDCLNT_BUFFERFLAGS_SILENT);
    in.client->GetStreamLatency(&in_lat);
    out.client->GetStreamLatency(&out_lat);
    HRESULT hr = in.client->Start();
    if (SUCCEEDED(hr)) hr = out.client->Start();
    if (FAILED(hr)) *err = hr_msg("IAudioClient::Start", hr);
  }
  const bool ok = err->empty();
  running = ok;
  SetEvent(ready);  // err/running are now visible to nf_engine_start
  if (!ok) {
    if (mmcss) AvRevertMmThreadCharacteristics(mmcss);
    return;
  }

  const size_t target = kFrame;          // keep ~1 frame queued for the output
  const size_t high = 4 * kFrame;        // above this, drop back to target (drift)
  bool primed = false;
  double avg = 0.0, mx = 0.0;
  HANDLE waits[3] = {stop_event, in.event, out.event};

  for (;;) {
    DWORD w = WaitForMultipleObjects(3, waits, FALSE, 500);
    if (w == WAIT_OBJECT_0) break;
    if (w == WAIT_TIMEOUT) {  // device stalled or unplugged
      xruns++;
      continue;
    }
    if (w == WAIT_OBJECT_0 + 1) {
      UINT32 pkt = 0;
      while (SUCCEEDED(in.cap->GetNextPacketSize(&pkt)) && pkt > 0) {
        BYTE* data = nullptr;
        UINT32 n = 0;
        DWORD flags = 0;
        if (FAILED(in.cap->GetBuffer(&data, &n, &flags, nullptr, nullptr))) break;
        if (flags & AUDCLNT_BUFFERFLAGS_DATA_DISCONTINUITY) xruns++;
        n = std::min<UINT32>(n, static_cast<UINT32>(tmp.size()));
        if (flags & AUDCLNT_BUFFERFLAGS_SILENT) {
          std::fill(tmp.begin(), tmp.begin() + n, 0.0f);
        } else {
          const int stride = in.channels * in.bytes;
          for (UINT32 i = 0; i < n; ++i) {
            float acc = 0.0f;
            for (int c = 0; c < in.channels; ++c) acc += read_sample(data + i * stride + c * in.bytes, in.type);
            tmp[i] = acc / in.channels;
          }
        }
        in.cap->ReleaseBuffer(n);
        infifo.push(tmp.data(), n);
      }
      while (infifo.size() >= kFrame) {
        infifo.pop(frame_in.data(), kFrame);
        LARGE_INTEGER t0, t1;
        QueryPerformanceCounter(&t0);
        nf_pipeline_process(pipe, frame_in.data(), frame_out.data());
        QueryPerformanceCounter(&t1);
        const double us = 1e6 * static_cast<double>(t1.QuadPart - t0.QuadPart) / qpf.QuadPart;
        avg = avg == 0.0 ? us : 0.99 * avg + 0.01 * us;
        mx = std::max(mx, us);
        dsp_avg_us = static_cast<float>(avg);
        dsp_max_us = static_cast<float>(mx);
        frames++;
        outfifo.push(frame_out.data(), kFrame);
      }
      if (outfifo.size() > high + out.buffer_frames) {
        outfifo.drop(outfifo.size() - target);
        xruns++;
      }
    }
    if (w == WAIT_OBJECT_0 + 2) {
      UINT32 avail = out.buffer_frames;
      UINT32 padding = 0;
      if (!out.exclusive) {
        out.client->GetCurrentPadding(&padding);
        avail = out.buffer_frames - padding;
      }
      if (avail == 0) continue;
      BYTE* data = nullptr;
      if (FAILED(out.ren->GetBuffer(avail, &data))) continue;
      if (!primed && outfifo.size() >= target) primed = true;
      size_t got = 0;
      if (primed) {
        got = outfifo.pop(tmp.data(), avail);
        if (got < avail) {
          xruns++;
          primed = false;  // wait for a full frame again before resuming
        }
      }
      std::fill(tmp.begin() + got, tmp.begin() + avail, 0.0f);
      const int stride = out.channels * out.bytes;
      for (UINT32 i = 0; i < avail; ++i)
        for (int c = 0; c < out.channels; ++c) write_sample(data + i * stride + c * out.bytes, out.type, tmp[i]);
      out.ren->ReleaseBuffer(avail, 0);
      latency_ms = static_cast<float>((in_lat + out_lat) / 10000.0 +
                                      1000.0 * (outfifo.size() + padding + kFrame) / kRate);
    }
  }
  in.close();
  out.close();
  running = false;
  if (mmcss) AvRevertMmThreadCharacteristics(mmcss);
}

extern "C" {

int nf_device_count(int kind) { return static_cast<int>(enumerate(kind).size()); }

int nf_device_get(int kind, int index, nf_device_info* info) {
  auto list = enumerate(kind);
  if (index < 0 || index >= static_cast<int>(list.size()) || !info) return -1;
  std::memset(info, 0, sizeof(*info));
  std::strncpy(info->id, list[index].id.c_str(), sizeof(info->id) - 1);
  std::strncpy(info->name, list[index].name.c_str(), sizeof(info->name) - 1);
  info->is_default = list[index].is_default;
  return 0;
}

nf_engine* nf_engine_create(nf_pipeline* p, const char* in_id, const char* out_id, int exclusive, char* err,
                            int err_len) {
  if (!p) {
    if (err && err_len > 0) std::snprintf(err, err_len, "pipeline is NULL");
    return nullptr;
  }
  nf_engine* e = new nf_engine();
  e->pipe = p;
  e->in_id = widen(in_id);
  e->out_id = widen(out_id);
  e->exclusive = exclusive != 0;
  e->stop_event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
  return e;
}

int nf_engine_start(nf_engine* e, char* err, int err_len) {
  if (e->running) return 0;
  if (e->th.joinable()) e->th.join();
  ResetEvent(e->stop_event);
  e->frames = 0;
  e->xruns = 0;
  e->dsp_max_us = 0;
  HANDLE ready = CreateEventW(nullptr, TRUE, FALSE, nullptr);
  std::string msg;
  e->th = std::thread([e, ready, &msg] { e->run(ready, &msg); });
  WaitForSingleObject(ready, INFINITE);
  CloseHandle(ready);
  if (!msg.empty()) {
    e->th.join();
    if (err && err_len > 0) std::snprintf(err, err_len, "%s", msg.c_str());
    return -1;
  }
  return 0;
}

void nf_engine_stop(nf_engine* e) {
  if (!e) return;
  SetEvent(e->stop_event);
  if (e->th.joinable()) e->th.join();
}

void nf_engine_destroy(nf_engine* e) {
  if (!e) return;
  nf_engine_stop(e);
  CloseHandle(e->stop_event);
  delete e;
}

void nf_engine_get_stats(nf_engine* e, nf_engine_stats* s) {
  s->frames = e->frames;
  s->xruns = e->xruns;
  s->dsp_avg_us = e->dsp_avg_us;
  s->dsp_max_us = e->dsp_max_us;
  s->latency_ms = e->latency_ms;
}

}  // extern "C"

#endif  // _WIN32
