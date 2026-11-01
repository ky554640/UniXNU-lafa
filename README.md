# UniXNU-lafa (SM8850)

本仓库为 **realme GT8 Pro（真我 GT8 Pro，代号 lafa，型号 RMX5200，板级代号 RE6030L1，SoC 高通骁龙 8 Elite Gen 5 / SM8850 "canoe"）** 的 UniXNU 与 Darwin / XNU 内核早期移植支持仓库。

---

## 设备信息（已采集确认）

| 项目 | 值 | 来源 |
| --- | --- | --- |
| SoC | SM8850（平台代号 `canoe`） | fastboot `product=canoe` + dtb msm-id 0x2c0 |
| 板级 | RE6030L1，lafa board msm-id 0x295 | dtbo `qcom,msm-id` |
| 面板 | BOE AE084（**1440×3136**，DSC cmd；真机 SurfaceFlinger mode0 实测） | dtbo + 真机 `dumpsys` |
| 独立显示芯片 | Pixelworks IRIS7P（`mdss_iris7p_cfg`） | dtbo |
| 触控 | Synaptics S3910（SPI，18×39；Android 下驱动路径 `synaptics_tcm/touch_input`） | dtbo + 真机 `dumpsys input` |
| PMIC | PMK8850 | dtbo |
| 存储 | UFS（`ufshc@0x1d84000`） | dtb |
| 平台 GIC | GICv3 `0x17000000` / GICR `0x17080000` | dtb（与 SM8850 共享层一致） |
| 定时器 | 19.2 MHz（`arch_timer@0x17810000`） | dtb |

## 架构与分工

| 模块 | 负责内容 | 构建环境 |
| --- | --- | --- |
| **UEFI 固件** | BootShim + lafa UEFI + GOP + UniXNUDxe + DarwinBoot | 本地 Linux (Clang 18+) |
| **Apple 设备树 (ADT)** | SM8850 GICv3 (`0x17000000`, `0x17080000`)、19.2 MHz 架构定时器、CPU0、NVRAM proxy | Linux / macOS (`scripts/make-lafa-adt.py`) |
| **早期屏幕诊断 (BootProgress)** | 无串口环境下通过 UEFI GOP Framebuffer 渲染早期内核进度 (`S1`~`S6`) 及异常/Panic 信息 | Linux / macOS |
| **Darwin / XNU 源码内核** | 纯源码编译 XNU Mach-O + corecrypto + libpthread + ArmDTPlatform + ArmCpu | GitHub Actions `macos-15` runner |
| **FAT Payload 镜像** | 包含 `kernel.macho`、`adt.bin`、`unixnu.toml` 的 FAT 镜像 | GitHub Actions 或本地 Linux (`mtools`) |
| **Android 启动镜像 (boot.img)** | 合成 BootShim + UEFI FD + 内嵌 Payload + 原厂 DTB 的 Android Boot v4 镜像 | 本地 Linux (`./unixnu bootimg`) |

---

## 与 SM8850 先行者的复用关系

本仓库以 **OnePlus 15T（`UniXNU-fairlady`，Osilvfe）** 为直接模板（同为 SM8850 标准 UniXNU 格式），并参考 **小米 17 Pro（`data-a-live`，ShueiTsuki）** 已跑通 GPU/UI 的实现。

- **平台层完全复用**：GICv3、定时器、UFS、CPU 拓扑与 fairlady 一致（已验证 dtb 地址相同）。
- **板级差异待适配**：
  1. 面板 BOE AE084（lafa 特有，含 Pixelworks IRIS7P 独立显示芯片链路）
  2. 触控 Synaptics S3910（SPI，与 pandora 的 Synaptics TCM 同系列，驱动可参考）
  3. 按键 GPIO / PMIC PON 映射（需从 lafa dtbo 校验）

## 启动阶段与诊断反馈

