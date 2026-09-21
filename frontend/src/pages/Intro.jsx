import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { BrandMark } from '../components/Brand';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
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

// The same scatter every time: dots start anywhere and end on the axis (y = 150).
export const DOTS = (() => {
  const random = seeded(7);
  return Array.from({ length: 44 }, (_, index) => {
    const x = 60 + (index / 43) * 880;
    return { x: round(x), dx: round(20 + random() * 960 - x), dy: round(10 + random() * 280 - 150), delay: round(0.5 + random() * 0.6), hot: index % 11 === 4 };
  });
})();

const nodeDelay = (index) => `${(2.6 + index * 0.42).toFixed(2)}s`;

/** Scattered event dots converge on one axis and light five stages, in about 4.8 s. Always continues to sign in. */
export default function Intro() {
  useDocumentTitle('');
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const goOn = () => navigate('/login', { replace: true });

  useEffect(() => {
    if (reduced) return undefined;
    const timer = setTimeout(() => navigate('/login', { replace: true }), INTRO_MS);
    return () => clearTimeout(timer);
  }, [reduced, navigate]);

  return (
    <main className={`intro${reduced ? ' still' : ''}`} id="main">
      <div className="intro-bg" aria-hidden="true" />
      <div className="intro-content">
        <div className="intro-logo">
          <BrandMark size={64} />
        </div>
        <h1 className="intro-name" aria-label="RAVEN">
          {'RAVEN'.split('').map((letter, index) => (
            <span key={index} aria-hidden="true" style={{ animationDelay: `${(0.25 + index * 0.09).toFixed(2)}s` }}>
              {letter}
            </span>
          ))}
        </h1>
        <p className="intro-full">Ransomware Attack Visualization and Event Navigator</p>

        <div className="intro-stage">
          <svg viewBox="0 0 1000 300" role="img" aria-label="Scattered events converge on one axis and light five stages: Telemetry, Detection, Reconstruction, Impact, Report.">
            <line className="intro-axis" x1="60" y1="150" x2="940" y2="150" />
            {DOTS.map((dot, index) => (
              <circle key={index} className={`intro-dot${dot.hot ? ' hot' : ''}`} cx={dot.x} cy="150" r={dot.hot ? 3.4 : 2.6} style={{ '--dx': `${dot.dx}px`, '--dy': `${dot.dy}px`, animationDelay: `${dot.delay}s` }} />
            ))}
            {NODES.map((node, index) => (
              <g key={node.label} className="intro-node-group" style={{ '--node-color': node.color, animationDelay: nodeDelay(index) }}>
                <circle className="intro-halo" cx={100 + index * 200} cy="150" r="18" style={{ animationDelay: nodeDelay(index) }} />
                <circle className="intro-node" cx={100 + index * 200} cy="150" r="10" style={{ animationDelay: nodeDelay(index) }} />
              </g>
            ))}
          </svg>
          <ul className="intro-chips">
            {NODES.map((node, index) => (
              <li key={node.label} className="intro-chip" style={{ '--node-color': node.color, animationDelay: nodeDelay(index) }}>
                {node.label}
              </li>
            ))}
          </ul>
        </div>

        <p className="intro-tagline">
          <span>Trace the Attack.</span>
          <span>Measure the Impact.</span>
        </p>
      </div>

      <div className="intro-footer">
        <div className="intro-progress" aria-hidden="true">
          <span />
        </div>
        {reduced ? (
          <button type="button" className="btn" onClick={goOn}>
            Continue to sign in
          </button>
        ) : (
          <button type="button" className="intro-skip" onClick={goOn} aria-label="Skip the introduction and go to sign in">
            Skip intro
          </button>
        )}
      </div>
    </main>
  );
}
