#!/usr/bin/env python3
"""Build 开元楷体 / Kaiyuan Kai SC.

A merged Kai typeface for simplified-Chinese use: glyphs come from Arphic's
classic 文鼎簡中楷 (gkai00mp.ttf, GB character set) wherever it has the
character, and from AR PL UKai's CN face (ukai.ttc, font index 0) for every
codepoint 簡中楷 lacks. Rationale: 簡中楷 is the original simplified-glyph
Kai design; UKai's CN face reuses 文鼎中楷 Big5's Taiwan glyph shapes for
characters where PRC/Taiwan forms differ (see arphic-ukai/README.md in the
free-fonts repo), so it is only used to fill in coverage, never to override
a 簡中楷 glyph.

Both upstream fonts are Arphic Technology Co., Ltd. works under the Arphic
Public License; merging and redistributing under that license (see
ARPHICPL.TXT) is explicitly permitted by section 2, provided modifications
are documented (2a) and the result stays Freely Available under the same
license (2b). This is a derivative font, not affiliated with or endorsed by
Arphic Technology; it is not named after Arphic's "AR PL" / 文鼎 marks.

Usage:
    pip install fonttools brotli pillow
    python3 build.py            # download to src/, merge, slice into fonts/
    python3 build.py --no-dl    # skip download (src/*.ttf, src/*.ttc present)
    python3 build.py --jobs N   # explicit parallelism for the slicing step
"""

import argparse
import logging
import tarfile
import tempfile
import urllib.request
from multiprocessing import Pool, cpu_count
from pathlib import Path

from fontTools import subset as ft_subset
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.merge import Merger
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable

logging.getLogger("fontTools").setLevel(logging.ERROR)

ROOT = Path(__file__).parent
SRC_DIR = ROOT / "src"
BUILD_DIR = ROOT / "build_tmp"
FONTS_DIR = ROOT / "fonts"
CSS_PATH = ROOT / "kaiyuan-kai-sc.css"
MASTER_PATH = ROOT / "kaiyuan-kai-sc.ttf"
CHUNK_SIZE = 0x100

GKAI_VERSION = "2.11"
GKAI_URL = (
    "http://deb.debian.org/debian/pool/main/f/fonts-arphic-gkai00mp/"
    f"fonts-arphic-gkai00mp_{GKAI_VERSION}.orig.tar.xz"
)
GKAI_FILE = "gkai00mp.ttf"

UKAI_VERSION = "0.2.20080216.2"
UKAI_URL = (
    "http://deb.debian.org/debian/pool/main/f/fonts-arphic-ukai/"
    f"fonts-arphic-ukai_{UKAI_VERSION}.orig.tar.bz2"
)
UKAI_FILE = "ukai.ttc"
UKAI_CN_INDEX = 0  # face order in the ttc: CN, HK, TW, TW MBE

FAMILY_EN = "Kaiyuan Kai SC"
FAMILY_ZH = "开元楷体"
PREFIX = "KaiyuanKaiSC"
WEIGHT = 400
# Single source of truth for the version: the VERSION file at repo root.
# package.json's "version" field is kept in sync with it by hand (npm has
# no mechanism to read an external file for that field) -- bump both
# together. Also bump on every rebuild during development: Word/Office key
# their font-metric cache off (name, version), so overwriting the .ttf in
# place without a new version string lets stale cached ascent/descent leak
# into the new file's rendering (this bit us once already).
FONT_VERSION = (ROOT / "VERSION").read_text().strip()

MOD_NOTICE = (
    "开元楷体 / Kaiyuan Kai SC, built by the free-fonts project (2026). Glyphs "
    "are merged from two Arphic Technology Co., Ltd. fonts under the Arphic "
    "Public License: 文鼎簡中楷 (gkai00mp.ttf 2.11) supplies every codepoint it "
    "covers; AR PL UKai's CN face (ukai.ttc 0.2.20080216.2, font index 0) "
    "supplies the remaining codepoints only. No glyph outlines were altered; "
    "only cmap/glyph-set merging, subsetting and name-table changes were "
    "made. Not affiliated with or endorsed by Arphic Technology; not named "
    "after Arphic's AR PL / 文鼎 marks. "
    "Sources: https://github.com/frankslin/free-fonts"
)

