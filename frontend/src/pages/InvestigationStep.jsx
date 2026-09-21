import { useParams } from 'react-router-dom';
import { WORKFLOW } from '../utils/navigation';
import NotFound from './NotFound';
import Planned from './Planned';

// The real page of each step is registered here as it is built.
export const STEP_PAGES = {};

const ENDPOINTS = {
  evidence: ['GET /evidence', 'POST /evidence', 'POST /analysis', 'GET /collector'],
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
  if (!info || !/^\d+$/.test(id ?? '') || Number(id) < 1) return <NotFound />;
  const Page = STEP_PAGES[step];
  if (Page) return <Page investigationId={Number(id)} />;
  return <Planned title={info.label} endpoints={ENDPOINTS[step].map((text) => text.replace(' /', ` /api/investigations/${id}/`))} />;
}
