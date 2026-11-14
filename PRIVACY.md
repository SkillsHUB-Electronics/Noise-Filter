# Noise Filter Privacy Policy

Last updated: 14 November 2026 (app version 0.9.0)

Noise Filter is a Windows app by SkillsHUB Electronics that cleans up your microphone sound. This policy says
what data the app handles, what leaves your PC and when, and how you can delete it. Bahasa Indonesia:
[PRIVACY.id.md](noise_filter/legal/PRIVACY.id.md).

## In short

- Your microphone sound is processed **only on your PC**. It is never recorded to disk or sent anywhere
  while you use the filter.
- There are **no accounts, no ads, no analytics, no tracking and no crash reports**.
- The app connects to the internet for only two things: **checking for a new AI model** (a download from
  GitHub) and, **only when you press "Send"**, uploading a short **noise sample** you chose to share.
- You can delete every noise sample you sent with one button: **Settings > AI model & noise samples > Delete my samples**.

## 1. Data that stays on your PC

| What | Where | Why |
|---|---|---|
| Settings (devices, filter, equalizer, theme, language, window size) | `%APPDATA%\NoiseFilter\config.json` | To remember your choices |
| Downloaded AI models | `%APPDATA%\NoiseFilter\models\` | Newer noise-reduction models |
| Sample-sharing state: a random installation ID, your consent choice, how many samples you sent | `%APPDATA%\NoiseFilter\contribute.json` | So you can delete your samples later |
| "Learn my room noise" profile | Memory only | Better noise reduction; gone when the app closes |

The audio stream from your microphone passes through the filter in memory, 10 ms at a time, and is sent to
the output device you chose (for example VB-CABLE). It is not saved.

**Local control.** The command-line tool `nfctl` and the MCP server for AI assistants talk to the app through
a local pipe that only your Windows user account can open. Nothing goes over the network.

Uninstalling the app does not remove `%APPDATA%\NoiseFilter`; delete that folder to remove these files.

## 2. AI model update check

About 3 seconds after the app starts, and when you press "Check for AI model update", the app downloads a
small file (`manifest.json`) from `raw.githubusercontent.com` (GitHub). If it lists a newer model, the model
file is downloaded from GitHub and its checksum is verified. **Nothing about you is uploaded.** Like any web
request, GitHub receives your IP address and the app's user agent; GitHub's handling of that is described in
the [GitHub Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement).
Set the environment variable `NF_NO_UPDATE_CHECK=1` to turn the automatic check off.

## 3. Sharing noise samples (optional)

You can help the AI get better by sharing recordings of **background noise only** (fan, air conditioner,
traffic, keyboard...). This is always your choice:

- The app offers a sample after "Learn my room noise", "Record noise…" (10 s from your microphone) or
  "Send a noise file…" (a file you recorded yourself). You can listen to it first.
- Before anything is offered, the app checks the recording **on your PC** and refuses any part that sounds
  like a voice or music.
- Nothing is sent until you tick the consent box and press **Send**. You can turn the offer off with
  "Don't ask again" or the "Offer to share noise samples" setting.

**What is sent with each sample:**

- the audio clip (2-10 seconds, 48 kHz mono WAV);
- the noise type you picked (for example "Fan / air conditioner");
- the app version and the operating system name (for example "windows");
- the random installation ID (created once on your PC; it identifies the installation, not you or your PC);
- the consent version (`cc0-v1`) and whether the clip came from the microphone or a file.

No name, email, account, device name, location or other file is sent.

**Where it goes.** Samples are received by a Cloudflare Worker (`noise-filter-samples.mukhamadkhoirul.workers.dev`)
and stored in a private Cloudflare R2 storage bucket. Our service does not store your IP address.
Cloudflare, as the hosting provider, processes connection data (such as IP addresses) to run and protect its
network, as described in the [Cloudflare Privacy Policy](https://www.cloudflare.com/privacypolicy/).

**What happens next.**

1. An automatic check runs every day (format, length, clipping, voice detection, duplicates).
2. The developer **listens to every sample** on a password-protected review page and accepts or rejects it.
3. Only accepted samples are used to train new versions of the Noise Filter AI model. Training runs on
   GitHub Actions; the resulting model is published in the public GitHub repository.
4. Rejected samples are deleted automatically after 30 days. Accepted samples are kept for future training
   until you delete them.

**License of your sample.** When you consent, you release the sample under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) (public domain). We do not currently publish the
samples, but CC0 allows them to be shared, for example as part of an open noise dataset. Only share noise you
recorded yourself and are happy to give away.

**Deleting your samples.** Press **Settings > AI model & noise samples > Delete my samples**. This deletes every sample sent
from this installation (waiting, accepted or rejected) from our storage straight away. (The button appears once you have sent a sample.) A model that was
already trained with a sample cannot "forget" it, but the sample itself is gone. The delete button works with
the installation ID in `contribute.json`, so press it **before** you uninstall or delete that file.

## 4. Children

Noise Filter is not directed at children and does not knowingly collect personal data from anyone. Noise
samples must not contain voices.

## 5. Changes

If this policy changes, the new version ships with the app and is published in the repository with a new
date. A change that sends new kinds of data will ask for your consent again.

## 6. Contact

Questions or requests: open an issue at
[github.com/SkillsHUB-Electronics/Noise-Filter/issues](https://github.com/SkillsHUB-Electronics/Noise-Filter/issues).
Do not post personal data in a public issue; ask there for a private contact if you need one.
