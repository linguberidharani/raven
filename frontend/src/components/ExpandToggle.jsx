import { Icon } from './Icons';

/** The one "View more / View less" (or "Show details / Hide details") button used everywhere a block of
 * content is collapsed by default, so the interaction is the same on every page. The arrow rotates the same
 * way as the JSON tree's toggle. */
export function ExpandToggle({ open, onClick, moreLabel = 'View more', lessLabel = 'View less', hiddenCount, controls, className = '' }) {
  const label = open ? lessLabel : hiddenCount != null ? `${moreLabel} (${hiddenCount})` : moreLabel;
  return (
    <button type="button" className={`expand-toggle ${className}`.trim()} onClick={onClick} aria-expanded={open} aria-controls={controls}>
      <Icon name="arrow" size={14} />
      {label}
    </button>
  );
}