由于手机在没有拆机飞线的情况下缺乏硬件串口 UART，内核早期崩溃通常会导致黑屏或复位。
本项目集成原生早期显存映射与控制台驱动 (`BootProgress`)，在加载器交接后直接利用 GOP 帧缓冲区绘制进度：

- **S1**: 内核入口代码执行，MMU 关闭，打印引导参数物理/虚拟地址与时钟频率
- **S2**: 扩展 TTBR0 初始恒等页表映射至 GOP 显存
- **S3**: MMU 启用，切换至虚拟地址
- **S4**: 进入 `arm_init`，执行内核重定位与符号初始化
- **S5**: 进入 `machine_startup`，初始化单核调度器与中断
- **S6**: 进入 `bsd_init`，初始化 BSD 子系统并寻找根文件系统
- **异常 / Panic**: 拦截同步/异步异常，将 ESR、FAR、PC 及寄存器状态直接转储在屏幕上

## 构建步骤

### 1. 云端编译 XNU Mach-O 内核 (GitHub Actions)
在 GitHub 仓库中，进入 **Actions → lafa SM8850 XNU (realme GT8 Pro) → Run workflow**，运行工作流。
工作流完成后，下载 Artifact 产物，解压至 `out/lafa/actions/run-<序号>`：
- `kernel/kernel.macho`
- `payload/payload.img`
- `payload/payload.json`
- `unixnu.lock`

### 2. 本地测试与设备树校验
```bash
python3 scripts/test-upstream.py
TREE=$(./unixnu --prepare)
python3 "$TREE/scripts/test-kernel-source.py"
python3 "$TREE/scripts/test-bootimg.py"
python3 scripts/test-adt.py
python3 "$TREE/drivers/DarwinBoot/Test/test-adt.py"
```

### 3. 本地打包最终启动镜像
```bash
./unixnu bootimg \
  --fd ../Mu-Silicium/Build/lafaPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd \
  --dtb .cache/firmware/vendor_boot/dtb \
  --ramdisk out/lafa/actions/run-1/payload/payload.img \
  -o out/lafa/boot.img
```

### 4. 刷入与临时引导测试
```bash
fastboot boot out/lafa/boot.img
```

> 注意：lafa 的 fastboot 仅支持写入（`flash`/`boot`），不支持 `fetch`/`get_stored` 读取分区。

---

## 显示链路适配（重要更新）

lafa 的显示链路是 **MDSS → Pixelworks IRIS7P → BOE AE084**，其中 IRIS7P 是最大卡点。**已确认 IRIS7P 驱动源码开源**，已下载到 `references/iris7/`（43 个文件，来自 `opudon/vendor_qcom_opensource_display-drivers`）。

关键匹配：
- lafa 设备树节点 `pxlw,iris` ↔ 开源驱动 `dsi_iris_lightup.c` 的 `{.compatible = "pxlw,iris"}`
- IRIS7 芯片版本 `0x4777`，固件 `iris7.fw`（闭源，需从原厂 `/odm/firmware/` 提取）
- 面板 `AC180_P_3_A0020` 与 fairlady 同款，驱动可参考

详见 `../lafa显示链路适配方案.md`。

## ⚠️ 架构澄清：UniXNU 显示不走 IRIS/DSI，走「UEFI GOP + GPU 合成」

经过对 data-a-live（已跑通 GPU 合成 UI）的深入分析，**UniXNU 的显示架构与 Linux 不同**：

```
UniXNU 实际显示链路：
  UEFI GOP 点亮屏幕（framebuffer）
    └─ GPU (Adreno 840) 合成画面（NativeAdreno 驱动）
         └─ CPU 拷屏 / 显示控制器直接显示（优化项）
```

