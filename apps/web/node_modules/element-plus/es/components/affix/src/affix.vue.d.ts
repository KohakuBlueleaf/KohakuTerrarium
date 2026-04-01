import { ZIndexType } from "../../../utils/typescript.js";
import "../../../utils/index.js";
import { AffixProps } from "./affix.js";
import * as vue from "vue";

//#region ../../packages/components/affix/src/affix.vue.d.ts
declare var __VLS_7: {};
type __VLS_Slots = {} & {
  default?: (props: typeof __VLS_7) => any;
};
declare const __VLS_base: vue.DefineComponent<AffixProps, {
  /** @description update affix status */update: () => void; /** @description update rootRect info */
  updateRoot: () => Promise<void>;
}, {}, {}, {}, vue.ComponentOptionsMixin, vue.ComponentOptionsMixin, {
  scroll: (args_0: {
    scrollTop: number;
    fixed: boolean;
  }) => void;
  change: (fixed: boolean) => void;
}, string, vue.PublicProps, Readonly<AffixProps> & Readonly<{
  onChange?: ((fixed: boolean) => any) | undefined;
  onScroll?: ((args_0: {
    scrollTop: number;
    fixed: boolean;
  }) => any) | undefined;
}>, {
  zIndex: ZIndexType;
  offset: number;
  appendTo: string | HTMLElement;
  position: "top" | "bottom";
  target: string;
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