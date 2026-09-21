import { get, patch, post, upload } from './client';

const base = (id) => `/api/investigations/${id}`;

export const listInvestigations = (params, signal) => get('/api/investigations', { params, signal });
export const getInvestigation = (id, signal) => get(base(id), { signal });
export const createInvestigation = (body) => post('/api/investigations', body);
export const updateInvestigation = (id, body) => patch(base(id), body);

export const listEvidence = (id, signal) => get(`${base(id)}/evidence`, { signal });
export const uploadEvidence = (id, file, signal) => upload(`${base(id)}/evidence`, file, { signal });

export const getAnalysis = (id, signal) => get(`${base(id)}/analysis`, { signal });
export const startAnalysis = (id) => post(`${base(id)}/analysis`);

export const getCollector = (id, signal) => get(`${base(id)}/collector`, { signal });
export const linkCollectorFile = (id, sourceName) => post(`${base(id)}/collector`, { source_name: sourceName });

export const getDetections = (id, params, signal) => get(`${base(id)}/detections`, { params, signal });
export const getReconstruction = (id, signal) => get(`${base(id)}/reconstruction`, { signal });
export const getEvent = (id, ref, signal) => get(`${base(id)}/events/${ref}`, { signal });

export const getTimeline = (id, params, signal) => get(`${base(id)}/timeline`, { params, signal });
export const getImpact = (id, signal) => get(`${base(id)}/impact`, { signal });

export const getRarf = (id, params, signal) => get(`${base(id)}/rarf`, { params, signal });
export const getReport = (id, params, signal) => get(`${base(id)}/report`, { params, signal });

/** The RARF as a file download (the server sends it with a file name). */
export const rarfDownloadUrl = (id, session) => `${base(id)}/rarf?download=true${session ? `&session=${encodeURIComponent(session)}` : ''}`;
