import "../../../utils/index.js";
import { TransferDataItem, TransferKey, TransferProps } from "./transfer.js";
import { _default } from "./transfer-panel.vue.js";
import { ExtractPublicPropTypes, VNode } from "vue";

//#region ../../packages/components/transfer/src/transfer-panel.d.ts
interface TransferPanelState {
  checked: TransferKey[];
  allChecked: boolean;
  query: string;
  checkChangeByUser: boolean;
}
interface TransferPanelProps {
  data?: TransferProps['data'];
  optionRender?: (option: TransferDataItem) => VNode | VNode[];
  placeholder?: string;
  title?: string;
  filterable?: boolean;
  format?: TransferProps['format'];
  filterMethod?: TransferProps['filterMethod'];
  defaultChecked?: TransferProps['leftDefaultChecked'];
  props?: TransferProps['props'];
}
declare const transferPanelEmits: {
  "checked-change": (value: TransferKey[], movedKeys?: TransferKey[]) => boolean;
};
type TransferPanelEmits = typeof transferPanelEmits;
type TransferPanelInstance = InstanceType<typeof _default> & unknown;
//#endregion
export { TransferPanelEmits, TransferPanelInstance, TransferPanelProps, TransferPanelState };