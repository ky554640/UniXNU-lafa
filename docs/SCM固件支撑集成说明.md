# lafa 驱动编译集成补充（SCM/PAS 支撑 + 固件打包）

> 本文是 `GPU编译集成说明.md` 的补充，覆盖 GPU 冷启动链路里**缺失的支撑件**：
> SCM/PAS 固件认证（`lafa_adsp.c`）+ 固件包打包（`mkfwpack-lafa.py`）。
> GPU 驱动 `lafa_gpu.c` 依赖这些支撑才能把 `gen80200_zap.mbn` 交给 TrustZone 认证。

## 一、依赖链全貌

GPU 冷启动（Level 8+，GMU 固件加载）的完整调用链：

```
lafa_gpu.c (gpu_level8)
  └─ pandora_pas_load_auth("gen80200_zap.mbn", GPU_ZAP_PAS, ...)
       └─ lafa_adsp.c : pandora_pas_load_auth()
            ├─ pandora_fw_read()          ← sweet_ufs.c（读 PANDFW01 固件包）
            └─ pandora_scm_call()         ← lafa_adsp.c（TrustZone SCM 调用）
                 └─ PAS_AUTH_AND_RESET    ← TZ 认证固件段
```

所以一个能跑到 Level 8 的完整构建，需要注册 **4 个源文件**：

| 文件 | 来源 | 作用 |
| --- | --- | --- |
| `bsd/dev/lafa_gpu.c` | `drivers/adreno/lafa_gpu.c` | GPU 驱动主体（GMU/HFI/CP） |
| `bsd/dev/adreno/*.c`（10个） | `drivers/adreno/ArmSmmu4K*` | SMMU 4K 页表套件 |
| `bsd/dev/lafa_adsp.c` | `drivers/scm/lafa_adsp.c` | SCM 调用 + PAS 认证 + 固件读取 |
| `bsd/dev/sweet_ufs.c` | UniXNU 平台层（UFS 补丁 0028/0114-0121） | UFS 根设备 + `pandora_fw_read` |

## 二、注册步骤（bsd/conf/files）

在 `bsd/conf/files` 里追加：

```
bsd/dev/lafa_gpu.c            standard
bsd/dev/lafa_adsp.c           standard
bsd/dev/adreno/ArmSmmu4K.c         standard
bsd/dev/adreno/ArmSmmu4KContext.c  standard
bsd/dev/adreno/ArmSmmu4KMmio.c     standard
bsd/dev/adreno/ArmSmmu4KProgram.c  standard
bsd/dev/adreno/ArmSmmu4KStreams.c  standard
```

（`sweet_ufs.c` 由 UFS 补丁 0028/0114 注入，走 UniXNU 平台层，不在 lafa 仓库重复维护。）

## 三、启动调用（sweet_ufs.c）

在 `sweet_ufs_init()` 里追加调用（与 GPU 一致）：

```c
extern void lafa_gpu_init(void);
extern void pandora_adsp_init(void);   /* SCM/PAS 支撑，函数名保留 pandora_ 前缀 */

/* 在 sweet_ufs_init() 里： */
lafa_gpu_init();
pandora_adsp_init();   /* 仅当 GPU 需要 zap 认证时；audio 部分可后续再开 */
```

> 注意：`lafa_adsp.c` 里的公共函数名保留 `pandora_` 前缀（`pandora_scm_call`、
> `pandora_pas_load_auth`），因为 `lafa_gpu.c` 的 extern 声明就是这个名字。
> 这是跨文件的稳定 ABI，不要改。

## 四、编译宏

所有 lafa 驱动文件都需定义 `-DLAFA`（原来 pandora 用 `-DPANDORA`）：

```
-DLAFA
```

## 五、GPU 固件打包（PANDFW01）

`pandora_fw_read()` 读的不是 vendor 分区，而是打进 boot.img 的**自制固件包**
（"PANDFW01" 格式，见 `tools/mkfwpack.py`）。

### 步骤

1. 从 lafa 提取 GPU 固件（需 root 或 TWRP，`/vendor/firmware/` 下）：

   ```bash
   adb shell su -c 'ls /vendor/firmware/gen80200_*'
   # gen80200_gmu.bin  gen80200_sqe.fw  gen80200_zap.mbn
   adb pull /vendor/firmware/gen80200_gmu.bin .
   adb pull /vendor/firmware/gen80200_sqe.fw .
   adb pull /vendor/firmware/gen80200_zap.mbn .
   ```

   > ⚠️ 注意：GPU 固件在 `/vendor/firmware/`（不是 `/odm/firmware/`），
   > 而 `/vendor` 在 lafa 上是只读分区，普通 `adb pull` 可能读不到。
   > 需要 root（Magisk）或用 `adb shell su -c` 提权读取。

2. 打包成 PANDFW01：

   ```bash
   python3 tools/mkfwpack-lafa.py <固件目录> lafa_fwpack.img
   ```

3. 把 `lafa_fwpack.img` 放进 boot.img 的 payload（由 `unixnu` 打包脚本处理，
   具体挂载点参考 pandora 的 `tools/mkfwpack.py` 使用方式）。

## 六、ADSP 音频的差异（后续处理）

`lafa_adsp.c` 里捆绑了 ADSP 音频 bring-up（SMEM/SMP2P/GLINK/GPR + 扬声器 TDM）。
这部分是板级相关的，lafa 与 pandora 有差异：

| 项 | pandora | lafa |
| --- | --- | --- |
| ADSP carveout 大小 | 0x5580000 | 0x5000000 |
| 扬声器 TDM GPIO | 122-125 | 需从 lafa dtbo 确认 |
| 音频 codec | （pandora 的） | tfa98xx（`proprietary-firmware/audio/tfa98xx.cnt`） |

这些**不影响 GPU**，只影响音频。当前先把 `pandora_adsp.c` 的 SCM/PAS 部分用起来
（GPU zap 认证必需），音频部分留待后续单独适配。

## 七、核对清单（刷机前）

- [ ] `bsd/conf/files` 注册了 lafa_gpu.c / lafa_adsp.c / ArmSmmu4K* 共 7 个文件
- [ ] `sweet_ufs.c` 里调用了 `lafa_gpu_init()` 和 `pandora_adsp_init()`
- [ ] 编译加 `-DLAFA`
- [ ] 提取了 3 个 GPU 固件并打成 PANDFW01 包
- [ ] 固件包放进了 boot.img payload
- [ ] vbmeta 已处理（见 `vbmeta处理说明.md`）
