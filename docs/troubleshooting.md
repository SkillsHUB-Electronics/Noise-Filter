# Troubleshooting

## The meeting app does not hear the filtered voice

1. In Noise Filter, the **output device** must be **CABLE Input (VB-Audio Virtual Cable)**, and the
   filter must be running (the status bar says *Running*).
2. In the meeting app (Teams, Meet, Zoom, Discord, TeamTalk, OBS…), the **microphone** must be
   **CABLE Output (VB-Audio Virtual Cable)**. Input and output names are swapped on purpose: the
   app writes into the cable's input, the meeting app reads from its output.
3. Browser apps such as Google Meet: pick the microphone in the meeting's settings, and make sure
   the browser has microphone permission.

## There is no "CABLE Input" device

VB-CABLE is not installed. Run the Noise Filter installer again (it installs VB-CABLE when it is
missing) and restart Windows if the installer asks. When running from source, install VB-CABLE from
[vb-cable.com](https://www.vb-cable.com).

## The sound crackles or drops out

- Look at **xruns** in the status bar. If the number keeps climbing, the audio is starved.
- Turn off **Exclusive mode** if it is on, or try it if it is off; some devices prefer one or the other.
- Close other apps that use the same microphone in exclusive mode.
- Use the **C++ engine** (the status bar says *Engine: C++*). The installer always includes it.
- The AI denoiser costs more CPU than the spectral one; switch to *Spectral* on a slow PC.

## My voice sounds thin, robotic or cut off

- Lower **Strength** (1.0 is the default).
- Lower the **Gate threshold** or turn the gate off; a high gate cuts quiet syllables.
- Click **Learn my room noise** while you stay quiet, so the spectral denoiser knows the real noise.
- Check the **Equalizer**: a strong high-pass or several stacked presets can remove too much.

## Windows SmartScreen warns about the installer

The installer is not code-signed yet, so Windows may show *Windows protected your PC*. Choose
**More info › Run anyway** if you downloaded it from the
[official releases page](https://github.com/SkillsHUB-Electronics/Noise-Filter/releases).

## Reset all settings

Quit Noise Filter from the tray menu, then delete `%APPDATA%\NoiseFilter\config.json`. The next
start uses the defaults.

## Still stuck?

Open a [bug report](https://github.com/SkillsHUB-Electronics/Noise-Filter/issues/new?template=bug_report.yml)
with the Noise Filter version (Settings › About), your Windows version, the devices you use and
what the status bar shows. The output of `nfctl status` helps a lot.
