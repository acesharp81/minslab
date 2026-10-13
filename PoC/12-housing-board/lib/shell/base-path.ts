export const BASE_PATH = '/poc/housing-board';

/** For native anchors and public assets. next/link adds basePath itself. */
export const withBasePath = (path: string) => path.startsWith('/') && !path.startsWith('//') ? BASE_PATH + path : path;
