export function minMaxValues(arr: number[]): [number, number] {
	let max = Number.NEGATIVE_INFINITY;
	let min = Number.POSITIVE_INFINITY;
	for (const v of arr) {
		if (v < min) {
			min = v;
		}
		if (v > max) {
			max = v;
		}
	}
	return [min, max];
}
