# Training the AI denoiser (NFNet)

NFNet is a small realtime model: 0.2 M parameters, about 2 M multiply-adds per 10 ms frame,
**0.4 ms per frame on one CPU core** in the C++ engine. It uses the same framing as the spectral
denoiser (480-sample hop, 1 frame of latency) and the app's streaming ONNX contract.

## Train in the cloud (no GPU needed)
GitHub → Actions → **Train AI model** → Run workflow. It downloads the public datasets, trains for
the time budget (default 150 min), evaluates against the spectral DSP and against the model that
ships today, and, when the new model is better, commits it to `noise_filter/models/` on that branch.
Merging the branch ships it: every app downloads it on its next start (verified by SHA-256).
A commit whose message contains `[train]` also starts a run.

Every Sunday 01:00 UTC the workflow also runs on its own. If the developer accepted new
user noise samples (F3, on the `/review` page) since the shipped model, it retrains with them and publishes the result to the default branch
when it passes the quality gate, so every app gets it with its next update check. Weeks without
new samples are skipped. The shipped manifest records how many contributed samples it was trained
with (`contrib_samples`).

## Train on your own PC
```
pip install torch scipy soundfile pystoi pesq onnx onnxruntime -e .
python -m training.download_data --out data --speakers 10      # ~ EARS + DEMAND + ESC-50
python -m training.train --clean data/clean --noise data/noise --minutes 120 --out runs/v1
python -m training.publish runs/v1 noise_filter/models          # quality gate + manifest
```
A CUDA GPU is used automatically when present. `--synthetic` trains on generated signals (smoke test).
Add more noise folders to `--noise`; user-contributed noise (roadmap F3) plugs in the same way.

## Data and licenses
| Data | Use | License |
|---|---|---|
| EARS (48 kHz anechoic speech) | clean speech | CC BY-NC 4.0 |
| DEMAND (48 kHz environments) | noise | CC BY-SA 3.0 |
| ESC-50 (environmental sounds) | noise | CC BY-NC 3.0 |

Because of the NC licenses, models trained on this data are for **non-commercial** use
(education, research, personal). For a commercial product, retrain on commercially licensed
speech (for example VCTK, CC BY 4.0) and noise.

## Files
`model.py` network and streaming step · `data.py` on-the-fly mixing · `train.py` training loop ·
`evaluate.py` SI-SDR / STOI / PESQ vs DSP · `export.py` ONNX export + streaming check ·
`publish.py` quality gate + manifest · `download_data.py` dataset download