COPYRIGHT = (
    "Portions Copyright (C) 1994-1999 Arphic Technology Co., Ltd. "
    "Merged and modified for web use by the free-fonts project (2026)."
)


def download() -> None:
    SRC_DIR.mkdir(exist_ok=True)

    gkai_dest = SRC_DIR / GKAI_FILE
    if not gkai_dest.exists():
        print(f"Downloading {GKAI_URL} ...")
        with tempfile.NamedTemporaryFile(suffix=".tar.xz") as tmp:
            urllib.request.urlretrieve(GKAI_URL, tmp.name)
            with tarfile.open(tmp.name) as tar:
                for member in tar.getmembers():
                    if Path(member.name).name == GKAI_FILE:
                        gkai_dest.write_bytes(tar.extractfile(member).read())
                        print(f"  {gkai_dest.stat().st_size / 1024 / 1024:.1f} MB -> {gkai_dest}")
                        break
    else:
        print(f"{gkai_dest.name} already present, skipping download.")

    ukai_dest = SRC_DIR / UKAI_FILE
    if not ukai_dest.exists():
        print(f"Downloading {UKAI_URL} ...")
        with tempfile.NamedTemporaryFile(suffix=".tar.bz2") as tmp:
            urllib.request.urlretrieve(UKAI_URL, tmp.name)
            with tarfile.open(tmp.name) as tar:
                for member in tar.getmembers():
                    if Path(member.name).name == UKAI_FILE:
                        ukai_dest.write_bytes(tar.extractfile(member).read())
                        print(f"  {ukai_dest.stat().st_size / 1024 / 1024:.1f} MB -> {ukai_dest}")
                        break
    else:
        print(f"{ukai_dest.name} already present, skipping download.")


def _replay(pen, ops) -> None:
    for op, args in ops:
        getattr(pen, op)(*args) if args else getattr(pen, op)()


def _split_contours(ops):
    contours = []
    cur = []
    for op, args in ops:
        if op == "moveTo":
            if cur:
                contours.append(cur)
            cur = [(op, args)]
        else:
            cur.append((op, args))
    if cur:
        contours.append(cur)
    return contours


def _shift_scale(ops, dx: float = 0, sx: float = 1.0, dy: float = 0):
    out = []
    for op, args in ops:
        newargs = tuple((x * sx + dx, y + dy) for x, y in args) if args else args
        out.append((op, newargs))
    return out


def _set_glyph(glyf, hmtx, gname: str, new_glyph, advance: int | None = None) -> None:
    # fontTools draws a TrueType glyph's outline at hmtx's left side
    # bearing, not at glyf's own recalculated xMin -- moving points without
    # also updating hmtx[gname]'s LSB leaves the *stored* coordinates
    # correct but the *rendered* shape sitting at the old position (the bug
    # that motivated this helper in the first place).
    glyf[gname] = new_glyph
    new_glyph.recalcBounds(glyf)
    old_advance, _old_lsb = hmtx[gname]
    hmtx[gname] = (advance if advance is not None else old_advance, new_glyph.xMin)


