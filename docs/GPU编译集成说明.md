# lafa GPU 驱动编译集成说明

`drivers/adreno/lafa_gpu.c` 是从 data-a-live 的 `pandora_gpu.c` 移植来的完整 Adreno 840 驱动
（GMU 冷启动 → HFI → CP → Metal 用户接口，Level 1–15）。本说明讲清楚如何把它编译进 lafa 的
XNU 内核源码树。

---

## 1. 文件清单与去处

| 本仓库文件 | 内核源码树去处 |
| --- | --- |
| `drivers/adreno/lafa_gpu.c` | `bsd/dev/pandora_gpu.c`（**改名回去**，保持与 pandora 一致，见下） |
| `drivers/adreno/ArmSmmu4K.c` 等 5 个 `.c` | `bsd/dev/adreno/` |
| `drivers/adreno/ArmSmmu4K.h` 等 5 个 `.h` | `bsd/dev/adreno/` |
| `drivers/adreno/lafa_gpu_params.h` | （可选）`bsd/dev/adreno/` 作参数备份 |

> 说明：lafa_gpu.c 已经是**改好 lafa 板级参数**的版本，你可以：
> - 直接把它当 `pandora_gpu.c` 用（内容已改好，函数名/启动参数名仍是 `pandora_gpu*`，无需改调用方）；
> - 或者按下方 `bsd/conf/files` 注册时用 `lafa_gpu.c` 这个名字也行（但 `sweet_ufs.c` 里调用的
>   `pandora_gpu_init()` 符号名不变，所以要 `#include` 对应文件）。

**推荐**：保持文件名 `pandora_gpu.c`（内容和 data-a-live 完全同构），这样后续跟进 data-a-live
的新补丁（0257 之后的）时 diff 最小。

---

## 2. 编译依赖（必须先有这些）

`lafa_gpu.c` 依赖以下符号，必须由内核里已有的文件提供：

| 符号 | 提供者 |
| --- | --- |
| `pandora_scm_call()` | `bsd/dev/pandora_adsp.c`（SCM 调用，GPU_INIT_REGS 用） |
| `pandora_fw_read()` | `bsd/dev/sweet_ufs.c`（读固件包） |
| `pandora_pas_load_auth()` | `bsd/dev/pandora_adsp.c`（zap shader PAS 加载） |
| `ml_io_map_wcomb / ml_io_unmap / ml_io_map_unmappable` | XNU 内核导出 |
| `ArmSmmu4K*`（整套） | `bsd/dev/adreno/*.c`（本仓库已提供） |
| `PANDORA` 宏 | 编译选项（lafa 内核要用 SM8850 平台宏，见下） |

**注意**：`lafa_gpu.c` 整个文件包在 `#if defined(PANDORA)` 里（第 142 行）。lafa 内核编译时要
定义 `PANDORA` 宏（或改用 lafa 自己的平台宏，例如把 `#if defined(PANDORA)` 改成
`#if defined(LAFA)` 并保证 LAFA 已定义）。

---

## 3. 集成步骤（对照 data-a-live 的 fix_0162.py / fix_0165.py）

### 3.1 放文件
```bash
# 假设内核树根是 $TREE
cp drivers/adreno/lafa_gpu.c          $TREE/bsd/dev/pandora_gpu.c
mkdir -p $TREE/bsd/dev/adreno
cp drivers/adreno/ArmSmmu4K*.c        $TREE/bsd/dev/adreno/
cp drivers/adreno/ArmSmmu4K*.h        $TREE/bsd/dev/adreno/
```

### 3.2 注册到 `bsd/conf/files`
```diff
 bsd/dev/pandora_files.c			standard
+bsd/dev/pandora_gpu.c			standard
+bsd/dev/adreno/ArmSmmu4K.c		standard
+bsd/dev/adreno/ArmSmmu4KContext.c		standard
+bsd/dev/adreno/ArmSmmu4KMmio.c		standard
+bsd/dev/adreno/ArmSmmu4KProgram.c		standard
+bsd/dev/adreno/ArmSmmu4KStreams.c		standard
```

