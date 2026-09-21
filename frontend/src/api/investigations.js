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
