import { PopperEffect } from "../../popper/src/popper.js";
import { ElTooltipContentProps } from "./content.js";
import { PopperContentInstance } from "../../popper/src/content.js";
import { Options, Placement } from "../../popper/index.js";
import * as vue from "vue";

//#region ../../packages/components/tooltip/src/content.vue.d.ts
declare var __VLS_32: {};
type __VLS_Slots = {} & {
  default?: (props: typeof __VLS_32) => any;
};
declare const __VLS_base: vue.DefineComponent<ElTooltipContentProps, {
  /**
   * @description el-popper-content component instance
   */
  contentRef: vue.Ref<PopperContentInstance | undefined, PopperContentInstance | undefined>;
  /**
   * @description validate current focus event is trigger inside el-popper-content
   */
  isFocusInsideContent: (event?: FocusEvent) => boolean | undefined;
}, {}, {}, {}, vue.ComponentOptionsMixin, vue.ComponentOptionsMixin, {}, string, vue.PublicProps, Readonly<ElTooltipContentProps> & Readonly<{}>, {
  effect: PopperEffect;
  placement: Placement;
  popperStyle: string | false | vue.CSSProperties | vue.StyleValue[] | null;
  teleported: boolean;
  visible: boolean | null;
  style: string | false | vue.CSSProperties | vue.StyleValue[] | null;
  enterable: boolean;
  pure: boolean;
  focusOnShow: boolean;
  trapping: boolean;
  stopPopperMouseEvent: boolean;
  virtualTriggering: boolean;
  loop: boolean;
  boundariesPadding: number;
  gpuAcceleration: boolean;
  offset: number;
  popperOptions: Partial<Options>;
  strategy: "absolute" | "fixed";
  arrowOffset: number;
  content: string;
  showAfter: number;
  hideAfter: number;
  autoClose: number;
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