def fix_repeating_punctuation(font: TTFont) -> None:
    """簡中楷's own em-dash and ellipsis glyphs sit inset from both edges of
    their 1024-unit advance box (em dash: x 73-952; ellipsis's 3 dots: x
    158-867). Chinese typesetting convention draws these two marks doubled
    (——, ……) to read as one unbroken dash / six evenly-spaced dots, but the
    inset margins show up as a visible gap at the seam between repeats. This
    is 簡中楷's own upstream design, untouched by the UKai merge -- fixed
    here by repositioning the existing outlines within their own glyph box
    (no new artwork, so no separate license to worry about).
    """
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()

    # Em dash (U+2014): a single continuous bar. Stretch it to touch both
    # edges (0..1024) so two in a row form one unbroken line.
    gname = cmap.get(0x2014)
    if gname is not None:
        pen = RecordingPen()
        gs[gname].draw(pen)
        xs = [x for op, args in pen.value for x, y in args]
        x0, x1 = min(xs), max(xs)
        scale = 1024 / (x1 - x0)
        dx = -x0 * scale
        ttpen = TTGlyphPen(gs)
        _replay(ttpen, _shift_scale(pen.value, dx=dx, sx=scale))
        _set_glyph(glyf, hmtx, gname, ttpen.glyph())

    # Horizontal ellipsis (U+2026): 3 separate dot contours. Re-center them
    # on even sixths of the box (dots at 1/6, 3/6, 5/6) *without* rescaling
    # dot size, so that when two copies sit side by side the gap between
    # dot 3 and dot 4 matches the gap between dots 1-2 and 2-3 exactly.
    gname = cmap.get(0x2026)
    if gname is not None:
        pen = RecordingPen()
        gs[gname].draw(pen)
        contours = _split_contours(pen.value)
        targets = [1024 / 6, 3 * 1024 / 6, 5 * 1024 / 6]
        ttpen = TTGlyphPen(gs)
        for contour, target in zip(contours, targets):
            xs = [x for op, args in contour for x, y in args]
            center = (min(xs) + max(xs)) / 2
            _replay(ttpen, _shift_scale(contour, dx=target - center, sx=1.0))
        _set_glyph(glyf, hmtx, gname, ttpen.glyph())


# Punctuation covered by the `halt` feature below, split the same way
# Hiragino Sans GB (a mainland-simplified system font that ships this
# feature) splits them: "opening" marks get pulled left by half their box
# in addition to losing half their width; everything else -- closing marks
# and the free-standing 、。，；：！？ -- just loses the right half.
_HALT_OPENERS = [
    "quotedblleft", "quoteleft",  # “ ‘
    "uniFF08",                    # （
    "uni300A", "uni300C", "uni300E", "uni3010", "uni3014", "uni3008",  # 《「『【〔〈
]
_HALT_OTHERS = [
    "quotedblright", "quoteright",  # ” ’
    "uniFF09",                      # ）
    "uni300B", "uni300D", "uni300F", "uni3011", "uni3015", "uni3009",  # 》」』】〕〉
    "uni3001", "uni3002", "uniFF0C", "uniFF1B", "uniFF1A", "uniFF01", "uniFF1F",  # 、。，；：！？
]


def add_halt_feature(font: TTFont) -> None:
    """簡中楷 draws every punctuation mark as a full 1024-unit-wide glyph,
    like any other ideograph -- correct as the *default*: plain Chinese
    text should stay on a uniform grid unless the layout software asks
    otherwise. Compression is something a CJK-aware layout engine opts
    into per paragraph (e.g. Word's "characterSpacingControl
    compressPunctuation", InDesign's punctuation spacing rules), and the
    standard way a font offers that is the OpenType `halt` (Alternate Half
    Widths) GPOS feature: leave the default glyph alone, and give
    open/close punctuation a *positioning* adjustment that only applies
    when `halt` is requested.

    Values aren't invented here -- they're read off /System/Library/Fonts/
    Hiragino Sans GB.ttc (Apple's system font for simplified Chinese, which
    ships exactly this feature) and rescaled from its 1000 unitsPerEm to
    ours (1024). Its `halt` table is a completely uniform rule: every
    covered glyph gets XAdvance = -unitsPerEm/2 (lose the right half of the
    box), and "opening" marks additionally get XPlacement = -unitsPerEm/2
    (shift the whole glyph left by that same half, so it now hugs the
    *following* character instead of sitting centered). See
    doc/punctuation-placement.md for the raw extracted table.
    """
    half = font["head"].unitsPerEm // 2
    fea_lines = ["languagesystem DFLT dflt;", "languagesystem hani dflt;",
                 "languagesystem latn dflt;", "", "feature halt {"]
    for gname in _HALT_OPENERS:
        fea_lines.append(f"    pos {gname} <-{half} 0 -{half} 0>;")
    for gname in _HALT_OTHERS:
        fea_lines.append(f"    pos {gname} <0 0 -{half} 0>;")
    fea_lines.append("} halt;")
    addOpenTypeFeaturesFromString(font, "\n".join(fea_lines))


