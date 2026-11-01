# lafa (realme GT8 Pro) GPU 驱动移植对照表

> Adreno 840 → data-a-live `pandora_gpu.c` 的板级参数移植。
> 结论先行：**SM8850 平台硬件 IP 完全一致，90% 的代码直接复用**，只需改频点表、chipid 和带宽表这三处硬编码。

---

## 0. 一句话结论

`pandora_gpu.c`（3665 行，已验证跑通 GMU 冷启动 → HFI → CP → Metal）在 lafa 上**不需要重写**。把下面 4 处硬编码参数换成 lafa 的值即可，其余全部通用。

已生成好直接可用的参数头：`drivers/adreno/lafa_gpu_params.h`。

---

## 1. 必须改的参数（4 处）

| # | pandora_gpu.c 位置 | pandora 值 | lafa 值 | 依据 |
|---|---|---|---|---|
| 1 | `gpu_opps[]`（第 1018 行附近，18 档） | 18 档，最高 1200 MHz | **17 档，最高 1050 MHz**（见 `lafa_gpu_params.h`） | lafa_full.dts:8585-8738 |
| 2 | `gmu_opps[]`（第 1024 行附近，4 档） | 475/575/700/750 MHz | **2 档：475 / 700 MHz** | lafa_full.dts:18118 |
| 3 | `gpu_ddr_kbps[]`（第 1247 行附近，11 档） | pandora 数值 | **lafa 数值**（见 `lafa_gpu_params.h`） | lafa_full.dts:8528 |
| 4 | `gpu_chip_id`（第 2358 行 `= 0x44050a01u`） | 0x44050a01 | **0x44050a00** | lafa_full.dts:8540 |

**注意**：`gpu_chip_id` 的初值只在 level 14 之前有用；level 14 里那段
`gpu_chip_id = 0x44050a01u | (popcount(slices) << 4)` 是运行期动态算的，**那个 `0x44050a01` 也要一起改成 `0x44050a00`**，否则用户态拿到的 chip id 会错。

---

## 2. 派生参数（改完上面 4 处后会自动正确，但要检查常量）

| 项目 | 说明 | 需改？ |
|---|---|---|
| `#define NGPU` | `1 + sizeof(gpu_opps)/sizeof(...)`，会自动变成 18 | 否（自动） |
| `#define NGMU` | 会自动变成 3 | 否（自动） |
| `gpu_opp_bw[]`（第 3388 行） | DCVS 每档 bus-freq 索引，lafa 是 17 个元素，要替换 | **是**（见 `lafa_gpu_params.h` 的 `lafa_gpu_opp_bw`） |
| `DCVS_INITIAL`（第 3381 行） | pandora = 3（222 MHz）；lafa initial-pwrlevel 0x0e=14（从 0 计）也是 222 MHz → **升序数组里 222 MHz 是第 3 档**，值不变 | 否（碰巧一致） |
| `_Static_assert(sizeof(gpu_opp_bw) == NGPU-1)` | 会校验 `gpu_opp_bw` 是 17 个元素 | 否（自动） |
| `GPU_ZAP_PA 0x9959a000` | lafa gpu_microcode_region 相同 | 否 |
| `GMU_CHIPID 0x08020100` | 相同 | 否 |

---

## 3. 完全不用改的部分（已验证，SM8850 通用）

这些是 `pandora_gpu.c` 里占绝对大头的逻辑，lafa 与 pandora 一字不差：

- **寄存器地址**（第 177-216 行）：`GCC_PA 0x100000`、`GPUCC_PA 0x3d90000`、`SMMU_PA 0x3da0000`、`GPU_PA 0x3d00000`、`GMU_PA 0x3d37000`、`GMU_SIZE 0x68000`、`CMDDB_PA 0x81c60000` —— 全部一致。
- **GMU 寄存器 dword 偏移**（第 744-769 行）：ITCM/DTCM_START、SYSRESET、FW_INIT_RESULT、HFI_*、GENERAL_8/9/10、CX_FAL、围栏等 —— A8XX 统一。
- **GMU 冷启动流程**（`gpu_level5`）：FAL veto、固件装载、HFI 队列表、配置、放复位、轮询 FW_INIT_RESULT —— 全平台通用。
- **HFI 传输 + 性能表/带宽表生成**（`hfi_send`、`gpu_level6`、`gpu_level7`）：协议与算法通用。
- **SMMU 上下文**（`smmu_ctx_up`，基于 ArmSmmu4K）：bank/ASID/流号/ACTLR 0x32b —— 一致（lafa_full.dts:17176）。
- **CP 初始化**（`gpu_level10` ~ `gpu_level15`）：CP_ME_INIT、SQE、zap、a840_nonctxt 寄存器表、protect 表、UBWC —— 全部是 Adreno 840 IP 层，通用。
- **用户接口**（`pandora_gpu_open/bo_alloc/submit/...`，`gpu_level14`）：NativeAdreno ABI 层，通用。

