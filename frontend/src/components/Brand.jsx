export function BrandMark({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <path d="M16 2.5l11.5 6.6v13.8L16 29.5 4.5 22.9V9.1z" fill="#0f1725" stroke="#5a9df5" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M8.5 16.5h4l2-5 3.5 9 2-4h3.5" fill="none" stroke="#e8edf6" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="24" cy="12" r="1.6" fill="#3db7aa" />
    </svg>
  );
}

export function Brand({ size = 30 }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10, fontWeight: 600, letterSpacing: '0.22em' }}>
      <BrandMark size={size} />
      <span>RAVEN</span>
    </span>
  );
}
