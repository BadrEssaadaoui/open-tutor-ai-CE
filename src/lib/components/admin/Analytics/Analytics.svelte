<!--
  Real-Time Analytics Dashboard — implements upstream issue #47.

  Five tabs: Overview · Corrections · Models · Contributors · Pedagogy.
  Auto-refreshes every 30 s when the tab is visible.
-->
<script lang="ts">
	import { getContext, onDestroy, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import Sparkline from './Sparkline.svelte';
	import BarRow from './BarRow.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	import {
		getAnalyticsSummary,
		getFeedbackTimeseries,
		getCorrections,
		getModelStats,
		getContributors,
		getPedagogy,
		type AnalyticsRange,
		type AnalyticsSummary,
		type TimeseriesPoint,
		type CorrectionsResponse,
		type ModelStat,
		type ContributorStat,
		type PedagogyStat
	} from '$lib/apis/analytics';

	const i18n = getContext<Writable<i18nType>>('i18n');

	type Tab = 'overview' | 'corrections' | 'models' | 'contributors' | 'pedagogy';
	const TABS: { id: Tab; label: string }[] = [
		{ id: 'overview', label: 'Overview' },
		{ id: 'corrections', label: 'Corrections' },
		{ id: 'models', label: 'Models' },
		{ id: 'contributors', label: 'Contributors' },
		{ id: 'pedagogy', label: 'Pedagogy' }
	];
	const RANGES: AnalyticsRange[] = ['24h', '7d', '30d', '90d', 'all'];

	let selectedTab: Tab = 'overview';
	let range: AnalyticsRange = '7d';

	let loading = true;
	let lastUpdated: Date | null = null;
	let refreshTimer: ReturnType<typeof setInterval> | null = null;
	let abortController: AbortController | null = null;

	let summary: AnalyticsSummary | null = null;
	let timeseries: TimeseriesPoint[] = [];
	let corrections: CorrectionsResponse | null = null;
	let models: ModelStat[] = [];
	let contributors: ContributorStat[] = [];
	let pedagogy: PedagogyStat[] = [];

	async function refresh(showSpinner = false) {
		if (showSpinner) loading = true;
		abortController?.abort();
		abortController = new AbortController();
		const token = localStorage.token;
		try {
			const [s, ts, c, m, contrib, ped] = await Promise.all([
				getAnalyticsSummary(token, range, abortController.signal),
				getFeedbackTimeseries(token, range, 'day', abortController.signal),
				getCorrections(token, range, abortController.signal),
				getModelStats(token, range, 10, abortController.signal),
				getContributors(token, range, 10, abortController.signal),
				getPedagogy(token, range, abortController.signal)
			]);
			summary = s;
			timeseries = ts;
			corrections = c;
			models = m;
			contributors = contrib;
			pedagogy = ped;
			lastUpdated = new Date();
		} catch (err) {
			if ((err as DOMException)?.name !== 'AbortError') {
				toast.error(
					$i18n.t('Failed to load analytics: {{message}}', {
						message: (err as Error)?.message ?? 'unknown'
					})
				);
			}
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		refresh(true);
		refreshTimer = setInterval(() => {
			if (document.visibilityState === 'visible') refresh(false);
		}, 30_000);
	});

	onDestroy(() => {
		if (refreshTimer) clearInterval(refreshTimer);
		abortController?.abort();
	});

	$: if (range) {
		// re-fetch whenever the range changes (after initial mount)
		if (lastUpdated) refresh(true);
	}

	const fmtPct = (v: number) => `${(v * 100).toFixed(1)}%`;
	const fmtDelta = (v: number) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`;
	const positiveSeries = (ts: TimeseriesPoint[]) => ts.map((p) => p.positive);
	const negativeSeries = (ts: TimeseriesPoint[]) => ts.map((p) => p.negative);
	const totalSeries = (ts: TimeseriesPoint[]) => ts.map((p) => p.total);
</script>

<div class="flex flex-col gap-4 w-full pb-6">
	<!-- Header -->
	<header class="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
		<div>
			<h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">
				{$i18n.t('Analytics Dashboard')}
			</h1>
			<p class="text-sm text-gray-500 dark:text-gray-400 max-w-2xl">
				{$i18n.t(
					'Track how feedback and expert corrections shape model behavior over time. Data refreshes every 30 seconds.'
				)}
			</p>
		</div>
		<div class="flex items-center gap-2">
			<label for="analytics-range" class="text-xs text-gray-500 dark:text-gray-400">
				{$i18n.t('Range')}
			</label>
			<select
				id="analytics-range"
				bind:value={range}
				class="text-sm rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 py-1"
			>
				{#each RANGES as r}
					<option value={r}>{r}</option>
				{/each}
			</select>
			<button
				class="text-sm px-2 py-1 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800"
				on:click={() => refresh(true)}
				aria-label={$i18n.t('Refresh analytics')}
			>
				{$i18n.t('Refresh')}
			</button>
			{#if lastUpdated}
				<span class="text-xs text-gray-400">
					{$i18n.t('Updated')}
					{lastUpdated.toLocaleTimeString()}
				</span>
			{/if}
		</div>
	</header>

	<!-- Tabs -->
	<nav class="flex flex-wrap gap-1 border-b border-gray-100 dark:border-gray-800" role="tablist">
		{#each TABS as tab}
			<button
				role="tab"
				aria-selected={selectedTab === tab.id}
				on:click={() => (selectedTab = tab.id)}
				class="px-3 py-1.5 text-sm rounded-t-md transition {selectedTab === tab.id
					? 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 font-medium'
					: 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'}"
			>
				{$i18n.t(tab.label)}
			</button>
		{/each}
	</nav>

	{#if loading && !summary}
		<div class="flex justify-center py-20"><Spinner /></div>
	{:else}
		<!-- Overview -->
		{#if selectedTab === 'overview' && summary}
			<section class="grid grid-cols-2 md:grid-cols-4 gap-3">
				<article class="rounded-xl border border-gray-100 dark:border-gray-800 p-4">
					<div class="text-xs uppercase text-gray-500">{$i18n.t('Total feedback')}</div>
					<div class="text-2xl font-semibold tabular-nums">{summary.total_feedbacks}</div>
					<div class="mt-2 h-8">
						<Sparkline points={totalSeries(timeseries)} colorClass="text-blue-500" />
					</div>
				</article>
				<article class="rounded-xl border border-gray-100 dark:border-gray-800 p-4">
					<div class="text-xs uppercase text-gray-500">{$i18n.t('Positive rate')}</div>
					<div class="text-2xl font-semibold tabular-nums">{fmtPct(summary.positive_rate)}</div>
					<div
						class="text-xs {summary.delta_positive_rate >= 0 ? 'text-emerald-600' : 'text-rose-600'}"
					>
						{fmtDelta(summary.delta_positive_rate)} vs prev. window
					</div>
				</article>
				<article class="rounded-xl border border-gray-100 dark:border-gray-800 p-4">
					<div class="text-xs uppercase text-gray-500">{$i18n.t('Expert corrections')}</div>
					<div class="text-2xl font-semibold tabular-nums">{summary.corrections}</div>
					<div class="text-xs text-gray-500">
						{summary.distinct_users}
						{$i18n.t('contributors')}
					</div>
				</article>
				<article class="rounded-xl border border-gray-100 dark:border-gray-800 p-4">
					<div class="text-xs uppercase text-gray-500">{$i18n.t('Models in use')}</div>
					<div class="text-2xl font-semibold tabular-nums">{summary.distinct_models}</div>
					<div class="text-xs text-gray-500">
						{summary.positive}/{summary.negative} 👍/👎
					</div>
				</article>
			</section>

			<section class="rounded-xl border border-gray-100 dark:border-gray-800 p-4">
				<h2 class="text-sm font-medium mb-2">{$i18n.t('Feedback volume (daily)')}</h2>
				<div class="h-32">
					<Sparkline points={positiveSeries(timeseries)} colorClass="text-emerald-500" />
				</div>
				<div class="h-24 -mt-1">
					<Sparkline points={negativeSeries(timeseries)} colorClass="text-rose-500" />
				</div>
				<div class="flex gap-3 text-xs text-gray-500 mt-2">
					<span class="inline-flex items-center gap-1"
						><span class="w-2 h-2 rounded-full bg-emerald-500"></span>
						{$i18n.t('Positive')}</span
					>
					<span class="inline-flex items-center gap-1"
						><span class="w-2 h-2 rounded-full bg-rose-500"></span>
						{$i18n.t('Negative')}</span
					>
				</div>
			</section>
		{/if}

		<!-- Corrections -->
		{#if selectedTab === 'corrections' && corrections}
			<section class="grid grid-cols-1 md:grid-cols-3 gap-3">
				<article class="rounded-xl border border-gray-100 dark:border-gray-800 p-4">
					<div class="text-xs uppercase text-gray-500">{$i18n.t('Resolution rate')}</div>
					<div class="text-2xl font-semibold tabular-nums">
						{fmtPct(corrections.resolution_rate)}
					</div>
					<div class="text-xs text-gray-500">
						{$i18n.t('Share of corrections with a stated reason')}
					</div>
				</article>
				<article class="md:col-span-2 rounded-xl border border-gray-100 dark:border-gray-800 p-4">
					<h2 class="text-sm font-medium mb-2">{$i18n.t('Corrections per day')}</h2>
					<div class="h-32">
						<Sparkline points={totalSeries(corrections.daily)} colorClass="text-violet-500" />
					</div>
				</article>
			</section>
			<section class="rounded-xl border border-gray-100 dark:border-gray-800 p-4">
				<h2 class="text-sm font-medium mb-3">{$i18n.t('Top error categories')}</h2>
				{#if corrections.top_categories.length === 0}
					<p class="text-sm text-gray-500">
						{$i18n.t('No categorised corrections yet in this range.')}
					</p>
				{:else}
					{@const max = Math.max(...corrections.top_categories.map((c) => c.count), 1)}
					{#each corrections.top_categories as c}
						<BarRow label={c.category} value={c.count} {max} colorClass="bg-violet-500" />
					{/each}
				{/if}
			</section>
		{/if}

		<!-- Models -->
		{#if selectedTab === 'models'}
			<section class="rounded-xl border border-gray-100 dark:border-gray-800 p-4">
				<h2 class="text-sm font-medium mb-3">{$i18n.t('Model performance leaderboard')}</h2>
				{#if models.length === 0}
					<p class="text-sm text-gray-500">{$i18n.t('No feedback events recorded in this range.')}</p>
				{:else}
					<div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
						{#each models as m}
							<article class="rounded-lg border border-gray-100 dark:border-gray-800 p-3">
								<div class="flex items-center justify-between gap-2">
									<div class="truncate">
										<div class="font-medium text-sm truncate" title={m.model_id}>{m.model_id}</div>
										<div class="text-xs text-gray-500">
											{m.total}
											{$i18n.t('events')} · 👍 {m.positive} · 👎 {m.negative}
										</div>
									</div>
									<div
										class="text-sm font-semibold {m.score >= 0.7
											? 'text-emerald-600'
											: m.score >= 0.4
												? 'text-amber-600'
												: 'text-rose-600'}"
									>
										{fmtPct(m.score)}
									</div>
								</div>
								<div class="h-10 mt-2">
									<Sparkline points={positiveSeries(m.trajectory)} colorClass="text-emerald-500" />
								</div>
							</article>
						{/each}
					</div>
				{/if}
			</section>
		{/if}

		<!-- Contributors -->
		{#if selectedTab === 'contributors'}
			<section class="rounded-xl border border-gray-100 dark:border-gray-800 p-4">
				<h2 class="text-sm font-medium mb-3">{$i18n.t('Top contributors')}</h2>
				{#if contributors.length === 0}
					<p class="text-sm text-gray-500">{$i18n.t('No contributors in this range.')}</p>
				{:else}
					{@const max = Math.max(...contributors.map((c) => c.count), 1)}
					{#each contributors as c}
						<BarRow
							label={`${c.name ?? c.user_id}${c.role ? ' · ' + c.role : ''}`}
							value={c.count}
							{max}
							colorClass="bg-blue-500"
						/>
					{/each}
				{/if}
			</section>
		{/if}

		<!-- Pedagogy -->
		{#if selectedTab === 'pedagogy'}
			<section class="rounded-xl border border-gray-100 dark:border-gray-800 p-4">
				<h2 class="text-sm font-medium mb-3">{$i18n.t('Subject coverage')}</h2>
				{#if pedagogy.length === 0}
					<p class="text-sm text-gray-500">
						{$i18n.t('No support sessions with feedback in this range yet.')}
					</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead class="text-xs uppercase text-gray-500">
								<tr>
									<th class="text-left py-2">{$i18n.t('Subject')}</th>
									<th class="text-left">{$i18n.t('Level')}</th>
									<th class="text-right">{$i18n.t('Feedback events')}</th>
									<th class="text-right">{$i18n.t('Positive rate')}</th>
								</tr>
							</thead>
							<tbody>
								{#each pedagogy as p}
									<tr class="border-t border-gray-100 dark:border-gray-800">
										<td class="py-2">{p.subject}</td>
										<td class="text-gray-500">{p.level ?? '—'}</td>
										<td class="text-right tabular-nums">{p.count}</td>
										<td
											class="text-right tabular-nums {p.positive_rate >= 0.7
												? 'text-emerald-600'
												: p.positive_rate >= 0.4
													? 'text-amber-600'
													: 'text-rose-600'}"
										>
											{p.count ? fmtPct(p.positive_rate) : '—'}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</section>
		{/if}
	{/if}
</div>
