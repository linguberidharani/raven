import { get } from './client';

export const getDashboard = (signal) => get('/api/dashboard', { signal });
