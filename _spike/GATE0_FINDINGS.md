# Gate 0 — IFC Fixture Spike findings

> 目的：在写任何主链代码前，确认真实 IFC 样本到底能不能支撑 R1/R2/R3 需要的字段。
> 结论优先：**GO**（用 FZK-Haus 作 pinned 真实 fixture），R2 完全支持、R1 部分支持（glazing fraction 缺失是真实、可展示的 review 分支）、R3 按设计走 external/constructed。

## 1. 选定的 pinned fixture（provenance）

| 字段 | 值 |
|---|---|
| 文件 | `data/fixtures/AC20-FZK-Haus.ifc` |
| 来源 URL | https://www.steptools.com/docs/stpfiles/ifc/AC20-FZK-Haus.ifc |
| 原始出处 | KIT / FZK 标准测试模型，ArchiCAD-20 导出（IFC2x3 add-on），FILE_SCHEMA 声明 **IFC4** |
| retrieved (UTC) | 2026-07-18T16:49:40Z |
| SHA-256 | `ea6f04eaf92fac4d7ad0038bc3d2dfea4c094dd3f516ecc33c50bf1835ca108d` |
| 大小 | 2,526,544 bytes |
| license | 公开测试模型；正式引用时补 KIT/FZK 出处说明 |

选它的原因：导出时开了 `IFC Base Quantities: On` / `Window Door Lining and Panel Parameters: On` / `IFC Space boundaries: On`，是少数同时带空间量算 + 窗量算 + space boundary 的公开样本。

对照组（已排除）：官方 PCERT `Building-Architecture.ifc`（IFC4）是 "silly sample scene"，4 个 Space 但**无窗、无 Qto、无 space boundary**，对本项目无用。

## 2. 实测字段覆盖（ifcopenshell==0.8.5 读取，非规范推定）

### 项目单位
- LENGTH = METRE，AREA = SQUARE_METRE，VOLUME = CUBIC_METRE；length scale to m = 1.0。
- 即本 fixture 天然 SI，**不需要单位换算**。→ 单位换算/`UNIT_MISMATCH` 分支需另造一个非 SI 的 fault-injection fixture 才能测到。

### IfcSpace（7 个，全部带量算）
- 量算集名为 **`BaseQuantities`**（不是 `Qto_SpaceBaseQuantities`）→ reader 匹配时要认这个名字或按属性存在性匹配。
- `NetFloorArea` ✓ 全 7 个（如 Schlafzimmer 21.41 m²、Wohnen 25.21 m²、Galerie 74.51 m²）
- `FinishCeilingHeight` ✓ 全 7 个（多数 2.5 m，Galerie 4.0 m）→ **R2 由真实数据完全支持**
- 另有 `GrossFloorArea` / `Height` / `NetVolume` 全 7 个

### IfcWindow（11 个）
- `BaseQuantities.Area` ✓（样本窗 = 2.4 m²，且 = OverallWidth×OverallHeight = 2.0×1.2）
  → 证实设计的警告成立：**这是窗外框/洞口面积，不是玻璃面积**。
- `Pset_WindowCommon` 存在，但 `GlazingAreaFraction` = **None（缺失）** → 无法从 Area 推出玻璃面积。
- 无 `Qto_WindowBaseQuantities` 命名集。

### Space ↔ Window 关系
- `IfcRelSpaceBoundary` 共 81 条，其中 **window-related = 11** ✓
- 示例：Space `Schlafzimmer` ↔ Window `EG-Fenster-3`（PHYSICAL / EXTERNAL）。
  → R1 需要的「窗属于哪个房间」关系**真实可读**。

## 3. 每条规则的 Gate 0 判定

| 规则 | 需要的字段 | 真实 fixture 能否支持 | 结论 |
|---|---|---|---|
| **R2** finished height ≥ 2.5m | `FinishCeilingHeight` + 单位 | ✓ 全部房间有，SI 单位 | **真实数据可硬判**；多为 2.5=2.5 边界相等，真实 fail 需 controlled case |
| **R1** glazing ratio ≥ 0.10 | 房间 `NetFloorArea` + 玻璃面积 + 窗-房间关系 | 楼面积 ✓、窗-房间关系 ✓、窗 Area ✓；**但 `GlazingAreaFraction` 缺失** | **部分支持**：真实数据上 R1 正确路由到 `needs_review`（缺 glazing fraction / 关系需确认）——正是设计要展示的诚实分支；确定性 pass/fail 用 controlled case 补 |
| **R3** travel distance ≤ 30m | 疏散距离 + UC3/exit context | IFC 不直接提供（符合预期） | 按设计走 `external_precomputed` / `constructed_case`，不碰几何 |

## 4. Go / Fallback 结论

**GO。** 采用「真实 pinned fixture + 受控 case」双层数据分层：

- `pinned_ifc`（FZK-Haus）：证明能读真实 IFC 的 Space 楼面积、finished height、窗 Area、窗-房间 boundary、SI 单位与 provenance。
- `controlled_ifc` / `constructed_case`：补 R1 玻璃面积/比值、R2 真实 fail、R3 疏散距离，以及 4 个 fault-injection（source hash / 单位 / 必需字段 / 窗-空间关系）。

**这不是数据不足的退让，而是一个更强的诚实故事**：在真实模型上，R1 因为缺 `GlazingAreaFraction` 而正确地停下来交人复核，而不是伪造一个 glass area 硬判——这正好演示「我知道 model 读到的数字不等于法规可用事实」。

## 5. 给 Day 1 的实现备注

1. reader 匹配量算集要认 `BaseQuantities`（ArchiCAD 命名），不要只认 `Qto_SpaceBaseQuantities`。
2. 窗 `Area` 只能当 outer opening area；缺 `GlazingAreaFraction` 时按 `MISSING_DATA` / `RELATIONSHIP_UNVERIFIED` 走 review，绝不用 Area 当 glass area。
3. 单位换算分支测不到（本 fixture 全 SI），需单独造非 SI fault fixture。
4. 每个读出的量都要带 provenance：model SHA-256 = `ea6f04...`、GlobalId、property path（如 `BaseQuantities.NetFloorArea`）、raw/SI 值与单位。
