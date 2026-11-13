/* nf-core public C API.
 *
 * Stable ABI used by every front end: the Python/PySide6 app (ctypes), the
 * CLI, and later Flutter (dart:ffi) on Windows, Android and iOS.
 *
 * Threading: nf_pipeline_process() is called from ONE audio thread. Every other
 * function may be called from any other thread (UI) at the same time; settings
 * changes are handed to the audio thread without ever blocking it.
 */
#ifndef NF_H
#define NF_H

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32)
#if defined(NF_BUILD_SHARED)
#define NF_API __declspec(dllexport)
#elif defined(NF_USE_SHARED)
#define NF_API __declspec(dllimport)
#else
#define NF_API
#endif
#else
#define NF_API __attribute__((visibility("default")))
#endif

#define NF_API_VERSION 2 /* 2: parametric EQ, compressor, limiter */

enum { NF_DENOISE_OFF = 0, NF_DENOISE_SPECTRAL = 1, NF_DENOISE_ONNX = 2 };
enum { NF_INPUT = 0, NF_OUTPUT = 1 };

typedef struct nf_config {
  int bypass;
  float highpass_hz; /* <= 0 disables */
  int denoise;       /* NF_DENOISE_* */
  float strength;
  int gate_enabled;
  float gate_threshold_db;
  float output_gain_db;
  /* v2: dynamics, after the gate (compressor) and after the output gain (limiter) */
  int comp_enabled;
  float comp_threshold_db; /* -60..0 */
  float comp_ratio;        /* 1..20 */
  float comp_attack_ms;
  float comp_release_ms;
  float comp_makeup_db;
  int limiter_enabled;
  float limiter_ceiling_db; /* e.g. -1: output never exceeds it, no look-ahead delay */
} nf_config;

/* Parametric EQ band (applied after the denoiser). */
enum {
  NF_EQ_PEAK = 0, NF_EQ_LOWSHELF = 1, NF_EQ_HIGHSHELF = 2, NF_EQ_LOWPASS = 3,
  NF_EQ_HIGHPASS = 4, NF_EQ_BANDPASS = 5, NF_EQ_NOTCH = 6
};
#define NF_EQ_MAX_BANDS 8

typedef struct nf_eq_band {
  int type;      /* NF_EQ_* */
  int on;
  float freq_hz; /* 20..20000 */
  float gain_db; /* -24..24, peak and shelf types */
  float q;       /* 0.1..18 */
  int slope_db;  /* low/high-pass: 12, 24, 36, 48 dB/octave (Butterworth) */
} nf_eq_band;

typedef struct nf_pipeline nf_pipeline;

NF_API int nf_api_version(void);
NF_API int nf_sample_rate(void);
NF_API int nf_frame_size(void);
NF_API int nf_analyzer_bins(void);
NF_API int nf_profile_bins(void);
NF_API int nf_has_onnx(void); /* built with ONNX Runtime support? */
NF_API void nf_default_config(nf_config* cfg);

NF_API nf_pipeline* nf_pipeline_create(const nf_config* cfg /* NULL = defaults */);
NF_API void nf_pipeline_destroy(nf_pipeline* p);

/* Live settings update; keeps learned profile and filter states. */
NF_API void nf_pipeline_set_config(nf_pipeline* p, const nf_config* cfg);
NF_API void nf_pipeline_get_config(nf_pipeline* p, nf_config* cfg);
/* Advanced spectral parameters (defaults: floor 0.08, smoothing 0.6, rise 0.003). */
NF_API void nf_pipeline_set_spectral_params(nf_pipeline* p, float floor, float smoothing, float rise);

/* Replace the whole EQ (count <= NF_EQ_MAX_BANDS). Filter states of unchanged bands are kept. */
NF_API void nf_pipeline_set_eq(nf_pipeline* p, int enabled, const nf_eq_band* bands, int count);

/* Load an ONNX denoiser (UTF-8 path). Returns 0 on success, else writes a message to err. */
NF_API int nf_pipeline_load_onnx(nf_pipeline* p, const char* path, char* err, int err_len);

/* Process exactly nf_frame_size() samples. in may equal out. Returns 0. */
NF_API int nf_pipeline_process(nf_pipeline* p, const float* in, float* out);

/* Room-noise profile learning (applied at the next frame boundary). */
NF_API void nf_pipeline_learn_start(nf_pipeline* p);
NF_API void nf_pipeline_learn_finish(nf_pipeline* p);
NF_API void nf_pipeline_clear_profile(nf_pipeline* p);
/* Copies the profile (nf_profile_bins() floats) into out. Returns 1 if a profile exists. */
NF_API int nf_pipeline_get_profile(nf_pipeline* p, float* out);
NF_API void nf_pipeline_set_profile(nf_pipeline* p, const float* profile);

/* Raw input capture (for noise sample contributions). capture_start records the next
   max_samples input samples into a buffer owned by the pipeline; capture_stop ends it, copies
   up to max samples into out and returns how many. *dropped (may be NULL) receives the number
   of frames the audio thread skipped because the UI held the buffer: non-zero = the recording
   has gaps and should be discarded. The audio thread never blocks on this. */
NF_API void nf_pipeline_capture_start(nf_pipeline* p, int max_samples);
NF_API int nf_pipeline_capture_stop(nf_pipeline* p, float* out, int max, int* dropped);

/* Current gain reduction in dB (>= 0) of the compressor and the limiter, for meters. */
NF_API void nf_pipeline_get_dynamics(nf_pipeline* p, float* comp_gr_db, float* limiter_gr_db);

/* Analyzer (UI thread). which = NF_INPUT or NF_OUTPUT. */
NF_API void nf_pipeline_spectrum_db(nf_pipeline* p, int which, float* db_out /* nf_analyzer_bins() */);
NF_API float nf_pipeline_level_db(nf_pipeline* p, int which);

/* ---------------------------------------------------------------- realtime engine
 * Windows: WASAPI (shared or exclusive), event driven, MMCSS "Pro Audio" thread.
 * Other platforms return NULL / 0 for now (Android/iOS engines come later). */

typedef struct nf_engine nf_engine;

typedef struct nf_device_info {
  char id[512];   /* opaque, UTF-8 */
  char name[256]; /* UTF-8 */
  int is_default;
} nf_device_info;

typedef struct nf_engine_stats {
  long long frames;     /* processed frames */
  long long xruns;      /* underruns + overruns + device glitches */
  float dsp_avg_us;     /* average nf_pipeline_process time */
  float dsp_max_us;     /* worst case since start */
  float latency_ms;     /* device buffers + queued audio (estimate) */
} nf_engine_stats;

NF_API int nf_device_count(int kind /* NF_INPUT / NF_OUTPUT */);
NF_API int nf_device_get(int kind, int index, nf_device_info* info); /* 0 on success */

/* in_id / out_id: nf_device_info.id, or NULL/"" for the default device. */
NF_API nf_engine* nf_engine_create(nf_pipeline* p, const char* in_id, const char* out_id, int exclusive,
                                   char* err, int err_len);
NF_API int nf_engine_start(nf_engine* e, char* err, int err_len);
NF_API void nf_engine_stop(nf_engine* e);
NF_API void nf_engine_destroy(nf_engine* e);
NF_API void nf_engine_get_stats(nf_engine* e, nf_engine_stats* s);

#ifdef __cplusplus
}
#endif
#endif
