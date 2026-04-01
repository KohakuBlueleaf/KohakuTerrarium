import { Color } from "../../color-picker-panel/src/utils/color.js";
import { ColorPickerProps } from "./color-picker.js";
import * as vue from "vue";

//#region ../../packages/components/color-picker/src/color-picker.vue.d.ts
declare function show(): void;
declare function hide(): void;
declare function focus(): void;
declare function blur(): void;
declare const __VLS_export: vue.DefineComponent<ColorPickerProps, {
  /**
   * @description current color object
   */
  color: Color;
  /**
   * @description manually show ColorPicker
   */
  show: typeof show;
  /**
   * @description manually hide ColorPicker
   */
  hide: typeof hide;
  /**
   * @description focus the input element
   */
  focus: typeof focus;
  /**
   * @description blur the input element
   */
  blur: typeof blur;
}, {}, {}, {}, vue.ComponentOptionsMixin, vue.ComponentOptionsMixin, {
  blur: (evt: FocusEvent) => void;
  focus: (evt: FocusEvent) => void;
  clear: () => void;
  "update:modelValue": (val: string | null) => void;
  change: (val: string | null) => void;
  activeChange: (val: string | null) => void;
}, string, vue.PublicProps, Readonly<ColorPickerProps> & Readonly<{
  onBlur?: ((evt: FocusEvent) => any) | undefined;
  onChange?: ((val: string | null) => any) | undefined;
  onFocus?: ((evt: FocusEvent) => any) | undefined;
  onClear?: (() => any) | undefined;
  "onUpdate:modelValue"?: ((val: string | null) => any) | undefined;
  onActiveChange?: ((val: string | null) => any) | undefined;
}>, {
  disabled: boolean;
  clearable: boolean;
  popperStyle: string | false | vue.CSSProperties | vue.StyleValue[] | null;
  teleported: boolean;
  validateEvent: boolean;
  persistent: boolean;
  modelValue: string | null;
  valueOnClear: string | number | boolean | Function | null;
  tabindex: string | number;
}, {}, {}, {}, string, vue.ComponentProvideOptions, false, {}, any>;
declare const _default: typeof __VLS_export;
//#endregion
export { _default };