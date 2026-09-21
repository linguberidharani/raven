import { useEffect } from 'react';
import { dataSource } from '../api/client';

/** Shown on every screen while demo data is on. It cannot be dismissed. */
export function DemoBanner() {
  const demo = dataSource() === 'demo';
  useEffect(() => {
    if (!demo) return undefined;
    document.body.classList.add('has-demo-banner');
    return () => document.body.classList.remove('has-demo-banner');
  }, [demo]);
  if (!demo) return null;
  return (
    <div className="demo-banner" role="status">
      Demo data, not real telemetry.
    </div>
  );
}
