# 排查记录：Word 里行距自动加倍

## 症状

将 `kaiyuan-kai-sc.ttf` 安装到系统并在 Word 中选用后，部分段落的行距会变为
正常值的约两倍，而同一份文档中使用系统自带楷体（"Kai"）的段落则完全正常。
使用一份仅含两段、每段均为同一字符反复排列、字体分别设为 "Kai" 与
"Kaiyuan Kai SC" 的最小测试文档（`test file.docx`）可稳定复现该问题。

## 诊断过程中先后排除的无关因素

以下几点在此次排查中耗费了不少时间，但**最终都不是真正原因**，记录下来
以避免日后重复排查：

- **`fc-list`（FreeType）能正常解析，但 `system_profiler SPFontsDataType` /
  Font Book 却搜索不到该字体**——一度怀疑是 CoreText 拒绝了这个合并出来的
  字体（例如 GSUB/GPOS 表因 `fontTools.merge` 对 OpenType layout 表的合并
  支持不完整，产生了几乎为空的残缺表）。后来发现，即便将**未经任何修改的
  原始 `gkai00mp.ttf`** 复制到 `~/Library/Fonts/`，`system_profiler` 同样
  搜索不到——说明该命令在当时的排查环境中并未实时反映系统里新安装的字体，
  是诊断工具本身不可靠，并非字体的问题。**重启 `fontd`** 之后，Font Book
  立即能够搜索到。→ 教训：安装字体后 Font Book/`system_profiler` 无反应，
  应先怀疑缓存，而非立即怀疑字体文件本身。
- 移除 GSUB/GPOS/GDEF/VORG 这几张从 UKai 继承、内容几乎为空的排版表，是一项
  独立的、值得保留的清理工作（这套字体本身不需要任何替代字形特性），但
  **并非行距问题的成因**。

## 真正的原因

`fontTools.merge` 合并两个字体时，是以表（table）为单位、将整张表从某一个
输入字体中直接搬移过来的，**不会检查两个来源字体中同一类度量表的数值是否
互相兼容**。`gkai00mp.ttf`（簡中楷）与 `ukai.ttc`（UKai）各自的垂直度量表
本来都是自洽的：

| | hhea (ascender/descender/lineGap) | OS/2 typo | OS/2 win |
|---|---|---|---|
| 簡中楷 | 900 / -123 / 6 | 900 / -124 / 80 | 900 / 124 |
| UKai CN | 997 / -133 / 6 | 900 / -124 / 0 | 997 / 133 |

