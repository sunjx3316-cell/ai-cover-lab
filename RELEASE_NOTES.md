# AI Cover Lab v0.1.0-beta

Windows x64 完整离线测试版，包含分离、RVC 声线训练、参考转换和已授权的“凑企鹅”第 25 轮推理模型。
不包含原始录音、训练素材、歌曲成品或该声线的续训检查点。

## 下载与启动

1. 下载所有 `AI-Cover-Lab-Windows-offline.zip.partNN` 分卷、`offline-manifest.json`、`Install-Offline.cmd` 和 `install-offline.ps1`，放在同一文件夹。
2. 双击 `Install-Offline.cmd`。脚本校验分卷与完整 ZIP，合并并解压，无需另装解压工具，也不联网下载组件。
3. 打开解压出的 `AI-Cover-Lab` 文件夹，双击 `Start-Cover.cmd`，等待本地网页打开。
4. 选择声线库中的“凑企鹅 · 25轮”，上传歌曲制作。结束后可双击 `Stop-Cover.cmd` 关闭该目录的服务；训练时优先在网页中保存后停止。

完整包体积较大，合并和解压需要额外磁盘空间。安装目录不能是已有目录，避免覆盖你的模型和素材。
GitHub 自动生成的 Source code 不是完整运行包。

## 环境

无需预装 Python、Git 或 CUDA Toolkit，但仍需兼容 CUDA 12.4 的 NVIDIA 驱动。
已测试 RTX 4060 Laptop 8 GB；其他硬件的速度与可用批量可能不同。
当前不提供 CPU-only、macOS 或 Linux 的即用 Release。
启动器自动选择 7867–7886 中的空闲本地端口。

本版本未做代码签名。遇到系统安全提示先核验来源和 SHA256，不要关闭系统安全保护。
“凑企鹅”仅附带推理权重和索引，不能从该包继续原作者的训练；训练你自己的声线需新建项目。

## 许可

本项目原创 UI 和编排代码使用 MIT。第三方引擎、运行库和模型不是统一 MIT 许可。
YingMusic 权重采用 CC BY-NC 4.0，因此附带这些权重的流程仅限非商业使用，并须遵守署名等要求。
其他组件的原始许可和对应源码信息保留在包内；见 `THIRD_PARTY.md`、`MODEL_CARD.md` 和 `LICENSES`。
声线权利说明基于发布者的授权确认，不代表独立法律审查或官方背书。
