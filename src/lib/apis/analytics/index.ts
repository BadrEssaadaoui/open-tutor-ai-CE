import { TUTOR_API_BASE_URL } from '$lib/constants';

export type AnalyticsRange = '24h' | '7d' | '30d' | '90d' | 'all';
export type AnalyticsBucket = 'hour' | 'day' | 'week';

export interface AnalyticsSummary {
	range: AnalyticsRange;
	total_feedbacks: number;
	positive: number;
	negative: number;
	neutral: number;
	corrections: number;
	distinct_users: number;
	distinct_models: number;
	positive_rate: number;
	delta_positive_rate: number;
}

export interface TimeseriesPoint {
	bucket: number; // epoch seconds at bucket start
	total: number;
	positive: number;
	negative: number;
}

export interface CorrectionsResponse {
	range: AnalyticsRange;
	daily: TimeseriesPoint[];
	top_categories: { category: string; count: number }[];
	resolution_rate: number;
}

export interface ModelStat {
	model_id: string;
	positive: number;
	negative: number;
	total: number;
	score: number;
	trajectory: TimeseriesPoint[];
}

export interface ContributorStat {
	user_id: string;
	name: string | null;
	role: string | null;
	count: number;
}

export interface PedagogyStat {
	subject: string;
	level: string | null;
	count: number;
	positive_rate: number;
}

/**
 * Shared fetch helper — centralises auth header, error parsing, and JSON
 * decoding so we don't repeat the 12-line then/catch boilerplate found in
 * other API clients.
 */
async function apiGet<T>(path: string, token: string, signal?: AbortSignal): Promise<T> {
	const res = await fetch(`${TUTOR_API_BASE_URL}/analytics${path}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		signal
	});
	if (!res.ok) {
		let detail: unknown;
		try {
			detail = (await res.json())?.detail;
		} catch {
			detail = res.statusText;
		}
		throw new Error(typeof detail === 'string' ? detail : 'Analytics request failed');
	}
	return (await res.json()) as T;
}

export const getAnalyticsSummary = (token: string, range: AnalyticsRange = '7d', signal?: AbortSignal) =>
	apiGet<AnalyticsSummary>(`/summary?range=${range}`, token, signal);

export const getFeedbackTimeseries = (
	token: string,
	range: AnalyticsRange = '30d',
	bucket: AnalyticsBucket = 'day',
	signal?: AbortSignal
) => apiGet<TimeseriesPoint[]>(`/feedback-timeseries?range=${range}&bucket=${bucket}`, token, signal);

export const getCorrections = (token: string, range: AnalyticsRange = '30d', signal?: AbortSignal) =>
	apiGet<CorrectionsResponse>(`/corrections?range=${range}`, token, signal);

export const getModelStats = (
	token: string,
	range: AnalyticsRange = '30d',
	limit = 10,
	signal?: AbortSignal
) => apiGet<ModelStat[]>(`/models?range=${range}&limit=${limit}`, token, signal);

export const getContributors = (
	token: string,
	range: AnalyticsRange = '30d',
	limit = 10,
	signal?: AbortSignal
) => apiGet<ContributorStat[]>(`/contributors?range=${range}&limit=${limit}`, token, signal);

export const getPedagogy = (token: string, range: AnalyticsRange = '30d', signal?: AbortSignal) =>
	apiGet<PedagogyStat[]>(`/pedagogy?range=${range}`, token, signal);
