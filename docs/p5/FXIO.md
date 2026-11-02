# FXio 玻片读取环境

2026-10-31：FXio 0.1.2 已安装到服务器 PathoReason 独立 `.venv`。使用用户提供的 `FXio-dev.zip`，SHA256 为 `f34aeac87ee5926fcbaf534a03436739b03dfb1556765ab5269738fd32dcb5be`；压缩包未提供 Git commit，因此来源按归档摘要固定。

## 调用

必须使用 `/home/bxn/projects/PathoReason/.venv/bin/python` 运行项目内读取脚本；系统 Python、旧引擎环境和本机环境不属于本次安装范围。正式对话可通过原生命令调用此解释器。

```python
from wsi import open_wsi

slide = open_wsi(verified_slide_path, lazy_init=True)
try:
    slide.ensure_initialized()
    metadata = {
        "dimensions": slide.dimensions,
        "level_count": slide.level_count,
        "level_dimensions": slide.level_dimensions,
        "level_downsamples": slide.level_downsamples,
        "mpp": slide.mpp,
        "mag": slide.mag,
    }
    tile = slide.read_region((0, 0), 0, (64, 64), read_as="numpy")
finally:
    slide.close()
```

`verified_slide_path` 来自已核验的接口记录。接口返回 JSON 与读取实际 WSI 是两个步骤；FXio 不会自动下载整个数据集。原始切片保持只读，元信息清单写入当前正式项目 `inputs/`，供展示的图件写入 `figures/`，分析报告写入 `outputs/`，按需显式 publish。不得把患者原始记录输出到公开对话。

## 已验证范围

- 真实 ZYP、MRXS 各一份：初始化、尺寸/层数/MPP/倍率、64×64 RGB 区域、最大边 128 的缩略图及句柄关闭通过；源文件大小和修改时间保持不变。
- `uv pip check` 通过；安装前的 26 个应用包版本保持不变。应用健康接口仍正常，没有重启服务。
- 其他格式未进行真实样本验收。组织 mask 等可选功能所需的 Python OpenCV、pyvips 等未由本次基础安装启用。安装成功不代表整个研究数据集已完成校验。

## 版本与恢复

新增：FXio 0.1.2、numpy 2.5.4、pillow 13.0.0、tqdm 4.70.1、openslide-bin 4.0.1.2、openslide-python 1.4.7、tifffile 2026.10.15。

归档、解包源码、安装前后依赖快照和真实读取回执均保存在：

`/data/bxn/PathoReason/acceptance/fxio-install-20261031-f34aeac8/`

这是附加研究工具安装，未改写基础应用 `requirements.lock`。若使用基础锁文件重建或同步环境，需要随后重新安装这一附加工具集合。在已恢复基础依赖的环境中可使用下列命令；`uv` 为现有包管理工具：

```bash
uv pip install --python /home/bxn/projects/PathoReason/.venv/bin/python \
  --cache-dir /data/bxn/PathoReason/cache/uv --link-mode copy \
  --constraint /data/bxn/PathoReason/acceptance/fxio-install-20261031-f34aeac8/constraints-before.txt \
  /data/bxn/PathoReason/acceptance/fxio-install-20261031-f34aeac8/source/fxio \
  numpy==2.5.4 Pillow==13.0.0 tqdm==4.70.1 \
  openslide-bin==4.0.1.2 openslide-python==1.4.7 tifffile==2026.10.15
```

本次使用的 uv 可执行文件：`/home/bxn/build_kg_paper/.dev/bootstrap-venv/bin/uv`（0.13.6），仅作为已有工具调用。
