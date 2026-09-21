import { useParams } from 'react-router-dom';
import { WORKFLOW } from '../utils/navigation';
import Evidence from './Evidence';
import NotFound from './NotFound';
import Planned from './Planned';

// The real page of each step is registered here as it is built.
export const STEP_PAGES = { evidence: Evidence };

const ENDPOINTS = {
  detection: ['GET /detections'],
  reconstruction: ['GET /reconstruction'],
  timeline: ['GET /timeline', 'GET /events/{ref}'],
  impact: ['GET /impact'],
  rarf: ['GET /rarf'],
  report: ['GET /report'],
};

export default function InvestigationStep() {
  const { id, step } = useParams();
  const info = WORKFLOW.find((item) => item.key === step);
  if (!info) return <NotFound />;
  const Page = STEP_PAGES[step];
  if (Page) return <Page />;
  return <Planned title={info.label} endpoints={ENDPOINTS[step].map((text) => text.replace(' /', ` /api/investigations/${id}/`))} />;
}
