# lafa UFS 上电序列移植方案

## 背景与现状

lafa 内核（source_only）已能在真机启动，`native-ufs-probe=2`（`inspect`）已证实
SM8850 的 UFS HC（0x1d84000）和 GCC（0x100000）寄存器**可映射、可读**，且
`hcs=0x02000009` 是真实状态值。

但 ABL 退出时把 UFS 彻底下电了：

```
gdsc = 0x004d2200   bit31=0 → UFS PHY 电源域下电
hce  = 0x00000000  → 控制器未使能
```

而 `NativeUfs`（`drivers/NativeUfs/NativeUfs.cpp`）**不含任何上电代码**，它
`hostStopQueue` 第一步就要求 `read32(hc,0x34)&1 == 1`（HCE 已使能），因此所有读
数据路径（adopt/hostBringUp/root）在 lafa 上都会在 "controller not ready for
takeover" 处失败。

sheng 靠私有 `libShengPlatformPower.a`（`sheng_pmgr_run`）绕过，该 .a 不在公开
源码。lafa 必须自己实现。

## 上电序列（需移植的内容）

参考 Linux `drivers/ufs/host/ufs-qcom.c` 的 `ufs_qcom_power_up_sequence` +
`drivers/phy/qualcomm/phy-qcom-qmp-ufs.c` 的 `qmp_ufs_enable_phy`。

### 第 1 步：GCC 时钟上电（简单，寄存器已确认）

写 `GCC_BASE (0x100000)` 下的寄存器：

- `GCC_UFS_PHY_GDSCR`（0x77004）：写 bit31=1 上电 UFS PHY 电源域，轮询等 bit31 回读为 1
- `GCC_UFS_PHY_AHB_ENABLE`（0x77024）：写 bit0=1，清 bit31（CLK_OFF）
- `GCC_UFS_PHY_AXI_ENABLE`（0x77018）：同上
- 参考 `NativeUfs::inspect` 里的 `busClocks` 判断：
  `!(axi & 0x80000000) && (ahb & 0x1) && (axi & 0x1)`

注：`inspect` 里 `gcc = mapPhys(GCC_BASE + 0x77000)`，读 `GDSCR - 0x77000 = 0x4`，
即 `gcc[0x4]` = GDSCR。写回也走同样映射。

### 第 2 步：QMP UFS PHY 校准（最难，数据已齐）

PHY 基址 = `0x1d80000`（`ufsphy_mem@1d80000`，`reg = phy_mem`）。

SM8750（lafa SM8850 同代）的 PHY 配置（已存 `references/ufs-phy/`）：

- compatible = `qcom,ufs-phy-qmp-v4-canoe`
- `.offsets = qmp_ufs_offsets_v6`：serdes=0x0, pcs=0x400, tx=0x1000, rx=0x1200
- `.regs = ufsphy_v6_regs_layout`：
  - PHY_START = QPHY_V6_PCS_UFS_PHY_START = 0x000
  - PCS_READY_STATUS = 0x1a8
  - SW_RESET = 0x008
  - POWER_DOWN_CONTROL = 0x004

寄存器表（偏移+值，均在 `phy-qcom-qmp-ufs.c` 的 `sm8750_ufsphy_*` 数组里）：

- `sm8750_ufsphy_serdes[]`（37 项，PLL/VCO 校准）
- `sm8750_ufsphy_tx[]`（3 项）
- `sm8750_ufsphy_rx[]`（约 52 项，UCDR/速率相关）
- `sm8750_ufsphy_pcs[]`（10 项）+ g4_pcs + hs_b_pcs

校准流程（Linux `qmp_ufs_enable_phy` 的简化）：

1. 写 serdes 表（PLL 配置，相对 serdes 基址 0x0）
2. 写 tx/rx 表（相对 tx=0x1000 / rx=0x1200）
3. 写 pcs 表（相对 pcs=0x400）
4. 释放 SW_RESET，写 PHY_START
5. 轮询 PCS_READY_STATUS

寄存器宏偏移值已存 `references/ufs-phy/phy-qcom-qmp-qserdes-com-v6.h`
（QSERDES_V6_COM_*）、`phy-qcom-qmp-pcs-ufs-v6.h`（QPHY_V6_PCS_UFS_*）、
`phy-qcom-qmp-qserdes-txrx-ufs-v7.h`（QSERDES_UFS_V7_TX/RX_*）。

### 第 3 步：HCE 使能（中等，UFS 规范标准序列）

写 `UFS_HC_BASE (0x1d84000)`：

- 写 0x34 bit0=1（HCE enable）
- 轮询 0x34：HCE 会经历 1→0→1（控制器初始化）
- 轮询 0x30（HCS）等 UTMRLRDY/UTMRLS 就绪（bit 2/1）
- 之后 NativeUfs 的 `hostBringUp` 可复用

## 参考实现位置

`references/ufs-phy/`：

- `phy-qcom-qmp-ufs.c` — 完整 QMP UFS PHY 驱动（含 sm8750 表）
- `phy-qcom-qmp-qserdes-com-v6.h` — serdes 寄存器宏
- `phy-qcom-qmp-pcs-ufs-v6.h` — PCS 寄存器宏
- `phy-qcom-qmp-qserdes-txrx-ufs-v7.h` — TX/RX 寄存器宏

## 关键风险提示（soc-porting.md:367 原文）

> Even reading MMIO from an unpowered peripheral can stall the bus.

所以顺序必须严格：先上电 GDSCR，再碰 PHY/HC 寄存器。绝不能在未上电时读写。

## 分阶段实现建议

1. **先只做第 1 步 + 第 3 步**（GCC 上电 + HCE 使能），跳过 PHY 校准。
   依据：Linux 补丁系列（Nitin Rawat）提到 "UFS PHY registers are retained after
   power collapse"，PHY 校准状态可能保留。若 HCE 使能后控制器能起来、NOP OUT
   能通，就省掉最难的 PHY 校准。
2. 若第 1 步后 NOP OUT 失败，再补第 2 步的完整 PHY 校准。

## 现状对照

- `NativeUfs.cpp` 已实现：inspect（读）、adopt（接管）、hostBringUp（SMMU bypass +
  request list + 读数据）。缺的只是**上电前置**。
- 最小改动：在 `hostBringUp` 入口前，加一个 `powerOnUfs()`（第 1 步 + 可选第 2 步 + 第 3 步），
  成功后再走现有逻辑。