### 3.3 在 `bsd/dev/sweet_ufs.c` 里挂 init
```diff
 extern void pandora_files_init(void);
+extern void pandora_gpu_init(void);
```
在 `sweet_ufs_init()` 里（`pandora_files_init()` 之后）：
```diff
 	/* Files from the pinned pack into the root file system (bsd/dev/pandora_files.c). */
 	pandora_files_init();
+	/* Adreno 840 bring-up, boot-arg pandora_gpu (bsd/dev/pandora_gpu.c). */
+	pandora_gpu_init();
```

---

## 4. 固件（必需，否则 level ≥5 起不来）

`lafa_gpu.c` 通过 `pandora_fw_read()` 从固件包（`PANDFW01` 魔数）读这三个文件：

| 固件 | 用途 | 首次需要它的 level |
| --- | --- | --- |
| `gen80200_gmu.bin` | GMU（CM3）固件 | 5 |
| `gen80200_sqe.fw` | CP SQE 微码 | 9 |
| `gen80200_zap.mbn` | zap shader（退安全模式） | 11 |

从 lafa 的 `/vendor/firmware/`（或 `/odm/firmware/`）提取，打进固件包。
SM8850 平台通用，但**优先用 lafa 自己的**（realme 可能打厂商补丁）。

---

## 5. 测试

刷机后，用内核启动参数逐级开启（严格按顺序，每级都要求上一级"前提成立"）：

```
pandora_gpu=1   纯读（先做这个！确认 GCC/GPUCC/SMMU/GMU 读数正常）
pandora_gpu=2   CX 电源 + SMMU 时钟
pandora_gpu=3   GPLL0 投票 + SCM GPU_INIT_REGS
pandora_gpu=4   GMU 的 SMMU 上下文
pandora_gpu=5   GMU 冷启动
pandora_gpu=6   HFI 性能表
pandora_gpu=7   带宽表 + CORE_FW_START + START
pandora_gpu=8   GX 上电
pandora_gpu=9   GPU SMMU 上下文 + SQE
pandora_gpu=10  CP 初始化
pandora_gpu=11  zap，退出安全模式
pandora_gpu=12  间接缓冲
pandora_gpu=13  缓冲池 + 带帧提交
pandora_gpu=14  用户接口（Metal/Turnip）
pandora_gpu=15  剩余 hw_init
```

**风险（务必遵守）**：
- cfg_ahb 关时读 GPUCC / CX GDSC 关时读 SMMU / 时钟没开时读 GMU → **总线挂死整机复位**。
- GX 没开时读 GPU 寄存器窗口 → 同样挂死。
- 一次读完全部 SMR → 同步异常复位（逐个读）。
- GMU 放出复位后锁死，冷启动失败要整机重启再试。

---

## 6. 许可

- `lafa_gpu.c`：沿用 data-a-live 的 BSD-2-Clause-Patent（文件头已含）。
- `ArmSmmu4K*`：MIT（见 `LICENSE.ArmSmmu4K`）。
- 寄存器数值来自 Linux `a6xx_gmu.c` / `a6xx_catalog.c` / Qualcomm `gen8_reg.h`（GPL-2.0-only），
  只取事实（地址/数值/顺序），不复制代码——与 data-a-live 的许可策略一致（见 `docs/GPU_PORT_MAP.md` 第 5 节）。

---

## 7. 与 data-a-live 后续补丁的同步

data-a-live 的 `xnu/patches/` 里有 0162–0198 等一系列 `pandora-gpu-*.patch`，对应 `pandora_gpu.c`
从 level 1 到 level 15 的演进。lafa 的 `lafa_gpu.c` 已经是**最终态**（含全部 15 级 + DCVS + 中断 +
hang dump + watch）。若 data-a-live 后续有 0257 之后的更新，`git diff` 一下 `pandora_gpu.c`
即可同步。