**关键结论：**
1. **IRIS7P 在 UniXNU 里可绕过** —— 它是画质增强芯片，UniXNU 用 UEFI GOP framebuffer 显示，不走 MDSS/DSI/IRIS。
2. **真正的 P0 是 Adreno 840 GPU 驱动**，而 **data-a-live 已经把 SM8850 的 Adreno 840 跑通**（`wsl/pandora_gpu.c`，146KB，Level 1-15 全过，GPU 合成 UI 工作）。GPU 是平台级硬件，lafa 与 pandora 完全一致，**100% 可复用**。
3. IRIS7P 驱动源码/固件保留为「未来做显示控制器直接显示（120Hz 优化）」的储备，不是点亮屏幕的前置条件。

### 修正后的适配优先级

| 优先级 | 模块 | 复用来源 |
|---|---|---|
| P0 | Adreno 840 GPU | data-a-live `pandora_gpu.c` + `xnu/patches/pandora-gpu-*.patch`（42个）|
| P0 | UEFI GOP 点亮 | fairlady BootProgress + data-a-live framebuffer 补丁 |
| P1 | 触控 S3910 | pandora Synaptics TCM（`pandora_touch.c`，硬件接线一致）|
| P2 | UFS/PMIC/按键 | 平台层一致 |

## GPU 驱动移植（已完成板级参数适配）

Adreno 840 是平台级硬件，lafa 与 pandora（小米 17 Pro）**硬件 IP 完全一致**。已把
data-a-live 跑通的 `pandora_gpu.c`（3665 行，Level 1–15 全过，GMU 冷启动 → HFI → CP → Metal）
移植为 lafa 版：

| 文件 | 说明 |
| --- | --- |
| `drivers/adreno/lafa_gpu.c` | 完整 GPU 驱动（GMU 冷启动 + HFI + CP + 用户接口），已改好 lafa 板级参数 |
| `drivers/adreno/lafa_gpu_params.h` | lafa 板级参数头（频点表 / chipid / 带宽表） |
| `docs/GPU移植对照表.md` | pandora→lafa 精确参数 diff 与分级测试步骤 |

**已改的 4 处板级参数**（其余代码 100% 复用）：

| 参数 | pandora | lafa |
| --- | --- | --- |
| GPU 频点表 | 18 档，最高 1200 MHz（speed-bin 0xfc） | 17 档，最高 1050 MHz（speed-bin 0x0） |
| GMU 频点表 | 4 档（475/575/700/750 MHz） | 2 档（475/700 MHz） |
| DDR 带宽表 | 12 档（6672899） | 12 档（6671875） |
| chip id | 0x44050a01 | 0x44050a00 |

**测试**：刷机后用启动参数 `pandora_gpu=1`（纯读）逐级到 `pandora_gpu=14`（用户接口）。
固件 `gen80200_gmu.bin` / `gen80200_sqe.fw` / `gen80200_zap.mbn` 需从 lafa
`/vendor/firmware/` 提取（建议用 lafa 自己的，realme 可能有厂商 patch）。

## 触控驱动移植（已完成板级参数适配）

lafa 触控是 **Synaptics S3910（SPI，TouchComm 协议）**，硬件接线与 pandora（小米 17 Pro）的
S3910P **99% 相同**（同为 SM8850 QUPv3 wrapper 4 SE0 @ 0x1a80000，GPIO 48-51 SPI、IRQ 158）。
已把 data-a-live 跑通的 `pandora_touch.c` 移植为 lafa 版：

| 文件 | 说明 |
| --- | --- |
| `drivers/touch/lafa_touch.c` | 完整触控驱动（GCC 时钟 + GENI SE + GPI DMA + SMMU + TouchComm），已改好 lafa 板级参数 |
| `docs/触控移植对照表.md` | pandora→lafa 精确参数 diff、HBP 封装说明、分级测试步骤 |

**已改的 4 处板级参数**（其余代码 100% 复用）：

| 参数 | pandora | lafa |
| --- | --- | --- |
| RESET GPIO | 66 | 159（0x9f） |
| AVDD GPIO | 117 | 66（0x42） |
| iovdd LDO | L4I_E0 | L4B |
| 面板分辨率 | 1220×2656（呈 1125×2436） | 1440×3136（无缩放） |

