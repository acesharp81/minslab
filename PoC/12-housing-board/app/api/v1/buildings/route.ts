import handler from '../../../../handlers/v1/buildings.js';
import { allMethods, toRoute } from '../../../../lib/next-handler';

export const dynamic = 'force-dynamic';
export const maxDuration = 30;
export const { GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS } = allMethods(toRoute(handler));
