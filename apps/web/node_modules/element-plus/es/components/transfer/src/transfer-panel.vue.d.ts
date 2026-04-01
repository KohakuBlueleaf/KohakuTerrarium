import { TransferDataItem, TransferFormat, TransferKey, TransferPropsAlias } from "./transfer.js";
import { TransferPanelProps } from "./transfer-panel.js";
import "../../../index.js";
import * as vue from "vue";

//#region ../../packages/components/transfer/src/transfer-panel.vue.d.ts
declare var __VLS_31: {}, __VLS_33: {};
type __VLS_Slots = {} & {
  empty?: (props: typeof __VLS_31) => any;
} & {
  default?: (props: typeof __VLS_33) => any;
};
declare const __VLS_base: vue.DefineComponent<TransferPanelProps, {
  /** @description filter keyword */query: vue.Ref<string, string>;
}, {}, {}, {}, vue.ComponentOptionsMixin, vue.ComponentOptionsMixin, {
  "checked-change": (value: TransferKey[], movedKeys?: TransferKey[] | undefined) => void;
}, string, vue.PublicProps, Readonly<TransferPanelProps> & Readonly<{
  "onChecked-change"?: ((value: TransferKey[], movedKeys?: TransferKey[] | undefined) => any) | undefined;
}>, {
  props: TransferPropsAlias;
  data: TransferDataItem[];
  format: TransferFormat;
  defaultChecked: TransferKey[];
}, {}, {}, {}, string, vue.ComponentProvideOptions, false, {}, any>;
declare const __VLS_export: __VLS_WithSlots<typeof __VLS_base, __VLS_Slots>;
declare const _default: typeof __VLS_export;
type __VLS_WithSlots<T, S> = T & {
  new (): {
    $slots: S;
  };
};
//#endregion
export { _default };