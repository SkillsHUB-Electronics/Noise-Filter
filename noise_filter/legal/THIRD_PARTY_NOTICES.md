# Third-party notices

Noise Filter's own source code is under the MIT License (see LICENSE). The Windows installer and the
Python package use the components below, which keep their own licenses.

| Component | Used for | License | Source |
|---|---|---|---|
| Qt 6 / PySide6 (Qt for Python) | User interface, audio file decoding | LGPL-3.0 | https://www.qt.io, https://wiki.qt.io/Qt_for_Python |
| FFmpeg (inside Qt Multimedia) | Decoding MP3 / M4A / FLAC / OGG noise files | LGPL-2.1+ | https://ffmpeg.org |
| pyqtgraph | Spectrum and equalizer graphs | MIT | https://github.com/pyqtgraph/pyqtgraph |
| NumPy | Signal processing | BSD-3-Clause | https://numpy.org |
| python-sounddevice | Audio input/output (Python engine) | MIT | https://github.com/spatialaudio/python-sounddevice |
| PortAudio (inside sounddevice) | Audio input/output (Python engine) | MIT | https://www.portaudio.com |
| ONNX Runtime | Running the AI model | MIT | https://github.com/microsoft/onnxruntime |
| pocketfft | FFT in the C++ core (`cpp/third_party/pocketfft`) | BSD-3-Clause | https://gitlab.mpcdf.mpg.de/mtr/pocketfft |
| Python | Runtime bundled by PyInstaller | PSF License | https://www.python.org |
| PyInstaller bootloader | Starting the bundled app | GPL-2.0 with bootloader exception (allows any license for the bundled app) | https://pyinstaller.org |
| VB-CABLE (VB-Audio Software) | Virtual microphone, installed separately by the installer | Donationware, see below | https://www.vb-cable.com |

## Qt / PySide6 and FFmpeg (LGPL)

Qt, PySide6 and FFmpeg are used as separate, dynamically linked libraries (the `.dll` / `.pyd` files in the
installation folder). Under the LGPL you may replace them with your own compatible build. Their full license
texts and source code are available from the project sites above; the LGPL-3.0 text is at
https://www.gnu.org/licenses/lgpl-3.0.html.

## VB-CABLE

VB-CABLE is made by VB-Audio Software and bundled under their distribution terms.
VB-CABLE is a donationware, all participations are welcome. Deployments in companies, schools or public
institutions, where end users cannot donate themselves, need VB-CABLE licenses bought by the distributor:
https://shop.vb-audio.com

## AI model and training data

The bundled AI model (`noise_filter/models/nfnet-*.onnx`) is trained on these public datasets:

| Dataset | Use | License |
|---|---|---|
| EARS (Meta / facebookresearch) | Clean speech | CC BY-NC 4.0 |
| DEMAND (Thiemann, Ito, Vincent) | Noise | CC BY-SA 3.0 |
| ESC-50 (Karol J. Piczak) | Noise | CC BY-NC 3.0 |
| Noise samples shared by Noise Filter users | Noise | CC0 1.0 |

Because of the non-commercial (NC) licenses, the model files are for **non-commercial use only**
(education, research, personal use). For a commercial product, retrain the model on commercially licensed
data (see `training/README.md`). The MIT License of the source code does not change this.
