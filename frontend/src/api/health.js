import { get } from './client';

export const getHealth = (signal) => get('/api/health', { signal });