**关于 HBP**：lafa DT 的触控兼容字符串是 `synaptics,tcm-spi-hbp`（OPPO HBP 封装），但 HBP 是
纯软件层，IC 本身仍说原生 TouchComm。`lafa_touch.c` 直接和 IC 的 TouchComm 对话，正好绕过 HBP，
无需移植 HBP 框架。

**测试**：刷机后用启动参数 `lafa_touch=1`（纯 probe）→ `=3`（+RPMh）→ `=7`（+SPI+identify）
→ `=0xf`（+触摸上报）。辅助参数 `lafa_steps=MS` 定位总线挂死点。

⚠️ **待实测**：AVDD GPIO 66 的极性（lafa DT 第三个值 0x01 是 active-low，但 0x42 是 gpio-regulator
phandle 而非 TLMM 直连，驱动里输出高电平需实测确认）；cmd-db 里 L4B 的精确 VRM 资源名。

## SCM/PAS 支撑与固件打包（已完成）

GPU 冷启动的 Level 8+ 需要 TrustZone 认证 zap 固件，这条链路依赖 SCM 调用 + PAS 认证 +
UFS 读固件包。已补齐：

| 文件 | 说明 |
| --- | --- |
| `drivers/scm/lafa_adsp.c` | SCM 调用 + PAS 认证 + 固件读取（从 `pandora_adsp.c` 移植，SM8850 通用） |
| `tools/mkfwpack.py` | 原始 PANDFW01 固件包打包器 |
| `tools/mkfwpack-lafa.py` | lafa GPU 固件打包脚本（打包 gen80200 三件套） |
| `docs/SCM固件支撑集成说明.md` | SCM/PAS/UFS 支撑的注册方式 + 固件打包步骤 |

**关键确认**：SCM/PAS 所需的所有地址（IPCC 0x1106000、RSC 0x18920000、SMEM 0x81d00000、
ADSP carveout 0xa1400000）在 lafa 的 DT 里与 pandora **完全一致**，100% 平台通用。

**注意**：`lafa_adsp.c` 里公共函数名保留 `pandora_` 前缀（`pandora_scm_call`/
`pandora_pas_load_auth`），因为 `lafa_gpu.c` 的 extern 声明就是这个名字，是跨文件稳定 ABI。
ADSP 音频部分（TDM GPIO、carveout 大小 0x5000000）是板级相关，留待后续单独适配。

## vbmeta 校验处理（调试阶段不要碰）

**调试阶段全程用 `fastboot boot`，不需要也不能去改 vbmeta。**

`fastboot boot` 把镜像走 USB 直接加载进 RAM 执行，**一个字节都不写入存储**，不经过 vbmeta
的 AVB 校验链。所以：

- 重启 / 断电 → RAM 清空 → 自动回到原 Android 系统，无需救砖
- 崩溃最坏结果是停在 bootloader，重来一次即可
- 完全不用关心 `secure=yes`

```bash
fastboot boot out/lafa/boot.img
```

⚠️ **事故记录**：曾经按旧文档执行 `avbtool make_vbmeta_image --flags 2` 生成 vbmeta 并
**同时刷入 a/b 两个槽**，导致设备无限重启、最终掉进 EDL(9008)，只能送 realme 官方售后
用带授权的 MSM 工具才救回。原因有三：

1. `avbtool` 生成的是**小端** vbmeta，而 OPPO/realme 的 AVB 格式是**大端**（非标准）
2. **两个槽一起刷** → 退路全毁，无法 `fastboot set_active b` 回退
3. vbmeta 被改坏后 bootloader 直接拒绝引导

只有当你确实要**长期刷入**自定义 boot 分区（而不是临时 RAM 启动）时，才需要考虑禁用校验。
那种场景的正确做法见 `docs/vbmeta处理说明.md`，且**必须只刷当前槽位**。

