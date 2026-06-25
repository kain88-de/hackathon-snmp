export function computeOffsets<T>(
	items: readonly T[],
	getHeight: (item: T) => number,
): number[] {
	const offsets: number[] = [];
	let offset = 0;
	for (const item of items) {
		offsets.push(offset);
		offset += getHeight(item);
	}
	return offsets;
}

export function sumHeights<T>(
	items: readonly T[],
	getHeight: (item: T) => number,
): number {
	let total = 0;
	for (const item of items) {
		total += getHeight(item);
	}
	return total;
}

export function varHeightStartIdx<T>(
	items: readonly T[],
	offsets: readonly number[],
	getHeight: (item: T) => number,
	scrollY: number,
): number {
	let startIdx = 0;
	for (let i = 0; i < items.length; i += 1) {
		const item = items[i];
		if (item === undefined) {
			break;
		}
		if ((offsets[i] ?? 0) + getHeight(item) <= scrollY) {
			startIdx = i + 1;
		} else {
			break;
		}
	}
	return startIdx;
}

export function varHeightEndIdx(
	offsets: readonly number[],
	startIdx: number,
	totalCount: number,
	viewEnd: number,
): number {
	for (let i = startIdx; i < totalCount; i += 1) {
		if ((offsets[i] ?? 0) >= viewEnd) {
			return i;
		}
	}
	return totalCount;
}
