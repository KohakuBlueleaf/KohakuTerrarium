import { IconPropType } from "../../../utils/vue/icon.js";
import "../../../utils/index.js";
import { InputModelModifiers, InputType } from "../../input/src/input.js";
import { InputInstance } from "../../input/src/instance.js";
import "../../input/index.js";
import { TooltipInstance } from "../../tooltip/src/tooltip.js";
import "../../tooltip/index.js";
import { MentionOption } from "./types.js";
import { filterOption } from "./helper.js";
import { MentionOptionProps, MentionProps } from "./mention.js";
import * as vue from "vue";
import { CSSProperties } from "vue";
import * as _popperjs_core0 from "@popperjs/core";

//#region ../../packages/components/mention/src/mention.vue.d.ts
declare var __VLS_15: string, __VLS_16: any, __VLS_41: string, __VLS_42: any;
type __VLS_Slots = {} & { [K in NonNullable<typeof __VLS_15>]?: (props: typeof __VLS_16) => any } & { [K in NonNullable<typeof __VLS_41>]?: (props: typeof __VLS_42) => any };
declare const __VLS_base: vue.DefineComponent<MentionProps, {
  input: vue.Ref<InputInstance | undefined, InputInstance | undefined>;
  tooltip: vue.Ref<TooltipInstance | undefined, TooltipInstance | undefined>;
  dropdownVisible: vue.ComputedRef<boolean>;
}, {}, {}, {}, vue.ComponentOptionsMixin, vue.ComponentOptionsMixin, {
  blur: (evt: FocusEvent) => void;
  focus: (evt: FocusEvent) => void;
  input: (value: string) => void;
  select: (option: MentionOption, prefix: string) => void;
  "update:modelValue": (value: string) => void;
  search: (pattern: string, prefix: string) => void;
  "whole-remove": (pattern: string, prefix: string) => void;
}, string, vue.PublicProps, Readonly<MentionProps> & Readonly<{
  onBlur?: ((evt: FocusEvent) => any) | undefined;
  onFocus?: ((evt: FocusEvent) => any) | undefined;
  onInput?: ((value: string) => any) | undefined;
  onSelect?: ((option: MentionOption, prefix: string) => any) | undefined;
  "onUpdate:modelValue"?: ((value: string) => any) | undefined;
  onSearch?: ((pattern: string, prefix: string) => any) | undefined;
  "onWhole-remove"?: ((pattern: string, prefix: string) => any) | undefined;
}>, {
  type: InputType;
  props: MentionOptionProps;
  disabled: boolean;
  clearIcon: IconPropType;
  placement: "bottom" | "top";
  validateEvent: boolean;
  modelValue: string;
  options: MentionOption[];
  offset: number;
  popperOptions: Partial<_popperjs_core0.Options>;
  split: string;
  modelModifiers: InputModelModifiers;
  autocomplete: string;
  wordLimitPosition: "inside" | "outside";
  tabindex: string | number;
  inputStyle: string | false | CSSProperties | vue.StyleValue[] | null;
  rows: number;
  prefix: string | string[];
  filterOption: false | typeof filterOption;
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