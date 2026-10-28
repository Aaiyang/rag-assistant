# 问溪 · 小溪

- 项目展示名：**问溪（Wenxi）**。
- 标语：**循知而行，问有所归。**
- Agent 展示名：**小溪（Xiao Xi）**。
- 开场：**我是小溪，陪你从一个问题，找到清晰的答案。**

## 视觉

Logo 以展开的书页和蜿蜒溪流为意象，使用墨青、薄荷青与暖米白；小尺寸保留清晰轮廓。
吉祥物“小溪”是抱书的溪水精灵，以青玉般的身体、温润面孔和流动尾巴表达陪伴与探索。
图形不内嵌文字，名称与标语由 HTML 渲染，便于保持清晰、可访问和响应式排版。

界面以暖白纸色 `#fffdf7`、青绿 `#2f7057` 和墨绿 `#0c1714` 为基础，砂金仅用于次级强调。
主色、次色及 RGB 透明叠色由全局语义 token 管理，组件共用相同 token；错误、警告与成功仍有独立语义色。
欢迎标题使用本地宋体衬线字体回退，减少背景光晕和持续动画，卡片说明可展示两行。
新浏览器默认浅色主题，已有深浅色偏好继续生效。

| 资源 | 用途 |
| --- | --- |
| [wenxi-mark.png](../../frontend/src/assets/images/wenxi-mark.png) | 256 × 256 透明 PNG，侧栏、登录、恢复登录和 favicon |
| [xiaoxi-mascot.webp](../../frontend/src/assets/images/xiaoxi-mascot.webp) | 640 × 640 透明 WebP，欢迎页、Agent 头像及历史/知识库/证据空状态 |

素材使用内置 image_gen 生成，在项目中保留透明通道并导出缩小版本；没有新增应用依赖。
原有认证 Cookie、缓存 key、容器/卷、包分发名及持久图身份继续使用其既有机器标识，避免品牌展示变更影响现有数据与恢复协议。
原始仓库链接与历史架构文件保留真实来源路径。

## 生成提示词

下面记录最终使用的英文提示词；实际名称、标语和开场由应用组件及 Agent 基础提示词提供。

### 小溪吉祥物

```text
Use case: stylized-concept. Asset type: production website mascot illustration, transparent PNG cutout for a Chinese knowledge assistant named 小溪 (Xiao Xi), product 问溪 (Wenxi), poetic stream-of-knowledge concept. Create ONE memorable original creek spirit mascot: a rounded water-droplet creature with a pale celadon jade translucent body, creamy ivory face area, small deep ink-teal expressive eyes, tiny warm smile, rounded little arms and feet, a flowing tail shaped like a gentle winding stream. Friendly and quietly intelligent, slightly tilted head, holding one small open ivory book close to its chest. Refined soft 3D clay and frosted-jade illustration with subtle depth, clean silhouette, premium editorial product quality rather than a toy advertisement. Mint jade, pale warm ivory, a tiny muted lilac accent. Full body, three-quarter view facing slightly right but eyes toward viewer, centered, fills 85% of square image with equal padding, no clipping. Light comes softly from upper left; edges readable on both dark navy and light ivory UI. Real transparent background, no checkerboard drawn, no white rectangle, no room, no ground plane, no large cast shadow. No text, no letters, no logo, no watermark, no cat, no robot, no extra characters. This mascot will appear at 128 to 200 pixels tall so prioritize an immediately readable face and simple shapes. Return exactly one standalone mascot asset.
```

### 问溪 Logo

```text
Use case: logo-brand. Asset type: final production app icon / favicon / sidebar mark for Chinese knowledge assistant brand 问溪 (Wenxi), tagline about following knowledge like a stream. Generate ONE standalone logo symbol, no text. A bold elegant flowing creek drawn in negative space through two gently folded open-book pages; together the book and winding creek subtly suggest a question mark, but not a literal punctuation glyph. Compact balanced upright mark within a soft rounded-square creamy ivory tile. Restrained modern Chinese poetic sensibility; calm, timeless, confident, clean geometrical curves. Deep ink-teal foreground #184b48, jade-mint accent #8bcfbc, ivory tile #f4f0e4, one very subtle pale lilac accent only if needed. Mostly flat polished graphic with extremely subtle paper depth, sharp clean edges, high contrast, scalable and readable at 24x24 pixels. The logo occupies 88% of a square canvas, generous even padding, perfectly centered. The rounded-square tile is opaque ivory but outside the tile is truly transparent alpha. No surrounding canvas color, no checkerboard drawn, no watermark, no letters, no Chinese writing, no words, no mockup, no mascot, no character face, no shadows outside the tile, no multiple variations. Exactly one final usable square icon.
```
