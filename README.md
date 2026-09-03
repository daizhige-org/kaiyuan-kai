# 开元楷体 / Kaiyuan Kai SC

一套面向简体中文的合并楷体：字形优先取自文鼎**简中楷**（`gkai00mp.ttf`，GB
字集，原生简体字形），简中楷未覆盖的码位再用 **AR PL UKai** 的 CN face
（`ukai.ttc` 第一个 face）补齐覆盖范围，并在合并后的字体上做了若干优化，
以符合现代字型的实际使用需求。

## 为什么要合并两个文鼎字型

- 简中楷是文鼎最早直接为 GB 字集设计的楷体，字形是简体正字，但字集只有 7,574
  个码位，覆盖范围不够。
- AR PL UKai 把文鼎的字集统一到 Unicode，四个 face（CN/HK/TW/TW MBE）覆盖两三
  万字，但四个 face 字形几乎完全相同，基本沿用**文鼎中楷 Big5**的台湾字形，
  包括名字叫 "CN" 的那个 face 在内，并不是中国大陆字形楷书（对照见
  `arphic-ukai/README.md`）。若直接以 UKai CN 作为简体楷体使用，会有不少字形
  错误。
- 因此确定的规则是：**简中楷有的码位一律用简中楷的字形；简中楷没有的码位，
  才用 UKai CN 补齐**——UKai 只负责扩大覆盖范围，不会覆盖简中楷已有的正确
  简体字形。

当前统计：简中楷 7,574 码位（100% 采用）+ UKai CN 补上的 16,301 码位 = 共
23,875 码位。

## 相比文鼎原版做了哪些改进

字形轮廓本身未作改动（少数标点的墨迹位置除外，见下），主要工作是将两套原本
互不相干的字体拼合，并修复了合并过程与上游本身带来的一系列问题：

- **字集合并**：如上——将简中楷的正确简体字形与 UKai 的覆盖范围拼合为一套
  字形正确且字集充足的楷体。
- **破折号 / 省略号接续**：简中楷原始的 `—`、`…` 笔画左右均留有空白，连续
  使用两个（`——`、`……`）时接缝处会出现明显断档。已改为让笔画/点阵贴边、
  按六等分点重新定位，连接后为一整条不间断的线、六个点间距均匀——仅移动了
  已有轮廓的位置，未重新绘制笔画。
- **标点纵向位置**：简中楷将所有标点的墨迹留在字身格子内部、从不越过基线，
  属于较旧式的排版惯例。参照系统楷体字形，将 `、。，；：！？` 下移至基线
  以下、引号 `“”‘’` 上移至接近字面顶部，以贴近现代简体排版习惯。同样仅作
  平移，未改动笔画本身。
- **`halt` 半宽标点压缩（新增特性）**：默认字形保持满格等宽（这才是中文字体
  应有的安全默认值），标点压缩改为可选的 OpenType `halt` 特性——Word 的"标点
  挤压"、InDesign 等支持该特性的排版软件开启后，标点会自动收窄并贴紧前后
  文字；不支持的软件不受影响，仍显示满格。相关数值并非主观设定，而是从苹果
  系统自带的 Hiragino Sans GB 中实测所得，并按 unitsPerEm 换算得出。
- **垂直度量表**：`fontTools.merge` 将两个上游字体的 `hhea`/`OS/2`/`vhea` 合
  并为自相矛盾的组合（拼接自两套原本各自自洽的设计），导致 Word 中文档网格
  行距直接翻倍。已改为统一的、与系统参照字体同一比例的严格数值。
- **清理排版表**：简中楷没有、UKai 有但本项目用不到的 `GSUB`/`GPOS`/
  `GDEF`（IVS、日语排版特性等），`fontTools.merge` 合并后产生的版本几乎是空
  表，会被 macOS/CoreText 直接拒绝注册，因此整体移除，只保留自行编写的那张
  干净的 `halt` GPOS 表。
