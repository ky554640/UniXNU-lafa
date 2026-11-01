/*
 * lafa (realme GT8 Pro / RMX5200) Adreno 840 板级参数 —— SM8850 "canoe" 平台。
 *
 * 这些值全部从 lafa 的 /proc/device-tree 反编译得到的 lafa_full.dts 提取，
 * 用于替换 data-a-live (pandora / 小米 17 Pro) 的 pandora_gpu.c 里硬编码的板级参数。
 *
 * 重要结论：lafa 与 pandora 同为 SM8850，GPU 硬件 IP 完全相同，
 * 所以 GPUCC / GMU / SMMU 的寄存器地址、GMU 冷启动流程、HFI 协议、CP 初始化
 * 全部通用，可以直接复用 pandora_gpu.c 的代码。唯一不同的是下面这些
 * 板级频点 / 分级 / chipid 数值。
 *
 * 来源行号对应工作区根目录的 lafa_full.dts。
 */

#ifndef LAFA_GPU_PARAMS_H
#define LAFA_GPU_PARAMS_H

/* ---- chip id ------------------------------------------------------------------------- */
/* kgsl-3d0 qcom,chipid（lafa_full.dts:8540）＝ 0x44050a00，pandora 是 0x44050a01。
 * pandora_gpu.c 里 gpu_chip_id 的初值要改成下面这个值；
 * 而带 slice 数的那一版（0x44050a31）是运行期在 level 14 由 slice mask 动态生成的，
 * 那段逻辑（gpu_level14 里 __builtin_popcount(slices) << 4）不用改。 */
#define LAFA_GPU_CHIP_ID        0x44050a00u

/* GMU chip id（a6xx_catalog.c 的 gmu_chipid，pandora 也是 0x08020100）——不变。 */
#define LAFA_GMU_CHIPID         0x08020100u

/* ---- GPU 频点表（speed-bin 0x0，qcom,gpu-pwrlevels-0）--------------------------------
 * lafa_full.dts:8585-8738。17 档，160 MHz .. 1050 MHz，升序。
 * pandora 是 18 档（speed-bin 0xfc，最高 1200 MHz），所以这个表要整个替换。 */
#define LAFA_GPU_OPP_COUNT      17

static const struct { uint32_t hz, level; } lafa_gpu_opps[LAFA_GPU_OPP_COUNT] = {
	/*  pwrlevel  hz          level  bus-freq  */
	{ 160000000,  0x32 },   /* @16  0x09896800 */
	{ 191000000,  0x33 },   /* @15  0x0b626dc0 */
	{ 222000000,  0x34 },   /* @14  0x0d3b7380 (initial-pwrlevel 0x0e) */
	{ 282000000,  0x36 },   /* @13  0x10cefa80 */
	{ 342000000,  0x38 },   /* @12  0x14628180 */
	{ 382000000,  0x3c },   /* @11  0x16c4db80 */
	{ 422000000,  0x40 },   /* @10  0x19273580 */
	{ 440000000,  0x4c },   /* @9   0x1b7a4d40 */
	{ 500000000,  0x50 },   /* @8   0x1dcd6500 */
	{ 539000000,  0x60 },   /* @7   0x20207cc0 */
	{ 578000000,  0x80 },   /* @6   0x22739480 */
	{ 646000000,  0x90 },   /* @5   0x26812d80 */
	{ 726000000,  0xc0 },   /* @4   0x2b45e180 */
	{ 826000000,  0xe0 },   /* @3   0x313bc280 */
	{ 902000000,  0x100 },  /* @2   0x35c36d80 */
	{ 966000000,  0x140 },  /* @1   0x39a33fc0 */
	{ 1050000000, 0x1a0 },  /* @0   0x3e95ba80 */
};

/* qcom,gpu-pwrlevels-0 里每档的 qcom,bus-freq 索引（升序，对应上表）——
 * 用于 pandora_gpu.c 的 gpu_opp_bw[]（DCVS 每档带宽投票）。 */
static const uint8_t lafa_gpu_opp_bw[LAFA_GPU_OPP_COUNT] = {
	1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 5, 5, 7, 7, 7, 11,
};

/* 初始频点：qcom,initial-pwrlevel = 0x0e（第 14 档，从 0 计）＝ 222 MHz。
 * pandora_gpu.c 的 DCVS_INITIAL 常量（pandora 也是 222 MHz）——不变。 */

/* ---- GMU 频点表（qcom,gmu@3d37000 qcom,gmu-freq-table）-------------------------------
 * lafa_full.dts:18118。只有 2 档，pandora 有 4 档（475/575/700/750 MHz），要替换。 */
#define LAFA_GMU_OPP_COUNT      2

static const struct { uint32_t hz, level; } lafa_gmu_opps[LAFA_GMU_OPP_COUNT] = {
	{ 475000000, 0x38 },   /* 0x1c4fecc0 */
	{ 700000000, 0x80 },   /* 0x29b92700 */
};

/* ---- DDR 带宽表（qcom,bus-table-ddr）--------------------------------------------------
 * lafa_full.dts:8528，KBps，12 档，数值与 pandora 几乎相同（仅 6671875 vs 6672899 差 1 MiB）。 */
#define LAFA_DDR_BW_COUNT       12

static const uint32_t lafa_gpu_ddr_kbps[LAFA_DDR_BW_COUNT] = {
	0, 2136718, 5285156, 6074218, 6671875, 8171875, 10687500, 12449218, 14398437, 16500000, 18671875,
	20832031,
};

/* ---- a840 BCM 资源（SH0 / MC0 / ACV）—— 与 pandora 相同（a6xx_catalog.c），不变。 */

/* ---- 寄存器基址（全部与 pandora 相同，SM8850 平台通用）------------------------------- */
/* 见 pandora_gpu.c 顶部；这里重复列出以便自查，值都不改：
 *   GCC_PA       0x00100000   GPUCC_PA 0x03d90000
 *   SMMU_PA      0x03da0000   GPU_PA   0x03d00000
 *   GMU_PA       0x03d37000   GMU_SIZE 0x68000
 *   CMDDB_PA     0x81c60000   CMDDB_SIZE 0x20000
 *   RSCC         GPU 基址 + 0x50000 = 0x3d50000（lafa_full.dts:8549 reg "rscc"）
 *   cx_misc      0x3d9e000（lafa_full.dts:8549 reg "cx_misc"）
 *   zap (gpu_microcode_region) 0x9959a000, 8 KiB（lafa_full.dts:458-460）
 */

/* ---- SMMU / 中断 ---------------------------------------------------------------------- */
/* kgsl-smmu@3da0000 qcom,actlr = 0x32b（lafa_full.dts:17176），与 pandora 相同。
 * GMU 流号 5（gmu iommus = <... 0x5 0x0>，lafa_full.dts:18114），相同。
 * GPU 流号 0（gfx3d_user），相同。
 * 中断：kgsl_3d0_irq SPI 0x12c=300，cx_host_irq SPI 0x50=80（lafa_full.dts:8547-8548），
 *       gmu hfi SPI 0x130=304，gmu SPI 0x131=305（lafa_full.dts:18123）——与 pandora 相同。 */

#endif /* LAFA_GPU_PARAMS_H */
