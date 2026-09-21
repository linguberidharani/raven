import { useEffect } from 'react';

/** Puts the page name in the browser tab: "Dashboard | RAVEN". */
export function useDocumentTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} | RAVEN` : 'RAVEN';
  }, [title]);
}