---

## 4. lafa 特有但暂不影响 GPU 的事（非本次范围）

- **显示**：lafa 有 Pixelworks IRIS7P 画质芯片（`proprietary-firmware/display/iris7p.fw`），但 UniXNU 走 UEFI GOP + Adreno 合成 + CPU 拷屏，IRIS7P 可绕过，降级为后续优化项。
- **触控**：Synaptics S3910（SPI），与 GPU 无关，单独适配。
- **PMIC**：pmh0101 + 双 pm8010，与 GPU 上电无关（GMU 自己管 CX/GX 电源域）。

---

## 5. 移植步骤（照着做）

1. 把 `pandora_gpu.c` 复制进 lafa 的 XNU 树，位置 `bsd/dev/pandora_gpu.c`（或沿用 data-a-live 的目录结构）。
2. `#include "adreno/lafa_gpu_params.h"`，用 `lafa_gpu_opps` / `lafa_gmu_opps` / `lafa_gpu_ddr_kbps` / `lafa_gpu_opp_bw` 替换对应硬编码数组。
3. 改 `gpu_chip_id` 初值 + level 14 里的 `0x44050a01` → `0x44050a00`。
4. 固件 `gen80200_gmu.bin` / `gen80200_sqe.fw` / `gen80200_zap.mbn` 从 lafa 的 `/odm/firmware/` 或 `/vendor/firmware/` 提取（SM8850 通用，pandora 的固件包应该也能用，但建议用 lafa 自己的，因为可能有厂商 patch）。
5. 编译内核，用启动参数 `pandora_gpu=1` 先做**纯读**（只读 GCC/GPUCC/SMMU/GMU 状态，不写任何寄存器），确认读数正常再逐级 `pandora_gpu=2..14`。

---

## 6. 第一次上机的建议顺序

> 严格按 pandora_gpu.c 头部注释里的分级，一级一级来，每级都要求上一级"前提成立"。

```
pandora_gpu=1  纯读：GCC → GPUCC → SMMU（逐个 SMR）→ GMU 状态 → cmd-db
pandora_gpu=2  CX 电源 + SMMU 时钟（写 GPUCC，不碰 GMU）
pandora_gpu=3  GPLL0 投票 + SCM GPU_INIT_REGS
pandora_gpu=4  GMU 自己的 SMMU 上下文
pandora_gpu=5  GMU 冷启动（放复位，读 FW_INIT_RESULT）
pandora_gpu=6  HFI 性能表（第一条消息，看 GMU 是否 ACK）
pandora_gpu=7  带宽表 + CORE_FW_START + START
pandora_gpu=8  GX 上电（OOB GPU_SET + GX 投票）
pandora_gpu=9  GPU 自己的 SMMU 上下文 + SQE
pandora_gpu=10 CP 初始化
pandora_gpu=11 zap shader，退出安全模式
pandora_gpu=12 间接缓冲
pandora_gpu=13 缓冲池 + 带帧提交
pandora_gpu=14 用户接口（Metal / Turnip 可用）
pandora_gpu=15 剩余 hw_init
```

**风险提醒**（来自 GPU_PORT_MAP.md 第 6 节，务必遵守）：
- 在 `cfg_ahb` 关闭时读 GPUCC、CX GDSC 关闭时读 SMMU、时钟没开时读 GMU，都会导致**总线挂死整机复位**。
- GX 没开时读 GPU 寄存器窗口同样会挂死。
- 一次读完全部 SMR 会在 SM8550 上同步异常复位（要逐个读）。
- GMU 一旦放出复位就锁死，冷启动失败要整机重启才能再试——所以级别 4 只在 1-3 都对上后开。

---

## 7. 固件来源

| 文件 | 用途 | lafa 提取路径 |
|---|---|---|
| `gen80200_gmu.bin` | GMU 固件（CM3） | `/vendor/firmware/` 或 `/odm/firmware/` |
| `gen80200_sqe.fw` | CP SQE 微码 | 同上 |
| `gen80200_zap.mbn` | zap shader（退出安全模式） | 同上 |

lafa 与 pandora 都是 SM8850，这些固件理论上通用；但**强烈建议用 lafa 自己的**，因为 realme 可能打了厂商补丁。若提取不到，再用 pandora 的固件包兜底。

---

## 8. 参考

- `drivers/adreno/lafa_gpu_params.h` — 已生成好的 lafa 板级参数
- `refs/data-a-live-main/wsl/pandora_gpu.c` — 复用主体（3665 行）
- `refs/data-a-live-main/docs/GPU_PLAN.md` — 15 级分级设计
- `refs/data-a-live-main/docs/GPU_PORT_MAP.md` — A740→A840 寄存器差异与风险清单
- `lafa_full.dts` — lafa 设备树（参数来源）
