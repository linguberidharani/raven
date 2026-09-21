import { get, post } from './client';

export const listInbox = (signal) => get('/api/inbox', { signal });
export const pollInbox = () => post('/api/inbox/poll');
