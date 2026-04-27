import { getRpcBaseUrl } from '@/services/rpc-client';
import {
  HealthServiceClient,
  type AirQualityAlert,
  type ListAirQualityAlertsResponse,
} from '@/generated/client/worldmonitor/health/v1/service_client';
import { timedFetch } from '@/services/timed-fetch';

export type { AirQualityAlert, ListAirQualityAlertsResponse };

const client = new HealthServiceClient(getRpcBaseUrl(), { fetch: timedFetch });
const emptyAirQualityAlerts: ListAirQualityAlertsResponse = { alerts: [], fetchedAt: 0 };

export async function fetchHealthAirQuality(): Promise<ListAirQualityAlertsResponse> {
  try {
    return await client.listAirQualityAlerts({});
  } catch {
    return emptyAirQualityAlerts;
  }
}
