// Lucide SVGs (ISC/MIT) and Radix Colors (MIT); licenses in static/icons/covers/.
// Keep persisted color keys compatible with existing cards and API validation.
export const COVER_THEMES = [
  {
    "value": "#C47B2B",
    "name": "需求",
    "icon": "lightbulb",
    "background": "#fff7c2",
    "selected": "#fbe577",
    "border": "#e9c162",
    "accent": "#ffc53d",
    "ink": "#ab6400",
    "text": "#4f3422"
  },
  {
    "value": "#3D6B8A",
    "name": "开发",
    "icon": "code-xml",
    "background": "#e6f4fe",
    "selected": "#c2e5ff",
    "border": "#8ec8f6",
    "accent": "#0090ff",
    "ink": "#0d74ce",
    "text": "#113264"
  },
  {
    "value": "#7A5EA8",
    "name": "界面",
    "icon": "panels-top-left",
    "background": "#f0f1fe",
    "selected": "#dadcff",
    "border": "#b8baf8",
    "accent": "#5b5bd6",
    "ink": "#5753c6",
    "text": "#272962"
  },
  {
    "value": "#2F6F6A",
    "name": "数据",
    "icon": "database",
    "background": "#e0f8f3",
    "selected": "#b8eae0",
    "border": "#83cdc1",
    "accent": "#12a594",
    "ink": "#008573",
    "text": "#0d3d38"
  },
  {
    "value": "#5C6B52",
    "name": "测试",
    "icon": "flask-conical",
    "background": "#e6f6eb",
    "selected": "#c4e8d1",
    "border": "#8eceaa",
    "accent": "#30a46c",
    "ink": "#218358",
    "text": "#193b2d"
  },
  {
    "value": "#C46B4A",
    "name": "修复",
    "icon": "bug",
    "background": "#ffefd6",
    "selected": "#ffd19a",
    "border": "#f5ae73",
    "accent": "#f76b15",
    "ink": "#cc4e00",
    "text": "#582d1d"
  },
  {
    "value": "#D63A56",
    "name": "部署",
    "icon": "rocket",
    "background": "#ffe9f0",
    "selected": "#facedd",
    "border": "#eaacc3",
    "accent": "#e93d82",
    "ink": "#cb1d63",
    "text": "#621639"
  },
  {
    "value": "#8A4B5A",
    "name": "安全",
    "icon": "shield-check",
    "background": "#fbebfb",
    "selected": "#f2d1f3",
    "border": "#deade3",
    "accent": "#ab4aba",
    "ink": "#953ea3",
    "text": "#53195d"
  }
];

export function coverTheme(value) {
  return COVER_THEMES.find((theme) => theme.value.toLowerCase() === value?.toLowerCase());
}
