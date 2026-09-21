import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useReducedMotion } from '../hooks/useReducedMotion';

export const INTRO_MS = 4800;

const NODES = [
  { label: 'Telemetry', color: 'var(--observed)' },
  { label: 'Detection', color: 'var(--accent)' },
  { label: 'Reconstruction', color: 'var(--derived)' },
  { label: 'Impact', color: 'var(--sev-medium)' },
  { label: 'Report', color: 'var(--sev-info)' },
];

function seeded(seed) {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
}

const round = (value) => Math.round(value * 10) / 10;

// The same scatter every time: dots start anywhere and end on the axis (y = 200).
export const DOTS = (() => {
  const random = seeded(7);
  return Array.from({ length: 44 }, (_, index) => {
    const x = 60 + (index / 43) * 880;
    return { x: round(x), dx: round(20 + random() * 960 - x), dy: round(10 + random() * 380 - 200), delay: round(0.1 + random() * 0.5) };
  });
})();

/** Scattered event dots converge on one axis and light five stages, in about 4.8 s. Always continues to sign in. */
export default function Intro() {
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const goOn = () => navigate('/login', { replace: true });

  useEffect(() => {
    if (reduced) return undefined;
    const timer = setTimeout(() => navigate('/login', { replace: true }), INTRO_MS);
    return () => clearTimeout(timer);
  }, [reduced, navigate]);

  return (
    <main className="intro" id="main">
      <div className="intro-title">
        <h1 className="intro-name">RAVEN</h1>
        <p className="intro-full">Ransomware Attack Visualization and Event Navigator</p>
        <p className="intro-tagline">From telemetry to an evidence-backed reconstruction.</p>
      </div>
      <div className="intro-stage">
        <svg viewBox="0 0 1000 400" role="img" aria-label="Scattered events converge on one axis and light five stages: Telemetry, Detection, Reconstruction, Impact, Report.">
          <line className="intro-axis" x1="60" y1="200" x2="940" y2="200" />
          {DOTS.map((dot, index) => (
            <circle key={index} className="intro-dot" cx={dot.x} cy="200" r="2.6" style={{ '--dx': `${dot.dx}px`, '--dy': `${dot.dy}px`, animationDelay: `${dot.delay}s` }} />
          ))}
          {NODES.map((node, index) => {
            const x = 100 + index * 200;
            const delay = `${(2.4 + index * 0.5).toFixed(1)}s`;
            return (
              <g key={node.label}>
                <circle className="intro-node" cx={x} cy="200" r="10" style={{ '--node-color': node.color, animationDelay: delay }} />
                <text className="intro-node-label" x={x} y="244" style={{ animationDelay: delay }}>
                  {node.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="intro-actions">
        {reduced ? (
          <button type="button" className="btn" onClick={goOn}>
            Continue to sign in
          </button>
        ) : (
          <button type="button" className="btn btn-secondary" onClick={goOn} aria-label="Skip the introduction and go to sign in">
            Skip
          </button>
        )}
      </div>
    </main>
  );
}
