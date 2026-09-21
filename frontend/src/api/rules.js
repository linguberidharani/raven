import { get } from './client';

export const getRules = (signal) => get('/api/rules', { signal });