- **`meta` 表**：两个上游均没有此表。现已声明 `dlng=zh-Hans`（表明该字体是
  为简体中文设计的），`slng` 则是用 [hyperglot](https://github.com/rosettatype/hyperglot)
  实测这套合并字集真正覆盖的 373 种语言得出的，而非照搬其他字体的清单。
- **改名**：不叫「文鼎」「AR PL」，见下面 License 一节。

详细排查过程见 [`doc/word-line-spacing.md`](doc/word-line-spacing.md) 和
[`doc/punctuation-placement.md`](doc/punctuation-placement.md)。

## License

两个上游字型都是 Arphic Technology Co., Ltd. 在 **Arphic Public License**
（见 `ARPHICPL.TXT`）下发布的作品。该 license 第 2 条明确允许修改字形、合并、
改名再散布，条件是：

- 2(a) 在每个改动过的文件里注明如何、何时改动过——见下方「修改说明」。
- 2(b) 改动后的版本必须继续以同一份 license「Freely Available」提供给所有人，
  不能收紧授权、不能闭源。

`开元楷体 / Kaiyuan Kai SC` 不叫「文鼎」或「AR PL」——这两个是 Arphic
Technology 的品牌名/商标，版权 license 允许改字形改名，但不等于授权使用对方的
品牌字号；继续用会造成"这是文鼎官方或授权版本"的误解。本项目与 Arphic
Technology 没有从属或授权关系。

build.py 等脚本、文档另按 MIT 授权，见 `LICENSE`。

### 修改说明 / Modification notice

依 Arphic Public License 第 2(a) 条：`kaiyuan-kai-sc.ttf` 与其切片
webfont，由 free-fonts 项目于 2026 年合并生成——字形来自文鼎简中楷
(`gkai00mp.ttf`, 2.11) 与 AR PL UKai 的 CN face (`ukai.ttc`
0.2.20080216.2, font index 0)：简中楷覆盖到的码位一律用简中楷的字形，其余码位
用 UKai CN 补上。没有修改任何字形轮廓本身，只做了 cmap／字符集合并、按
Unicode 码位子集切片，以及 name table 改名。

## 用法

```html
<link rel="stylesheet" href="./kaiyuan-kai-sc.css">
<style>
body { font-family: 'Kaiyuan Kai SC', cursive, serif; }
</style>
```

CSS 用 256-codepoint `unicode-range` 分片，浏览器只下载页面实际用到的区块
（同 [free-fonts](https://github.com/frankslin/free-fonts) 项目里其它字型
package 的约定）。

## 重新生成

```
pip install fonttools brotli pillow
python3 build.py            # 下载上游字型到 src/，合并、切片
python3 build.py --no-dl    # src/gkai00mp.ttf、src/ukai.ttc 已存在时跳过下载
```

仓库中除 `build.py` 外不需要任何其他输入——上游字型由 `build.py` 自行下载，
`src/` 不纳入版本控制。全新 clone 一份仓库、安装好上述三个 pip 包，运行
`python3 build.py`，即可重新产出与仓库中一致的 `kaiyuan-kai-sc.ttf`。

## 版本号

`VERSION` 文件是唯一的版本号来源——`build.py` 从这个文件读取，写进字体
`name` table 的 Version/Unique ID。发新版时：

1. 修改 `VERSION`（例如 `0.0.1` → `0.0.2`）。
2. 同步修改 `package.json` 的 `"version"` 字段（npm 无法从外部文件读取该
   字段，只能手动保持一致，两处均需修改）。
3. `git tag v0.0.2 && git push origin v0.0.2` 触发下面的 Release workflow——
   CI 会先检查 tag 版本号是否与 `VERSION` 文件一致，不一致则直接失败，以避免
   发布一个内部版本号与 tag 不符的字体。

## Release

`.github/workflows/release.yml`：推送一个 `v*` tag（如 `git tag v0.0.1 && git
push origin v0.0.1`）即会在 CI 中运行上述同一个 `build.py`，将产出的
`kaiyuan-kai-sc.ttf` 与打包好的 webfont zip（`kaiyuan-kai-sc.css` + `fonts/`
+ README/LICENSE/ARPHICPL.TXT）发布到 GitHub Release。也可以在 Actions 页
手动运行一次（`workflow_dispatch`）做不发布的 dry-run，构建产物会作为
workflow artifact 保留。

## 已知问题 / 文档

- [`doc/word-line-spacing.md`](doc/word-line-spacing.md) —— Word 中行距自动
  加倍的排查记录：`fontTools.merge` 按表合并、不检查跨表一致性，导致垂直
  度量表自相矛盾，以及 Word/Office 字体度量缓存的问题。修改 `build_master()`
  中与 `hhea`/`OS/2`/`vhea` 相关的逻辑之前，建议先阅读此文档。
- [`doc/punctuation-placement.md`](doc/punctuation-placement.md) —— 破折号/
  省略号接续断裂、标点纵向位置、`halt` 半宽压缩特性（数值取自 Hiragino Sans
  GB，用 `feaLib` 编译）、`meta` 表 `dlng`/`slng` 语言声明（用 hyperglot 核实
  真实语言覆盖范围）。修改标点相关函数之前，建议先阅读此文档。

## 来源

- 文鼎简中楷: `fonts-arphic-gkai00mp` 2.11 (Debian)
- AR PL UKai: `fonts-arphic-ukai` 0.2.20080216.2 (Debian, CJK Unifonts 项目)
- Upstream license: Arphic Public License（`ARPHICPL.TXT`）
