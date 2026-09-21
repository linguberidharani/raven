import { useParams } from 'react-router-dom';
import { WORKFLOW } from '../utils/navigation';
import Detection from './Detection';
import Evidence from './Evidence';
import Impact from './Impact';
import NotFound from './NotFound';
import Rarf from './Rarf';
import Reconstruction from './Reconstruction';
import Report from './Report';
import Timeline from './Timeline';

// One page for each of the seven steps of an investigation.
export const STEP_PAGES = {
  evidence: Evidence,
  detection: Detection,
  reconstruction: Reconstruction,
  timeline: Timeline,
  impact: Impact,
  rarf: Rarf,
  report: Report,
};

export default function InvestigationStep() {
  const { step } = useParams();
  const Page = WORKFLOW.some((item) => item.key === step) ? STEP_PAGES[step] : undefined;
  return Page ? <Page /> : <NotFound />;
}
