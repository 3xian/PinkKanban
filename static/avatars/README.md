# 预设头像

24 个原创手绘涂鸦头像，使用内置 imagegen 生成。运行时文件为 192×192 的 WebP，使用 Lanczos 缩小并以质量 80 编码，适配最大 56px 的头像及三倍像素密度屏幕；全部素材合计 181,644 字节，较原先 3,036,268 字节减少 94%。压缩直接使用 PNG 原稿，避免多次有损编码。PNG 原稿保存在生成工具的本地输出目录，不作为运行依赖。

应用生成的头像 URL 带有 `?v=1`，成功响应与条件请求的 304 响应允许浏览器缓存一年（`public, max-age=31536000, immutable`）；未版本化的请求仍须验证缓存。以后更换头像文件时，必须同步增加 `static/js/avatars.js` 的 URL 版本号，让浏览器获取新素材。选择器只加载当前分类的 6 个头像。单文件预算为 16 KiB，整套预算为 256 KiB，由前端测试检查。

## 画风与提示词

参考用户选定的 C 组：粗黑手绘线条、平涂、轻微纸张纹理、活泼表情。先生成 male-1，再以它作为其余 23 个头像的画风参考。

male-1 的提示词：

> Create ONE square avatar asset, NOT a comparison board. Use ONLY the C panel (middle left) of the reference as art direction: playful hand-drawn cartoon, rough lively thick black ink lines, simple flat colors, light paper texture, cheerful human expression. No 3D, no anime rendering. Single young adult man with tousled short black hair, round glasses, mustard yellow shirt, warm smile. Head and shoulders centered and big. Pale lavender solid background fills entire square, NO circle mask, NO border, NO text, NO letters. Clean silhouette, recognizable at 32px. Original character. Keep entire hair and face within safe center 80 percent so app can circle-crop. Final standalone project avatar.

其余头像的完整提示词由以下模板与各自的 subject 组成：

> Create ONE standalone square cartoon profile avatar image. Use the attached image as the strict reference for art style, composition scale, line weight and paper texture, but create the following DIFFERENT character: {subject}. Playful hand drawn doodle illustration, loose bold uneven black ink outlines, simple flat pastel color fills with subtle paper texture. Original character. Head and upper shoulders centered large, face recognizable at 32px. Keep all essential features including ears, hair, hats, antennas inside the safe central 80 percent for circular cropping by the app. Background must fill the full square with the specified pale color. NO circle frame, NO border, NO text, NO letters, NO multiple portraits, NO comparison board, NO photorealism, NO 3D. Match the charming rough doodle reference faithfully.

| 文件 ID | subject |
| --- | --- |
| male-2 | Young adult man, short chestnut curly hair, no glasses, green hoodie, toothy cheerful grin, pale peach background |
| male-3 | Young adult man, dark blue baseball cap over short black hair, coral sweatshirt, playful wink, pale mint background |
| male-4 | Adult man, close cropped dark hair, short neat beard and mustache, blue denim collar, gentle confident smile, pale butter yellow background |
| male-5 | Young adult man, straight medium length dark hair parted in middle, rectangular black glasses, lavender sweater, gentle closed mouth smile, pale sky blue background |
| male-6 | Young adult man with warm brown skin, short tight curly black hair, orange hoodie, laughing with eyes closed, pale pink background |
| female-1 | Young adult woman, short wavy black bob with bangs, lavender hoodie, broad joyful smile with eyes closed and rosy cheeks, pale peach background |
| female-2 | Young adult woman, long dark wavy hair, forest green baseball cap, small gold hoop earrings, black shirt, friendly smile, pale lavender background |
| female-3 | Young adult woman, dark brown high messy bun, round black glasses, sage green sweater, warm small smile, pale butter yellow background |
| female-4 | Young adult woman, auburn twin braids, blue striped shirt, freckles, playful wink, pale mint background |
| female-5 | Young adult woman with warm brown skin, voluminous short tight curly dark hair, mustard yellow shirt, joyful toothy smile, pale sky blue background |
| female-6 | Young adult woman, straight dark shoulder-length hair, small red hair clip, coral hoodie, sweet relaxed smile, pale pink background |
| pet-1 | Single cute orange tabby cat head and upper chest, triangular ears, dark forehead stripes, white muzzle, green neckerchief, mischievous smile, pale lavender background. Animal anatomy, no human hair. |
| pet-2 | Single cute golden retriever dog head and upper chest, big floppy ears, warm golden fur, red bandana, happy tongue out, pale mint background. Animal anatomy. |
| pet-3 | Single cute white rabbit head and upper chest, two tall upright ears fully within frame, pink inner ears, peach cheeks, tiny blue bowtie, gentle smile, pale peach background. Animal anatomy. |
| pet-4 | Single cute black and white panda head and upper chest, round black ears, distinct eye patches, mustard yellow scarf, joyful eyes closed, pale sky blue background. Animal anatomy. |
| pet-5 | Single cute round golden hamster head and upper chest, tiny round ears, very puffy cheeks, tiny paws near face, pink nose, eager bright eyes, pale pink background. Animal anatomy. |
| pet-6 | Single cute small green parrot head and upper chest, coral curved beak, pale yellow cheek patches, little tuft of feathers, friendly tilted head, pale butter yellow background. Bird anatomy. |
| robot-1 | Single cute lilac robot head and upper shoulders, rounded square head, single ball antenna, dark screen face with two expressive crescent eyes, hand-drawn cheerful mouth, little round ear pieces, pale peach background. Strictly flat hand drawn doodle, no glossy surfaces. |
| robot-2 | Single cute mint robot head and upper shoulders, round head, two tiny leaf-shaped antennas, dark screen face with dot eyes and warm smile, small collar, pale lavender background. Strictly flat hand drawn doodle, no 3D. |
| robot-3 | Single cute orange robot head and upper shoulders, boxy rectangular head with two small bolts on sides, mismatched friendly oval eyes and grin, simple chest panel, pale sky blue background. Strictly flat hand drawn doodle, no 3D. |
| robot-4 | Single cute sky blue robot head and upper shoulders, dome shaped head with two short antenna sticks, one eye a circle one eye playful wink, small bowtie, pale butter yellow background. Strictly flat hand drawn doodle, no 3D. |
| robot-5 | Single cute pink robot head and upper shoulders, round capsule head with chunky headphones, black screen face with big sparkly dot eyes and smile, pale mint background. Strictly flat hand drawn doodle, no 3D. |
| robot-6 | Single cute cream colored retro robot head and upper shoulders, broad rounded trapezoid head, spring coil antenna, asymmetrical round ear discs, black screen eyes laughing shut, coral neck scarf, pale pink background. Strictly flat hand drawn doodle, no 3D. |

