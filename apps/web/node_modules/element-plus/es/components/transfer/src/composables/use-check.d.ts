import { CheckboxValueType } from "../../../checkbox/src/checkbox.js";
import "../../../checkbox/index.js";
import { TransferDataItem } from "../transfer.js";
import { TransferPanelEmits, TransferPanelProps, TransferPanelState } from "../transfer-panel.js";
import * as vue from "vue";
import { SetupContext } from "vue";

//#region ../../packages/components/transfer/src/composables/use-check.d.ts
declare const useCheck: (props: Required<Pick<TransferPanelProps, "data" | "format" | "defaultChecked">> & {
  filterMethod: TransferPanelProps["filterMethod"];
}, panelState: TransferPanelState, emit: SetupContext<TransferPanelEmits>["emit"]) => {
  filteredData: vue.ComputedRef<TransferDataItem[]>;
  checkableData: vue.ComputedRef<TransferDataItem[]>;
  checkedSummary: vue.ComputedRef<string>;
  isIndeterminate: vue.ComputedRef<boolean>;
  updateAllChecked: () => void;
  handleAllCheckedChange: (value: CheckboxValueType) => void;
};
//#endregion
export { useCheck };