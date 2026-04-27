import { getRpcBaseUrl } from '@/services/rpc-client';
import {
  HealthServiceClient,
  type ListDiseaseOutbreaksResponse,
  type DiseaseOutbreakItem,
} from '@/generated/client/worldmonitor/health/v1/service_client';
import { getHydratedData } from '@/services/bootstrap';
import { timedFetch } from '@/services/timed-fetch';

export type { ListDiseaseOutbreaksResponse, DiseaseOutbreakItem };

const client = new HealthServiceClient(getRpcBaseUrl(), { fetch: timedFetch });

const emptyOutbreaks: ListDiseaseOutbreaksResponse = { outbreaks: [], fetchedAt: 0 };

export async function fetchDiseaseOutbreaks(): Promise<ListDiseaseOutbreaksResponse> {
  const hydrated = getHydratedData('diseaseOutbreaks') as ListDiseaseOutbreaksResponse | undefined;
  if (hydrated?.outbreaks?.length) return hydrated;

  try {
    return await client.listDiseaseOutbreaks({});
  } catch {
    return emptyOutbreaks;
  }
}