# `slng` (Supported Languages) for the `meta` table below: every language
# hyperglot's "base" orthography check verifies this font's actual cmap
# covers, converted from ISO 639-3 to 639-1 where one exists (via
# pycountry), plus 'zh'/'zh-Hans' which hyperglot reports per Chinese
# topolect (cmn/yue/wuu/hak/gan/nan/cjy) rather than as a generic tag.
# Regenerate after any cmap change:
#   pip install hyperglot pycountry
#   hyperglot -y /tmp/lang-support.yaml kaiyuan-kai-sc.ttf
#   python3 -c "
#   import yaml, pycountry
#   data = yaml.unsafe_load(open('/tmp/lang-support.yaml', encoding='utf-8'))
#   out = {(pycountry.languages.get(alpha_3=c) and
#           pycountry.languages.get(alpha_3=c).alpha_2) or c for c in data}
#   out |= {'zh', 'zh-Hans'}
#   print(','.join(sorted(out)))"
_SLNG = (
    "aa,aae,aat,abe,abn,abq,ace,ach,acu,acz,aer,af,agr,aht,ale,aln,alq,als,"
    "amc,ame,ami,amr,an,anw,aoz,apn,arl,arn,asa,ast,auc,aud,ayc,ayr,ban,bbc,"
    "bem,bez,bfa,bi,bik,bin,bjn,boa,br,bs,btd,btm,bts,btx,bug,ca,cab,cak,cbi,"
    "cbk,cbr,cbs,cbt,cbu,ceb,cfm,cgg,ch,chj,chk,cim,cjk,cjy,ckb,cmn,cnh,cni,"
    "cnr,co,con,cot,cpu,crh,crs,cs,csa,csb,ctd,cy,da,dav,de,dgl,dhv,diq,dsb,"
    "dyo,ebu,efi,ekk,en,eo,es,ese,eu,fi,fia,fil,fj,fkv,fo,fr,fur,fy,ga,gag,"
    "gah,gan,gax,gaz,gcf,gd,gil,gl,gni,gqa,gsw,guc,gux,guz,gv,gwi,haa,hae,"
    "hak,hea,hil,hms,hni,hns,hop,hr,hsb,ht,hu,hus,huu,ia,id,ie,ig,igs,ilo,"
    "io,is,it,jam,jbo,jiv,jv,kaa,kam,kde,kea,kek,kg,kgp,kha,ki,kiu,kj,kl,"
    "kln,kmb,kmr,knf,koo,kqn,krl,ksb,ksh,ktu,kum,kw,kwi,lad,lag,lb,lg,lij,"
    "lkt,lld,lmo,lot,loz,lt,ltg,lua,luo,lus,lvs,mad,mam,mcd,mcf,mdf,mer,mey,"
    "mfe,mfv,mg,mgh,mi,mic,min,miq,mnk,moh,mt,mto,mus,mwf,mwl,mwp,mxv,myv,"
    "mzi,nag,nan,nap,nd,nds,ng,nhn,niu,njo,nl,no,nog,not,nov,nr,nso,ny,nyn,"
    "oc,ojb,orc,orh,ote,pam,pap,pau,pbb,pcd,pis,piu,pl,plz,pms,pon,pot,pov,"
    "ppl,prg,prq,pt,qu,quc,rar,rm,rmn,rmy,rn,ro,roo,ru,ruo,rup,ruq,rw,rwk,"
    "saq,sbp,sc,scn,sco,se,seh,sei,sey,sg,shp,sje,sju,sjw,sk,sl,sm,sma,smj,"
    "smn,sn,snk,so,srm,srn,ss,st,su,sv,swb,swc,swh,szl,tdt,tet,tiv,tk,tkl,"
    "tl,tlh,tn,to,tob,toi,tok,top,tpi,tr,ts,tsz,tum,tvl,ty,tzh,tzo,ulk,umb,"
    "umu,ura,uzn,ve,vec,vep,vmw,vo,vro,wa,wae,war,wbp,wim,win,wmw,wo,wrh,"
    "wuu,wyb,xav,xh,xnz,xog,yad,yao,yap,yij,ymk,yo,yua,yue,zdj,zh,zh-Hans,"
    "zlm,zro,zsm,zu,zun"
)


