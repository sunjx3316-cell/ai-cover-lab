# AI Cover Lab

本地 AI 翻唱：三轨分离、专属声线训练、独立验收试听、声线入库、成品导出。
目前验证环境为 Windows、Python 3.10、RTX 4060 Laptop 8GB、CUDA PyTorch 2.4。

## 启动与安装

完整离线版本见 [GitHub Releases](https://github.com/sunjx3316-cell/ai-cover-lab/releases)。下载所有分卷及安装脚本，双击 `Install-Offline.cmd` 校验、合并和解压，然后双击解压目录中的 `Start-Cover.cmd`。
详见 [Release 使用说明](RELEASE_NOTES.md)。离线版无需预装 Python、Git 或 CUDA Toolkit，仍需兼容的 NVIDIA 驱动。

已安装：双击 `Start-Cover.cmd`，自动打开本地网页，优先使用 7867 端口。
首次安装：先安装 Git，再双击 `Setup.cmd`。默认安装到 `D:\AI-Cover-Lab`。
没有 D 盘时，可执行：

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1 -InstallRoot E:\AI-Cover-Lab
```

默认 Minimal 安装仅准备分离和 RVC 专属训练需要的模型。
要启用上传参考音频的免训练 YingMusic 转换，另执行：

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1 -Feature Ying
```

源码在线安装需要网络、足够的磁盘空间和兼容 NVIDIA 驱动；完整离线 Release 已附带组件。
下载、缓存、Python 和模型均位于安装目录，后端按固定 Git 提交下载。

## 声线训练

打开网页的“训练声线”页签：

1. 创建训练声线，或选择已有训练声线。
2. 添加多个目标声线的干净人声素材。初次建议 10–30 分钟，覆盖不同音区与力度。
3. 如需验收，单独添加目标声线验证录音，不能与训练使用同一录音；按歌曲/录音来源划分。
4. 完整验收还需添加其他声线的纯人声作为跨声线测试，覆盖高低音、快句、长音。
5. 开始训练。默认追加 5 轮，每轮保存模型和续训检查点，每 5 轮生成固定 12 秒验收片段。默认批量 4，关闭省显存训练；显存不足时降低批量或开启省显存。
6. 选择候选版本，对比原声和转换结果。确认声线、旋律、咬字、自然度后入库。
7. 正式翻唱时选择“已训练”声线，不需要每首歌重训。

同一训练声线可以添加新素材后续训。没有统一的 Loss 合格线。
声纹分数只能比较相同测试素材的不同版本，不能替代试听。
技术检测仅排查静音、明显时长错误和大量削波。严格验收入库需要技术检测、跨声线测试和试听确认。
验证素材和跨声线素材不再是训练或保存的必要条件。没有测试音频时，可选择候选版本，勾选“跳过完整验收”，点击“保存并加入声线库”。模型和索引会独立备份，当前模型状态标注为未完整验收，不代表音质合格。
“保存后停止”会等当前轮结束，保存后停止，不继续后续轮数；“立即停止”可能丢失本轮未保存进度，但保留此前完整轮数。GPU训练速度因素材长度、批量、显存和设备功耗而异。
训练不会根据主观音质自动提前停止；试听选择最佳版本，不一定是最新版本。
输入去重能够排除完全重复的音频，不能自动识别同一录音的不同剪辑，请按来源划分。

“参考”声线是 YingMusic 的参考音频，不是训练模型；两者分别标注。
旧 DDSP 权重不能直接加载为 RVC 或 YingMusic 模型。

## 翻唱和导出

在“制作翻唱”页签选择“声线库”，选择训练声线；名称旁边显示轮数，下面显示模型状态。
已训练声线优先被默认选中，残留的参考音频不会覆盖声线库选择。
只有主动选择“参考音频”时才使用上传的参考录音。YingMusic 推理步数对 RVC 模型不适用。
上传歌曲，先做短片段确认。制作时长设为 0 可处理整首。
分离模块保持主唱、和声、伴奏三轨；仅转换主唱。
“原曲和声混回”设为 -48 可关闭原唱和声。

“保存音频到本机”直接保存到安装目录的 `exports`，不依赖浏览器下载。
WAV 保留无损输出，MP3 使用 320 kbps，文件较小。下载链接采用附件响应。
刷新后恢复最近完成的成品；所有任务原文件仍在 `outputs`。

## 轻量化与开源发布

- 源码仓库只包含源码、安装脚本、依赖清单和文档，不含环境、模型、缓存与用户音频。
- 完整离线 Release 单独附带必要环境、第三方权重和授权推理声线，不包含原始训练录音。
- 默认不下载 Whisper/BigVGAN/YingMusic 转换权重，安装可选后端时才下载。
- PyTorch/CUDA 由训练和转换共用，GPU 阶段串行，避免多份环境与同时驻留。
- 同采样率只准备一套 40k 预训练模型；已有 RMVPE 尽可能硬链接复用。
- 仅保留一对续训检查点和最近三个未验收候选；已验收、手动保存和当前入库版本保留。
- 新安装的大权重直接落到运行位置，不再保存一份同样大小的下载缓存副本。

源码包小，不代表完整安装只有几 MB。CUDA、模型和训练状态仍占用 GB 级空间。
不建议量化训练或随意减小模型结构来缩体积，可能损害音质和训练兼容性。

运行 `python package_release.py` 生成 `dist/AI-Cover-Lab-source.zip`。
发布前检查 `THIRD_PARTY.md`，MIT 许可不覆盖第三方模型、音频或声线授权。
`.gitignore` 排除个人声音、成品、缓存、模型和环境；打包额外采用文件白名单。
仓库：https://github.com/sunjx3316-cell/ai-cover-lab 。附带声线的权利与质量状态见 `MODEL_CARD.md`。

## 验证

```powershell
.\envs\ying\Scripts\python.exe -m unittest test_contracts -v
```

开发自检 `validate_training.py` 仅使用开源示例跑短训练与续训，不代表声线质量。
该脚本依赖开发时样例路径，不包含在用户发布包内。
正式模型质量必须使用独立素材与实际听感验证。

## 数据目录

- envs, runtime: Python, CUDA PyTorch and FFmpeg.
- external: upstream inference code and bundled examples.
- models, cache: model weights and download caches.
- voices: saved reference recordings.
- training: per-voice datasets, candidates, validation reports and logs.
- exports: directly saved WAV/MP3 files.
- outputs: generated audio, settings and per-stage logs.
- temp: upload and processing temporary files.
- studio: backup copy of the previous DDSP app and retained trained model.

上游与许可证信息见 `THIRD_PARTY.md`。
