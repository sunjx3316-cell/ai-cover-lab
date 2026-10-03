# Third-Party Components

This source distribution contains the UI and orchestration code only. It does
not include third-party model weights, runtime environments, voice recordings,
or upstream source checkouts. Setup downloads upstream code with its original
license files intact.

- YingMusic-SVC: https://github.com/GiantAILab/YingMusic-SVC
  MIT-licensed source, pinned revision 4974a80c6044c4557059548409379f6365129f88.
- Applio: https://github.com/IAHispano/Applio
  MIT-licensed source, version 3.6.5, revision
  55fe0b976a6990bb75261c32ccecf6bfca3198f1.
- CUDA PyTorch: https://pytorch.org (separate upstream license).
- Gradio: https://github.com/gradio-app/gradio (Apache-2.0).
- imageio-ffmpeg is BSD-2-Clause; its Windows binary is separately licensed.
  The online installer currently receives a GPLv3 FFmpeg 7.1 Gyan static build.
  The offline builder requires an audited LGPL shared FFmpeg distribution and
  a corresponding-source folder; it excludes imageio's bundled static exe.
  https://ffmpeg.org/legal.html
- pedalboard 0.9.17: GPLv3, https://github.com/spotify/pedalboard/tree/v0.9.17.
  Its notices and corresponding source must accompany binary redistribution.
  MIT application source may be reused under MIT, but that does not remove GPL
  obligations from a combined runtime. Do not describe the complete bundle as MIT.
  This public offline build excludes its binaries: Applio's optional effects
  import is moved into its effects method by a recorded build-time patch.
  AI Cover Lab never requests those optional effects. The upstream source
  archive is retained for provenance, not loaded as a runtime plugin.
- SoundFile 0.12.1: BSD wrapper; libsndfile 1.2.0 is LGPL-2.1-or-later.
  The public DLL is rebuilt shared, with external and MPEG codecs disabled.
  FFmpeg handles compressed inputs/exports. Exact source and build recipe are
  included; users may replace/rebuild the shared library.
- soxr 1.1.0: LGPL-2.1-or-later Python wrapper/native library, BSD PFFFT/nanobind.
  The offline wheel is rebuilt from the included source, with the exact
  nanobind source and rebuild recipe supplied alongside it.
- NVIDIA CUDA 12.4 and cuDNN 9.1 runtime DLLs are proprietary redistributable
  components, not relicensed under MIT. Only the application's runtime DLLs
  are included, not a standalone SDK or driver. Their original EULAs and
  notices are included in LICENSES/corresponding-source/runtime-notices.zip.
  Use of NVIDIA components remains subject to those terms and NVIDIA GPU
  restrictions. No NVIDIA sponsorship or endorsement is claimed.
- CPython: PSF license; runtime LICENSE.txt is preserved.
- Installed Python package metadata and license files are retained in
  runtime/python/Lib/site-packages. DEPENDENCIES.json records installed versions.
- FAISS: https://github.com/facebookresearch/faiss (MIT).

Model download sources:

- https://huggingface.co/GiantAILab/YingMusic-SVC
- https://huggingface.co/IAHispano/Applio
- https://huggingface.co/funasr/campplus
- https://huggingface.co/lj1995/VoiceConversionWebUI
- https://huggingface.co/openai/whisper-small (model repository: Apache-2.0).
- https://huggingface.co/nvidia/bigvgan_v2_44khz_128band_512x (MIT).

YingMusic source code is MIT, but the GiantAILab/YingMusic-SVC model repository
labels its weights CC BY-NC 4.0. This applies to the separator checkpoint and
the full SVC checkpoint distributed from that repository, absent a file-level
exception. Attribute GiantAILab and retain the noncommercial restriction.
License: https://creativecommons.org/licenses/by-nc/4.0/
CAM++ weights are Apache-2.0; the Applio and lj1995 model repositories label
their distributed assets MIT. These are upstream declarations, not clearance
of unrelated user recordings or every possible derivative.

The bundled voice is documented separately in MODEL_CARD.md. No original
recordings or personal training datasets are redistributed. Full offline
releases include selected engine checkouts and weights; the source ZIP does not.

The project's MIT license does not grant rights to third-party weights or
recordings. Review each upstream model card and the rights to your voice/music
materials before distributing weights, datasets, or generated covers.
