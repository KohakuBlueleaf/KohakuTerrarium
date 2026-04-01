import { IconPropType } from "../../../utils/vue/icon.js";
import "../../../utils/index.js";
import { InputModelModifiers, InputType } from "../../input/src/input.js";
import { InputInstance } from "../../input/src/instance.js";
import "../../input/index.js";
import { TooltipInstance } from "../../tooltip/src/tooltip.js";
import "../../tooltip/index.js";
import { AutocompleteData, AutocompleteFetchSuggestions, AutocompletePlacement, AutocompleteProps } from "./autocomplete.js";
import * as vue from "vue";
import { StyleValue } from "vue";

//#region ../../packages/components/autocomplete/src/autocomplete.vue.d.ts
declare var __VLS_29: {}, __VLS_32: {}, __VLS_35: {}, __VLS_38: {}, __VLS_41: {}, __VLS_49: {}, __VLS_62: {
    item: Record<string, any>;
  }, __VLS_64: {};
type __VLS_Slots = {} & {
  prepend?: (props: typeof __VLS_29) => any;
} & {
  append?: (props: typeof __VLS_32) => any;
} & {
  prefix?: (props: typeof __VLS_35) => any;
} & {
  suffix?: (props: typeof __VLS_38) => any;
} & {
  header?: (props: typeof __VLS_41) => any;
} & {
  loading?: (props: typeof __VLS_49) => any;
} & {
  default?: (props: typeof __VLS_62) => any;
} & {
  footer?: (props: typeof __VLS_64) => any;
};
declare const __VLS_base: vue.DefineComponent<AutocompleteProps, {
  /** @description the index of the currently highlighted item */highlightedIndex: vue.Ref<number, number>; /** @description autocomplete whether activated */
  activated: vue.Ref<boolean, boolean>; /** @description remote search loading status */
  loading: vue.Ref<boolean, boolean>; /** @description el-input component instance */
  inputRef: vue.Ref<InputInstance | undefined, InputInstance | undefined>; /** @description el-tooltip component instance */
  popperRef: vue.Ref<TooltipInstance | undefined, TooltipInstance | undefined>; /** @description fetch suggestions result */
  suggestions: vue.Ref<Record<string, any>[], Record<string, any>[] | AutocompleteData>; /** @description triggers when a suggestion is clicked */
  handleSelect: (item: any) => Promise<void>; /** @description handle keyboard enter event */
  handleKeyEnter: () => Promise<void>; /** @description focus the input element */
  focus: () => void; /** @description blur the input element */
  blur: () => void; /** @description close suggestion */
  close: () => void; /** @description highlight an item in a suggestion */
  highlight: (index: number) => void; /** @description loading suggestion list */
  getData: (queryString: string) => Promise<void>;
}, {}, {}, {}, vue.ComponentOptionsMixin, vue.ComponentOptionsMixin, {
  blur: (evt: FocusEvent) => void;
  focus: (evt: FocusEvent) => void;
  select: (item: Record<string, any>) => void;
  clear: () => void;
  "update:modelValue": (value: string | number) => void;
  change: (value: string | number) => void;
  input: (value: string | number) => void;
}, string, vue.PublicProps, Readonly<AutocompleteProps> & Readonly<{
  onBlur?: ((evt: FocusEvent) => any) | undefined;
  onChange?: ((value: string | number) => any) | undefined;
  onFocus?: ((evt: FocusEvent) => any) | undefined;
  onInput?: ((value: string | number) => any) | undefined;
  onSelect?: ((item: Record<string, any>) => any) | undefined;
  onClear?: (() => any) | undefined;
  "onUpdate:modelValue"?: ((value: string | number) => any) | undefined;
}>, {
  type: InputType;
  disabled: boolean;
  clearIcon: IconPropType;
  debounce: number;
  placement: AutocompletePlacement;
  teleported: boolean;
  validateEvent: boolean;
  modelValue: string | number;
  modelModifiers: InputModelModifiers;
  autocomplete: string;
  wordLimitPosition: "inside" | "outside";
  tabindex: string | number;
  inputStyle: string | false | vue.CSSProperties | StyleValue[] | null;
  rows: number;
  valueKey: string;
  fetchSuggestions: AutocompleteFetchSuggestions;
  triggerOnFocus: boolean;
  loopNavigation: boolean;
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