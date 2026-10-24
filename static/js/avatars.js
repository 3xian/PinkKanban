export const AVATAR_GROUPS = [
  { id: "male", name: "男生", labels: ["短发眼镜", "卷发卫衣", "棒球帽", "短发胡须", "中分眼镜", "笑脸卷发"] },
  { id: "female", name: "女生", labels: ["短发笑脸", "长发绿帽", "丸子头眼镜", "双麻花辫", "蓬松卷发", "红发夹"] },
  { id: "pet", name: "宠物", labels: ["橘猫", "金毛", "白兔", "熊猫", "仓鼠", "鹦鹉"] },
  { id: "robot", name: "机器人", labels: ["紫色天线", "薄荷叶子", "橙色方盒", "蓝色圆顶", "粉色耳机", "奶油弹簧"] },
];

export const AVATARS = AVATAR_GROUPS.flatMap((group) => group.labels.map((name, index) => ({
  id: `${group.id}-${index + 1}`, group: group.id, name,
})));

export function avatarId(person) {
  if (AVATARS.some((item) => item.id === person?.avatar_id)) return person.avatar_id;
  const id = Number(person?.id);
  const index = Number.isSafeInteger(id) && id > 0 ? (id - 1) % AVATARS.length : 0;
  return AVATARS[index].id;
}

export function avatarPath(id) {
  const safe = AVATARS.some((item) => item.id === id) ? id : AVATARS[0].id;
  return `/static/avatars/${safe}.webp?v=1`;
}
