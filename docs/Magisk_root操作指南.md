# lafa (realme GT8 Pro / RMX5200) Magisk Root 操作指南

> 目标：给 lafa 获取 root 权限，以便后续提取 GPU 固件（`/vendor/firmware/gen80200_*`）、
> dd 读取 vbmeta 分区，最终完成 UniXNU 刷机。
>
> 你的设备信息（已实测采集）：
> - 型号 RMX5200，板级 RE6030L1，Android 16
> - 系统版本 **RMX5200_16.0.10.501(CN01)**，增量 `B.551d65a-2fef12e-2ff294a`
> - ROM V16.1.0，当前槽位 `_b`
> - BL 已解锁（`unlocked=yes`），`secure=yes`（vbmeta 校验开启）

---

## 一、为什么必须 root

| 需要的文件 | 位置 | 无 root 状态 |
| --- | --- | --- |
| GPU 固件 gen80200_* | `/vendor/firmware/` | ❌ `Permission denied` |
| 原厂 vbmeta | `/dev/block/by-name/vbmeta_a` | ❌ 需 dd（要 root） |
| 面板/触控/IRIS 固件 | `/odm/firmware/` | ✅ 已提取（无需 root） |

所以 root 是拿到 GPU 固件和 vbmeta 的唯一途径（除非走 OTA 包解包）。

---

## 二、前提准备

1. **确认 BL 已解锁**（你已满足，`unlocked=yes`）
2. **备份重要数据**（root 过程理论不清数据，但 Magisk 修补 boot 有风险）
3. **下载匹配的原厂固件包**（获取 boot.img，见下）

---

## 三、第 1 步：获取原厂 boot.img

Magisk 修补的是 **boot.img**（或 init_boot.img，SM8850 真我设备是 A/B 分区，boot 分区含 ramdisk）。

你的系统是 `RMX5200_16.0.10.501(CN01)`，**必须下载完全同版本的固件包**，否则 Magisk 修补后可能无法启动。

### 方式 A：从 OTA 全量包解包（推荐）

1. 从 realme 官方 / OPPO 社区下载 lafa 的 **全量 OTA 包**（版本 16.0.10.501 CN01），通常是 `.zip` 或 `.ofp`/`.ozip` 格式。
2. 如果是 A/B 分区设备，包内是 `payload.bin`，用 `payload-dumper-go` 解包：

   ```bash
   payload-dumper-go payload.bin
   # 输出 boot.img、vbmeta.img、vendor_boot.img 等
   ```

   注意：SM8850 设备可能是 `boot.img` + `init_boot.img` 分开，Magisk 修补的是 **boot.img**（含内核+ramdisk 的那个）。

### 方式 B：从已安装系统 dd 提取（需先临时 root）

如果手头有同版本设备的 root，或能用 TWRP，可 `dd if=/dev/block/by-name/boot_a of=/sdcard/boot.img`。但你现在无 root，此路不通，走方式 A。

---

## 四、第 2 步：安装 Magisk 并修补 boot.img

1. 手机上安装 **Magisk** APK（从官方 GitHub `topjohnwu/Magisk` 下载最新版，或 26.x 稳定版）。
2. 把原厂 `boot.img` 传到手机：`adb push boot.img /sdcard/`
3. 打开 Magisk → **安装 → 选择并修补一个文件** → 选 `/sdcard/boot.img`
4. Magisk 会生成 `Magisk-xxxxx_patched-xxxxx.img`（在 `/sdcard/Download/`）
5. 把修补后的镜像拉回电脑：

   ```bash
   adb pull /sdcard/Download/Magisk-*.img magisk_patched_boot.img
   ```

---

## 五、第 3 步：刷入修补后的 boot 并重启

```bash
adb reboot bootloader
# 等待进入 fastboot

fastboot flash boot_a magisk_patched_boot.img
fastboot flash boot_b magisk_patched_boot.img
# 或临时引导测试：fastboot boot magisk_patched_boot.img（不写入，重启失效）

fastboot reboot
```

> ⚠️ **注意 A/B 槽位**：当前槽位是 `_b`。为了保险，两个槽位都刷，或者先
> `fastboot boot`（临时引导）确认能启动再 `fastboot flash`。

---

## 六、第 4 步：验证 root

```bash
adb shell su -c id
# 期望输出 uid=0(root) ...

# 或
adb shell su -c "ls /vendor/firmware/gen80200*"
```

如果 `su -c id` 返回 `uid=0(root)`，说明 root 成功。

---

## 七、第 5 步：root 成功后通知我

root 成功后，**回复我"已 root"**，我会立刻接着用 adb 执行：

1. 提取 GPU 固件 `gen80200_gmu.bin` / `gen80200_sqe.fw` / `gen80200_zap.mbn`
2. dd 读取 vbmeta_a/vbmeta_b，准备禁用校验
3. 打包 PANDFW01 固件包
4. 继续刷机流程

---

## 八、风险与回滚

| 风险 | 应对 |
| --- | --- |
| 刷错 boot 导致不开机 | 用原厂 boot.img `fastboot flash boot` 刷回 |
| Magisk 版本不兼容 | 换 Magisk 26.x 稳定版 |
| 固件包版本不匹配 | 严格用 `RMX5200_16.0.10.501(CN01)` 同版本 |

> ⚠️ 关键：**务必用与你系统完全一致的固件版本**（16.0.10.501 CN01）。版本错配是
> root 变砖的最常见原因。

---

## 九、备选：免 root 走 OTA 包解包

如果你不想 root（或 root 遇到困难），还有一个免 root 方案：**从 OTA 全量包里直接
解包 GPU 固件和 vbmeta**。GPU 固件在 OTA 包的 `vendor.img` 里，vbmeta 本身就是独立分区。

如果走这条路，**回复我"走 OTA 解包"**，并告诉我你下载的固件包路径，我直接写脚本
帮你解包提取，全程不动手机系统。