def set_meta_languages(font: TTFont) -> None:
    """Declare a `meta` table so "what language is this font for" doesn't
    fall back to guessing from the OS/2 ulUnicodeRange bits, which -- since
    UKai contributes Greek/Cyrillic/Hiragana/Katakana/Bopomofo glyphs on top
    of the Chinese ones -- produces a long, misleading "supported languages"
    list in Font Book and similar UIs. System Chinese fonts (Kaiti SC,
    Hiragino Sans GB) declare `dlng` as their real "designed for" signal;
    both use `zh-Hans`. `slng` (Supported Languages) is the same idea those
    system fonts use for their long lists, but generated from an actual
    orthography check (hyperglot) against this font's cmap rather than
    inherited/copied wholesale -- see _SLNG above for how to regenerate it.
    """
    meta = font.get("meta") or newTable("meta")
    meta.data["dlng"] = "zh-Hans"
    meta.data["slng"] = _SLNG
    font["meta"] = meta


def reposition_punctuation_y(font: TTFont) -> None:
    """簡中楷 keeps every punctuation glyph's ink entirely within the
    character cell (never crossing the baseline), matching the old Arphic
    convention of treating punctuation like any other full-height ideograph.
    Modern mainland typesetting sits 、。，；：！？ noticeably *lower*,
    letting them dip below the baseline, and sits the curly quotes “”‘’
    noticeably *higher*, near cap-height -- compare against the system
    Kaiti SC (SinoType) reference. Vertical-only translation of the
    existing outline, same approach as narrow_quotes(): no new artwork.

    dy values below are (reference glyph's vertical center) minus (our
    glyph's vertical center), lifted directly from a bounds comparison
    against Kaiti SC -- see doc/punctuation-placement.md.
    """
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()

    DY = {
        0x3001: -98,   # 、
        0x3002: -140,  # 。
        0xFF0C: -248,  # ，
        0xFF1B: +15,   # ；
        0xFF1A: +38,   # ：
        0xFF01: -48,   # ！
        0xFF1F: -82,   # ？
        0x201C: +110,  # “
        0x201D: +117,  # ”
        0x2018: +111,  # ‘
        0x2019: +108,  # ’
    }

    for cp, dy in DY.items():
        gname = cmap.get(cp)
        if gname is None:
            continue
        pen = RecordingPen()
        gs[gname].draw(pen)
        ttpen = TTGlyphPen(gs)
        _replay(ttpen, _shift_scale(pen.value, dy=dy))
        _set_glyph(glyf, hmtx, gname, ttpen.glyph())


