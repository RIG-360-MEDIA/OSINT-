import { getRpcBaseUrl } from '@/services/rpc-client';
import {
  ClimateServiceClient,
  type AirQualityStation,
  type ListAirQualityDataResponse,
} from '@/generated/client/worldmonitor/climate/v1/service_client';
import { timedFetch } from '@/services/timed-fetch';

export type { AirQualityStation, ListAirQualityDataResponse };

const client = new ClimateServiceClient(getRpcBaseUrl(), { fetch: timedFetch });
const emptyClimateAirQuality: ListAirQualityDataResponse = { stations: [], fetchedAt: 0 };

export async function fetchClimateAirQuality(): Promise<ListAirQualityDataResponse> {
  try {
    return await client.listAirQualityData({});
  } catch {
    return emptyClimateAirQuality;
  }
}
