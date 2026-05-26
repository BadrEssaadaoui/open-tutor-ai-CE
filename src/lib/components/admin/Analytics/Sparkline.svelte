<!--
  Tiny SVG sparkline. No external deps.

  Props:
    - points: number[]   values to plot
    - width / height     pixel size (responsive via parent)
    - colorClass         Tailwind text-* class applied to the stroke
-->
<script lang="ts">
	export let points: number[] = [];
	export let width: number = 160;
	export let height: number = 40;
	export let colorClass: string = 'text-blue-500';
	export let area: boolean = true;
	export let strokeWidth: number = 1.5;

	$: max = Math.max(1, ...points);
	$: min = Math.min(0, ...points);
	$: range = Math.max(1, max - min);
	$: step = points.length > 1 ? width / (points.length - 1) : width;
	$: pathD = points
		.map((v, i) => {
			const x = i * step;
			const y = height - ((v - min) / range) * height;
			return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
		})
		.join(' ');
	$: areaD = points.length ? `${pathD} L ${(points.length - 1) * step} ${height} L 0 ${height} Z` : '';
</script>

<svg
	viewBox="0 0 {width} {height}"
	preserveAspectRatio="none"
	class="block w-full h-full {colorClass}"
	role="img"
	aria-label="sparkline"
>
	{#if area && points.length}
		<path d={areaD} fill="currentColor" fill-opacity="0.10" />
	{/if}
	{#if points.length}
		<path d={pathD} fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linejoin="round" />
	{/if}
</svg>
