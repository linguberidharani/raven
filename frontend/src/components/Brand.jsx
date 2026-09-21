export function BrandMark({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="7" fill="#121925" stroke="#263349" />
      <path d="M5 16h22" stroke="#5a9df5" strokeWidth="2" strokeLinecap="round" />
      <circle cx="9" cy="16" r="3" fill="#3db7aa" />
      <circle cx="16" cy="16" r="3" fill="#5a9df5" />
      <circle cx="23" cy="16" r="3" fill="#a78ff3" />
    </svg>
  );
}

export function Brand({ size = 30 }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10, fontWeight: 600, letterSpacing: '0.2em' }}>
      <BrandMark size={size} />
      <span>RAVEN</span>
    </span>
  );
}
