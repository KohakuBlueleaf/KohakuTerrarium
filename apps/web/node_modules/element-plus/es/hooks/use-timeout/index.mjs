import { tryOnScopeDispose } from "@vueuse/core";

//#region ../../packages/hooks/use-timeout/index.ts
function useTimeout() {
	let timeoutHandle;
	const registerTimeout = (fn, delay) => {
		cancelTimeout();
		timeoutHandle = window.setTimeout(fn, delay);
	};
	const cancelTimeout = () => window.clearTimeout(timeoutHandle);
	tryOnScopeDispose(() => cancelTimeout());
	return {
		registerTimeout,
		cancelTimeout
	};
}

//#endregion
export { useTimeout };
//# sourceMappingURL=index.mjs.map