## 待办 / 下一步

- [x] **UEFI 固件已在真机 `fastboot boot` 启动成功**（GOP 上屏，UniXNU 提示"没有系统"后复位）——见 `docs/首次上机记录.md`
- [x] 打包 lafa `boot.img`（header v4 + 原厂 14 个 DT 集合，打包自校验通过）
- [x] `MemoryMapLib` 按 lafa DT 的 `reserved-memory` 补齐 7 块保留区，并加 `scripts/check-reserved-regions.py` 校验
- [ ] 编出 XNU 内核（走 GitHub Actions `macos-15`；上游固定版本不支持 Linux 原生编译）
- [ ] 组 payload（kernelcache + 信任缓存 + 数据 ramdisk）后重打 `boot.img`
- [ ] 确认 lafa 真实 ECID 与 board-id（当前 ADT 用占位值 0x1570000000000001 / 0x295）
- [x] 从 lafa dtbo 提取完整面板时序（BOE AE084）与触控 S3910 的 reg/中断（见 `../lafa板级适配清单.md`）
- [x] 确认 IRIS7P 驱动源码（已下载到 `references/iris7/`）
- [x] 提取闭源固件（`iris7p*.fw` + 面板配置 + 触控 + UFS + 音频，见 `proprietary-firmware/`）
- [x] GPU 驱动板级参数适配（`drivers/adreno/lafa_gpu.c` + `lafa_gpu_params.h`）
- [x] 触控驱动板级参数适配（`drivers/touch/lafa_touch.c`）
- [x] SCM/PAS 支撑（`drivers/scm/lafa_adsp.c`）+ 固件打包脚本（`tools/mkfwpack-lafa.py`）
- [x] vbmeta 处理说明（`docs/vbmeta处理说明.md`）
- [ ] 提取 GPU 固件 `gen80200_{gmu.bin,sqe.fw,zap.mbn}`（从 lafa `/vendor/firmware/`，需 root）
- [ ] 打成 PANDFW01 固件包（`python3 tools/mkfwpack-lafa.py`）
- [ ] 禁用 vbmeta（刷 vbmeta_disabled.img）
- [ ] 刷机分级测试 GPU（`pandora_gpu=1` → `=14`）
- [ ] 刷机分级测试触控（`lafa_touch=1` → `=0xf`）
- [ ] 实测确认 AVDD GPIO 66 极性 + cmd-db L4B 资源名
- [ ] 移植 IRIS7P 驱动（SM8850 走 `dsi_iris_cmpt_8550.c` 路径；改 `IRIS_FIRMWARE_NAME` 为 `iris7p.fw`）
- [ ] 移植 BOE AE084 面板驱动（参考 fairlady 的 AC180）
- [ ] 校验按键 GPIO 与 PMIC PON 映射
- [ ] 处理 `secure=yes` 的 vbmeta 校验（刷自定义 UEFI 前需禁用）

## 闭源固件（已提取）

`proprietary-firmware/` 目录存放从 lafa 原厂 `/odm/firmware/` 提取的闭源二进制（**免 root 提取**，`/odm/firmware` 文件权限为 `-rw-r--r--`）：

```
proprietary-firmware/
├── display/   # iris7p.fw + iris7p_ccf1/2/3.fw + pxlw_i7p_panel_AE084_*.fw
├── touch/     # FW_S3910_BOE_HBP.img + LIB_S3910_BOE_HBP_TS_ALGO.so + libIfp.so
├── audio/     # tfa98xx.cnt (NXP 功放校准)
└── ufs/       # SAMSUNG + SKhynix UFS 芯片固件
```

> ⚠️ 移植 IRIS 驱动时，开源 `dsi_iris_def.h` 固件名为 `iris7.fw`，需改为 lafa 实际的 `iris7p.fw`。
