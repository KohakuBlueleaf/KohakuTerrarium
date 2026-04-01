import { TransferDataItem, TransferProps } from "../transfer.js";
import * as vue from "vue";

//#region ../../packages/components/transfer/src/composables/use-computed-data.d.ts
declare const useComputedData: (props: Required<Omit<TransferProps, "filterPlaceholder" | "filterMethod" | "renderContent">>) => {
  sourceData: vue.ComputedRef<TransferDataItem[]>;
  targetData: vue.ComputedRef<TransferDataItem[]>;
};
//#endregion
export { useComputedData };