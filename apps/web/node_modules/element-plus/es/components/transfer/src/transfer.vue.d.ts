import { TransferDataItem, TransferDirection, TransferFormat, TransferKey, TransferProps, TransferPropsAlias } from "./transfer.js";
import { TransferPanelInstance } from "./transfer-panel.js";
import * as vue from "vue";

//#region ../../packages/components/transfer/src/transfer.vue.d.ts
declare var __VLS_12: {}, __VLS_14: {}, __VLS_65: {}, __VLS_67: {};
type __VLS_Slots = {} & {
  'left-empty'?: (props: typeof __VLS_12) => any;
} & {
  'left-footer'?: (props: typeof __VLS_14) => any;
} & {
  'right-empty'?: (props: typeof __VLS_65) => any;
} & {
  'right-footer'?: (props: typeof __VLS_67) => any;
};
declare const __VLS_base: vue.DefineComponent<TransferProps, {
  /** @description clear the filter keyword of a certain panel */clearQuery: (which: TransferDirection) => void; /** @description left panel ref */
  leftPanel: vue.Ref<TransferPanelInstance | undefined, TransferPanelInstance | undefined>; /** @description right panel ref */
  rightPanel: vue.Ref<TransferPanelInstance | undefined, TransferPanelInstance | undefined>;
}, {}, {}, {}, vue.ComponentOptionsMixin, vue.ComponentOptionsMixin, {
  "update:modelValue": (value: TransferKey[]) => void;
  change: (value: TransferKey[], direction: TransferDirection, movedKeys: TransferKey[]) => void;
  "left-check-change": (value: TransferKey[], movedKeys?: TransferKey[] | undefined) => void;
  "right-check-change": (value: TransferKey[], movedKeys?: TransferKey[] | undefined) => void;
}, string, vue.PublicProps, Readonly<TransferProps> & Readonly<{
  onChange?: ((value: TransferKey[], direction: TransferDirection, movedKeys: TransferKey[]) => any) | undefined;
  "onUpdate:modelValue"?: ((value: TransferKey[]) => any) | undefined;
  "onLeft-check-change"?: ((value: TransferKey[], movedKeys?: TransferKey[] | undefined) => any) | undefined;
  "onRight-check-change"?: ((value: TransferKey[], movedKeys?: TransferKey[] | undefined) => any) | undefined;
}>, {
  props: TransferPropsAlias;
  validateEvent: boolean;
  modelValue: TransferKey[];
  data: TransferDataItem[];
  titles: [string, string];
  format: TransferFormat;
  buttonTexts: [string, string];
  leftDefaultChecked: TransferKey[];
  rightDefaultChecked: TransferKey[];
  targetOrder: "original" | "push" | "unshift";
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