def build_master() -> None:
    BUILD_DIR.mkdir(exist_ok=True)

    base_path = SRC_DIR / GKAI_FILE
    base = TTFont(str(base_path))
    base_cps = set(base.getBestCmap())
    base.close()

    ukai_cn_path = BUILD_DIR / "ukai-cn.ttf"
    ukai_cn = TTFont(str(SRC_DIR / UKAI_FILE), fontNumber=UKAI_CN_INDEX)
    assert ukai_cn["name"].getDebugName(1) == "AR PL UKai CN"
    ukai_cn.save(str(ukai_cn_path))
    ukai_cps = set(ukai_cn.getBestCmap())
    ukai_cn.close()

    missing = sorted(ukai_cps - base_cps)
    print(f"簡中楷: {len(base_cps):,} cps; UKai CN: {len(ukai_cps):,} cps; "
          f"filling {len(missing):,} cps from UKai CN")

    options = ft_subset.Options()
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    options.recalc_timestamp = False
    options.layout_features = []  # no GSUB/GPOS features needed; drop them below
    # fontTools.merge only partially supports merging OpenType layout tables;
    # a naively-merged GSUB/GPOS/GDEF from just the UKai side produced a
    # near-empty, invalid table that CoreText rejected outright (FreeType/
    # fontconfig tolerated it, but Font Book / Word on macOS silently refused
    # to register the font). We don't need any layout features here, so drop
    # them at the source instead of trying to merge them.
    options.drop_tables += ["GSUB", "GPOS", "GDEF", "VORG"]
    font = ft_subset.load_font(str(ukai_cn_path), options)
    subsetter = ft_subset.Subsetter(options=options)
    subsetter.populate(unicodes=missing)
    subsetter.subset(font)
    extra_path = BUILD_DIR / "ukai-cn-extra.ttf"
    ft_subset.save_font(font, str(extra_path), options)
    font.close()

    merger = Merger()
    merged = merger.merge([str(base_path), str(extra_path)])

    fix_repeating_punctuation(merged)
    reposition_punctuation_y(merged)
    add_halt_feature(merged)
    set_meta_languages(merged)

    name = merged["name"]
    name.names = []
    records = [
        (0, COPYRIGHT),
        (1, FAMILY_EN),
        (2, "Regular"),
        (3, f"{PREFIX};{FONT_VERSION};{FAMILY_EN}"),
        (4, FAMILY_EN),
        (5, f"Version {FONT_VERSION}"),
        (6, PREFIX.replace(" ", "") + "-Regular"),
        (13, MOD_NOTICE),
        (14, "https://www.gnu.org/licenses/license-list.html#ArphicPL"),
    ]
    for name_id, value in records:
        name.setName(value, name_id, 3, 1, 0x409)  # Windows, English (US)
    name.setName(FAMILY_ZH, 1, 3, 1, 0x804)  # Windows, Chinese (PRC)
    name.setName(FAMILY_ZH, 4, 3, 1, 0x804)
    name.setName(MOD_NOTICE, 13, 3, 1, 0x804)

    os2 = merged["OS/2"]
    hhea = merged["hhea"]
    os2.usWeightClass = WEIGHT

    # fontTools.merge copies whole tables from whichever input font "owns"
    # them, so we ended up with hhea taken from UKai (997/-133/6, sized for
    # UKai's own Latin/Greek accents) but OS/2 typo metrics taken from 簡中楷
    # (900/-124/80) -- two internally-consistent designs stitched into one
    # inconsistent font, which is what made line spacing misbehave in apps
    # that mix hhea and OS/2 fields. Use UKai's own self-consistent scheme
    # for the whole merged glyph set (it already accounts for the tallest/
    # deepest glyphs across both sources -- see build.py comments/README)
    # and force USE_TYPO_METRICS so typo-aware apps (Word, LibreOffice,
    # browsers) don't fall back to the looser win metrics.
    # Reference point: Apple's system "Kai" font (Shanghai Ikarus, the one
    # that renders with normal line spacing in Word) has hhea =
    # ascender 1638 / descender -410 / lineGap 0 at unitsPerEm 2048 -- i.e.
    # ascender + |descender| == unitsPerEm exactly, zero slack, and it has
    # no OS/2 table at all so line height can ONLY come from hhea. Our
    # earlier fix set OS/2 typo metrics to that same tight 1.0 ratio but
    # left hhea/win at 997/-133 (needed only for ~49 glyphs -- rare accented
    # Latin/Greek letters and a handful of obscure CJK-ext characters, see
    # the full-font scan; nothing in normal Chinese text). Word's CJK
    # document-grid line-pitch snapping (w:docGrid type="lines") apparently
    # keys off hhea/win rather than honoring USE_TYPO_METRICS, so a ~10%
    # looser hhea was enough to tip a line over the grid's per-line-pitch
    # threshold and double its height. Match Kai's tight 1.0-ratio,
    # zero-lineGap philosophy across every metric table instead, accepting
    # minor clipping on those ~49 rare glyphs.
    hhea.ascender, hhea.descender, hhea.lineGap = 900, -124, 0
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = 900, -124, 0
    os2.usWinAscent, os2.usWinDescent = 900, 124
    os2.fsSelection |= 0x80  # USE_TYPO_METRICS

    # vhea had the same cross-font mismatch (ascender from 簡中楷, descender
    # from UKai, -1024 out of a 1024 unitsPerEm font -- nonsensical). Give
    # it a plain symmetric em-box instead; vertical typesetting isn't this
    # font's use case, but it shouldn't contain self-contradictory data.
    if "vhea" in merged:
        vhea = merged["vhea"]
        vhea.ascent, vhea.descent, vhea.lineGap = 512, -512, 0

    merged.save(str(MASTER_PATH))
    merged.close()
    print(f"Master font -> {MASTER_PATH} ({MASTER_PATH.stat().st_size / 1024 / 1024:.1f} MB)")


