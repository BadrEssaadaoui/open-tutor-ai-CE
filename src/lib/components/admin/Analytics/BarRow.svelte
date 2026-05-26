<!--
  A horizontal bar row used for "top categories", "model leaderboard", etc.
  Renders semantic <progress> for accessibility and a visual fill on top.
-->
<script lang="ts">
	export let label: string;
	export let value: number;
	export let max: number = 1;
	export let suffix: string = '';
	export let colorClass: string = 'bg-blue-500';
	$: pct = Math.max(0, Math.min(100, max ? (value / max) * 100 : 0));
</script>

<div class="flex items-center gap-3 py-1.5">
	<div class="w-40 shrink-0 truncate text-sm text-gray-700 dark:text-gray-200" title={label}>
		{label}
	</div>
	<div class="relative flex-1 h-2 bg-gray-100 dark:bg-gray-800 rounded">
		<div class="absolute inset-y-0 left-0 rounded {colorClass}" style="width: {pct}%"></div>
	</div>
	<div class="w-16 shrink-0 text-right text-sm tabular-nums text-gray-600 dark:text-gray-300">
		{value}{suffix}
	</div>
</div>
