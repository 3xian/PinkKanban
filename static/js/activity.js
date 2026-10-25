// Input is newest-first. Comments and unknown actors always form their own group.
export function groupActivity(items) {
  const groups = [];
  for (const item of items || []) {
    const previous = groups.at(-1);
    const comment = item.action.startsWith("comment.");
    if (!comment && item.user?.id != null && previous &&
        !previous[0].action.startsWith("comment.") && previous[0].user?.id === item.user.id) {
      previous.push(item);
    } else {
      groups.push([item]);
    }
  }
  return groups;
}