合并之后，`merged["hhea"]` 整张表取自 UKai（997/-133/6），`merged["OS/2"]`
整张表取自簡中楷（typo 900/-124/**80**）——两套各自自洽的设计被拼接成了一个
自相矛盾的新组合，这种组合在两个原始字体中均不存在。

Word 处理**中文文档网格**（`w:docGrid w:type="lines" w:linePitch="…"`，即
Word 中"文档网格：只指定行网格"的设置）时，若某一行按字体度量计算出的行高
超过网格的 `linePitch`，会将该行的高度直接跳升至下一个网格倍数（例如从 1 倍
网格跳到 2 倍），而非平滑地放大——**这是一种离散的阈值行为，而非线性的
渐进变化**。因此，合并后的字体只是比系统自带的 "Kai" 字体的行高数值宽松约
10%，即足以使某些段落从 1 倍网格跳升到 2 倍网格，表现为"行距整体翻倍"。

此步诊断的关键操作：将系统中公认工作正常的参照字体（Apple 系统自带的
`Kai.ttf`，Shanghai Ikarus 出品）的 `hhea` 提取出来对比，发现其数值为
`ascender=1638 descender=-410 lineGap=0`（`unitsPerEm=2048`），换算比例正好是
`(1638+410)/2048 = 1.0`，不留任何余量；且该字体**完全没有 `OS/2` 表**，
Word 只能依据 `hhea` 计算行高。相比之下，合并出的字体 `hhea` 比例为
`(997+133)/1024 = 1.104`，宽松约 10%——这 10% 的差距即是触发网格跳档的原因。

## 修复

在 `build.py` 的 `build_master()` 中，于 `fontTools.merge` 合并完成之后、
写入文件之前，显式将所有垂直度量表**均**设为与参照字体相同的、不留任何冗余的
严格比例——`ascender + |descender| = unitsPerEm`、`lineGap = 0`：

```python
hhea.ascender, hhea.descender, hhea.lineGap = 900, -124, 0
os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = 900, -124, 0
os2.usWinAscent, os2.usWinDescent = 900, 124
os2.fsSelection |= 0x80  # USE_TYPO_METRICS
```

`vhea`（竖排书写用的度量表）存在同样的问题——`ascender` 沿用了簡中楷的 900，
`descender` 沿用了 UKai 的 -1024，拼接出一个在 1024 `unitsPerEm` 的字体中
没有实际意义的负值。这套字体并非用于竖排，因此直接给出一个对称的空数值
（`512/-512/0`），而非保留这种自相矛盾的数据：

```python
vhea.ascent, vhea.descent, vhea.lineGap = 512, -512, 0
```

此前 `hhea`/`OS/2` win 保留了 997/-133 的余量，用途是容纳合并后字符集中少数
超出簡中楷原本范围的字形（带音符拉丁字母、希腊语调号字母、少数罕见 CJK 扩展
字）。全字体扫描（逐个检查各 glyph 的 `yMin`/`yMax`）后发现：

- 落在 `[-124, 900]` 范围之外的字形共计 **49 个**，均为生僻字符
  （`Ḉ Ḝ Ṥ Ç Ş ή Ϊ` 一类带音符拉丁/希腊字母，以及 `爳 嚿 欍 𠍆 𢹸` 一类罕见
  CJK 扩展字），没有一个属于常用汉字。
- 超出幅度很小：`yMax` 最大为 997（仅比 900 多 97），`yMin` 最小为 -133
  （仅比 -124 少 9）。

权衡之下：为避免 Word 网格再次误判，将这 49 个字形笔画最尖端处裁去数个单位
（视觉上几乎无法察觉）是值得的，以换取所有场景下均与参照字体保持同一严格
比例。

同时为字体 `name` table 中的版本号／Unique ID 增加了一个显式的
`FONT_VERSION` 常量，每次实际改动字形或度量表后都需**手动递增版本号**再重新
生成——见下一节。

## 另一个问题：Word/Office 的字体度量缓存

即便字体文件已修正、重新覆盖安装，Word 在一段时间内仍会显示旧的（错误的）
行距。原因是 Word/Office 按 `(字体名, 版本号/Unique ID)` 缓存字体度量数据
（`~/Library/Containers/com.microsoft.Word/Data/Library/Application
Support/Microsoft/FontCache`、`.../FontPreviewCache`，以及
`~/Library/Group Containers/UBF8T346G9.Office/FontCache`），同名同版本号的
覆盖安装未必会使其重新读取文件内容。

解决办法需两步都执行：

1. `build.py` 中的 `FONT_VERSION` 常量，每当度量表或字形有实际变化时手动
   递增（例如 `1.0.2` → `1.0.3`），使 `name` table 中的 Version / Unique ID
   记录随之变化，Word 才更可能将其视为"新字体"重新读取，而非复用旧缓存。
2. 安装字体前退出 Word，删除上述几个缓存目录（均为纯缓存，重新打开 Word 会
   自动重建，不会丢失文档内容），再重新打开 Word 测试。

仅执行其中一步有时并不充分，两步同时执行才可靠。

## 排查方法论小结（可供日后类似问题参考）

1. **先找一个"确认工作正常"的参照字体**，提取其 `hhea`/`OS/2`/`vhea` 数值
   作为基准，而非凭经验猜测各字段应取何值。此次使用的是系统自带的
   `Kai.ttf`。
2. **计算比例，而非只看绝对值**：`(ascender + |descender|) / unitsPerEm`
   ——参照字体是否恰好等于 1.0、`lineGap` 是否为 0，这类整数比例往往正是
   工具链默认假设的安全区间，一旦略微超出，就可能触发某个离散阈值（此次为
   Word 的文档网格）。
3. **`fontTools.merge` 按表合并，不检查跨表一致性**——任何时候用它合并两个
   字体，合并完成后都应主动将 `hhea`/`OS/2`/`vhea` 这几张相互关联的度量表
   逐一检查并统一设为同一套自洽数值，不应信任默认合并产生的组合。
4. **对全字体扫描 `yMin`/`yMax`，以确定哪些字形确实需要更宽松的范围**，
   依据实际数据决定是否为极少数生僻字放宽度量表，而非凭印象判断。
5. **系统级诊断工具（`system_profiler`、Font Book UI）可能存在缓存延迟**，
   字体"看似未安装"应先怀疑缓存（`fontd`），"行为看似异常"应先怀疑应用层
   缓存（Word 的 FontCache）；建议先用一次干净的对照测试（例如未经修改的
   上游字体）确认工具本身是否可信，再转向字体文件本身排查问题。
