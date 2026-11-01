# lafa vbmeta 校验处理说明

> 目标：让 lafa（realme GT8 Pro，SM8850）能刷入并引导自定义 UEFI boot.img。
>
> 背景：fastboot 显示 `unlocked=yes`（BL 已解锁）+ `secure=yes`（AVB/vbmeta 校验仍开启）。

---

## ⚠️ 先读这一节：调试阶段不要碰 vbmeta

**`fastboot boot` 是从 RAM 启动，不写入任何分区，也不经过 vbmeta 校验链。**
因此调试自定义 UEFI 时**完全不需要禁用 vbmeta**：

```bash
fastboot boot out/lafa/boot.img    # 只需要这一条
```

崩溃 / 卡死 → 长按电源键 15-20 秒 → 自动回到原 Android 系统。零写入，零变砖风险。

### 2026-10-30 变砖事故记录（血的教训）

按本文件旧版「方式 A」执行后，设备无限重启并掉入 EDL(9008)，最终送 realme 售后用
官方 MSM 工具才救回。具体踩了三个坑：

| 坑 | 说明 |
| --- | --- |
| `avbtool` 生成小端 vbmeta | OPPO/realme 的 vbmeta 字段是**大端**，`--flags 2` 直接生成的小端镜像会被 bootloader 判为损坏 |
| A/B 两个槽都刷 | 把唯一的退路也写坏了，无法 `set_active` 回滚 |
| 改 vbmeta 本身 | vbmeta 一旦校验不过，bootloader 会在 PBL/ABL 阶段直接拒绝引导并落 EDL，fastboot 再也进不去 |

**结论：只有确认「必须真刷 boot 分区」时才读下面第二章之后的 vbmeta 操作，
且必须只刷一个槽、并先用 `fastboot boot` 验证镜像能起来。**

---

## 一、原理（仅在你确实要真刷 boot 时才需要）

Android Verified Boot (AVB) 用 `vbmeta` 分区保存 boot/vendor_boot 等分区的哈希与签名链。
`secure=yes` 表示 bootloader 会校验这些哈希。刷自定义 UEFI 镜像后哈希不匹配，设备会拒绝引导。

禁用方式：给 vbmeta 分区打上 **`--disable-verity` + `--disable-verification`** 标志，
让 bootloader 跳过 boot 分区的哈希校验（但保留签名结构，BL 仍能接受）。

## 二、前置条件

1. 已解锁 BL（`unlocked=yes` ✅ 已满足）
2. 有原厂 vbmeta 镜像（从 lafa 的 OTA 包 / 原厂固件提取）
3. Android SDK 的 `fastboot` 和 `avbtool`

## 三、提取 vbmeta 镜像

lafa 是真我设备，原厂固件可从 realme 官方或 oppo 社区获取。从固件包提取：

```bash
# 如果下载的是 payload.bin（A/B OTA），用 payload-dumper-go 解包
# 得到 vbmeta.img、boot.img、vendor_boot.img 等

# 或者直接从已 root 的手机提取（需要 root）
adb shell su -c 'dd if=/dev/block/by-name/vbmeta_a of=/sdcard/vbmeta_a.img'
adb pull /sdcard/vbmeta_a.img .
```

> ⚠️ lafa 的 fastboot 不支持读分区（无 `fetch`/`get_stored`），所以只能从
> 原厂固件包或已 root 的系统提取，不能直接 `fastboot fetch vbmeta`。

## 四、禁用校验并刷入

### 方式 A：刷入带禁用标志的 vbmeta（⚠️ 高风险，2026-10-30 曾因此变砖送修）

```bash
# 1. 用 avbtool 给 vbmeta 加禁用标志
avbtool make_vbmeta_image \
  --flags 2 \
  --padding_size 4096 \
  --output vbmeta_disabled.img

# 注：--flags 2 即 AVB_VBMETA_IMAGE_FLAGS_VERIFICATION_DISABLED（禁用校验）
#     也可用 --flags 3（同时禁用 verity 和 verification）

# 2. 只刷当前槽位！另一个槽保持原厂作退路
#    fastboot getvar current-slot  先确认为 a 还是 b
fastboot --disable-verity --disable-verification flash vbmeta_a vbmeta_disabled.img

# 3. 刷自定义 boot（同样只刷当前槽）
fastboot flash boot_a boot.img
```