def _build_chunk(args: tuple) -> tuple[str, int]:
    ttf_path, cps, out_path = args
    options = ft_subset.Options()
    options.flavor = "woff2"
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]

    font = ft_subset.load_font(ttf_path, options)
    subsetter = ft_subset.Subsetter(options=options)
    subsetter.populate(unicodes=sorted(cps))
    subsetter.subset(font)
    ft_subset.save_font(font, out_path, options)
    font.close()
    p = Path(out_path)
    return p.name, p.stat().st_size


def unicode_range_str(start: int) -> str:
    end = start + CHUNK_SIZE - 1
    if end <= 0xFFFF:
        return f"U+{start:04X}-{end:04X}"
    return f"U+{start:05X}-{end:05X}"


def build_webfonts(jobs: int) -> None:
    FONTS_DIR.mkdir(exist_ok=True)

    tt = TTFont(str(MASTER_PATH), lazy=True)
    cps = set(tt.getBestCmap())
    tt.close()

    chunk_map: dict[int, set[int]] = {}
    for cp in cps:
        chunk_map.setdefault((cp // CHUNK_SIZE) * CHUNK_SIZE, set()).add(cp)
    print(f"{MASTER_PATH.name}: {len(cps):,} cps, {len(chunk_map)} chunks")

    tasks = [
        (str(MASTER_PATH), chunk_cps,
         str(FONTS_DIR / f"{PREFIX}-{WEIGHT}-{start:06x}.woff2"))
        for start, chunk_cps in sorted(chunk_map.items())
    ]
    with Pool(processes=jobs) as pool:
        for i, (name, size) in enumerate(pool.imap_unordered(_build_chunk, tasks), 1):
            if i % 40 == 0 or i == len(tasks):
                print(f"  [{i}/{len(tasks)}] {name} {size // 1024} KB")

    rules = []
    for start in sorted(chunk_map):
        rule = (
            "@font-face {\n"
            f"  font-family: '{FAMILY_EN}';\n"
            "  font-style: normal;\n"
            f"  font-weight: {WEIGHT};\n"
            "  font-display: swap;\n"
            f"  src: url('fonts/{PREFIX}-{WEIGHT}-{start:06x}.woff2') format('woff2');\n"
            f"  unicode-range: {unicode_range_str(start)};\n"
            "}"
        )
        rules.append(rule)

    header = (
        f"/* {FAMILY_ZH} / {FAMILY_EN} Webfonts\n"
        " * Merged from Arphic 文鼎簡中楷 (gkai00mp.ttf, base) and AR PL UKai's\n"
        " * CN face (ukai.ttc, fills codepoints 簡中楷 lacks). Arphic Public\n"
        " * License; see ARPHICPL.TXT and README.md for the modification notice.\n"
        " * Generated CSS; do not edit manually.\n"
        " */\n\n"
    )
    CSS_PATH.write_text(header + "\n\n".join(rules) + "\n", encoding="utf-8")
    print(f"\nCSS -> {CSS_PATH} ({len(rules)} @font-face rules)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-dl", action="store_true", help="Skip download step")
    ap.add_argument("--jobs", type=int, default=cpu_count(), metavar="N")
    args = ap.parse_args()

    if not args.no_dl:
        download()

    build_master()
    build_webfonts(args.jobs)


if __name__ == "__main__":
    main()
