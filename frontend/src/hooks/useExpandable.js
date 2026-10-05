import { useState } from 'react';

/** Shows only the first `initialCount` items until "View more" is used; "View less" collapses back. The same
 * rule everywhere a list can get long: Dashboard alerts and activity, Report findings. */
export function useExpandable(items, initialCount = 3) {
  const [open, setOpen] = useState(false);
  const shown = open ? items : items.slice(0, initialCount);
  const hidden = Math.max(items.length - initialCount, 0);
  return { shown, open, hidden, toggle: () => setOpen((value) => !value) };
}