> ### 🔴 avbtool 输出端序问题（必读）
>
> `avbtool` 生成的是**小端**（little-endian）结构，而 **OPPO/realme 的 vbmeta 字段使用大端**。
> 直接把 `avbtool` 的产物刷进去，bootloader 会判为镜像损坏 → 拒绝引导 → 无限重启 → 落 EDL。
>
> 确认真实端序的方法：检查原厂 vbmeta 前 4 字节之后的字段。lafa 原厂 vbmeta 的
> `flags` 字段读取结果是 `0`（验证开启），且结构为大端。若要生成可用的禁用镜像，
> 必须先把 avbtool 输出按字段做字节序翻转，或直接用十六进制改原厂 vbmeta 的 flags 字段。
>
> 上次变砖就是漏了这一步。**没有验证过端序之前，不要刷任何自制 vbmeta。**

### 方式 B：直接 flash 时加禁用参数（部分设备支持）

```bash
fastboot --disable-verity --disable-verification flash boot boot.img
```

> ⚠️ 真我/OPPO 设备的 fastboot 对 `--disable-verity` 支持不完整，方式 A（直接刷
> 空 vbmeta）更可靠。

### 方式 C：刷空 vbmeta（最粗暴，但最有效）

如果手头没有原厂 vbmeta，可以刷一个**空 vbmeta**（无任何分区描述符），bootloader
会因为没有可校验的 boot 描述符而跳过校验：

```bash
# 生成空 vbmeta
avbtool make_vbmeta_image --output vbmeta_empty.img

fastboot --disable-verity --disable-verification flash vbmeta_a vbmeta_empty.img
fastboot --disable-verity --disable-verification flash vbmeta_b vbmeta_empty.img
fastboot reboot bootloader
```

## 五、验证

刷完后重新进入 bootloader，确认状态：

```bash
fastboot getvar all 2>&1 | grep -E "secure|unlocked|verified"
# 期望 secure=no（或 verifiedbootstate=orange）
```

- `verifiedbootstate=green` → 校验通过（原厂状态）
- `verifiedbootstate=orange` → 已解锁/校验禁用（**刷自定义 UEFI 后的正常状态**）
- `verifiedbootstate=yellow` → 校验失败但允许引导（部分设备）
- `verifiedbootstate=red` → 校验失败拒绝引导（需重新处理 vbmeta）

## 六、临时引导 vs 刷入

lafa 的 fastboot 支持 `fastboot boot boot.img`（临时引导，不写入分区）。

- **临时引导**（`fastboot boot`）：如果 vbmeta 校验已经禁用，可以直接 `fastboot boot`
  测试自定义 UEFI，重启后回到原系统，**更安全**，推荐先这么测。
- **刷入**（`fastboot flash boot`）：确认能引导后再刷入，避免变砖。

## 七、风险与恢复

1. **变砖风险**：如果 vbmeta 刷错导致无法引导，可以 `fastboot flash vbmeta` 刷回
   原厂 vbmeta 恢复。
2. **数据备份**：刷机前备份重要数据（虽然禁用 vbmeta 不清数据，但刷 boot 有风险）。
3. **A/B 槽位**：lafa 是 A/B 设备，注意刷对槽位（`fastboot getvar current-slot`
   查看当前槽位）。临时引导用 `fastboot boot` 会自动处理槽位。

## 八、与刷机流程的整合

完整刷机顺序：

```bash
# 1. 禁用 vbmeta（只需做一次）
fastboot --disable-verity --disable-verification flash vbmeta_a vbmeta_disabled.img
fastboot --disable-verity --disable-verification flash vbmeta_b vbmeta_disabled.img

# 2. 临时引导测试（推荐先这样）
fastboot boot out/lafa/boot.img

# 3. 确认能引导后，再决定是否刷入
# fastboot flash boot out/lafa/boot.img
```

## 九、待确认项

- [ ] lafa 的 vbmeta 分区名是 `vbmeta_a`/`vbmeta_b` 还是 `vbmeta`（真我 A/B 设备一般是 `vbmeta_a`/`vbmeta_b`，用 `fastboot getvar all` 确认）
- [ ] 原厂 vbmeta 是否包含 vendor_boot 的校验（如果有，vendor_boot 也要一起处理）
- [ ] 真我 fastboot 是否支持 `--disable-verity` 参数（如果不支持，直接用空 vbmeta 方式 C）
