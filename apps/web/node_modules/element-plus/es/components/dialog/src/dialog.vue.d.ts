import { DialogProps, DialogTransition } from "./dialog.js";
import * as vue from "vue";

//#region ../../packages/components/dialog/src/dialog.vue.d.ts
declare var __VLS_42: {
    close: () => void;
    titleId: string;
    titleClass: string;
  }, __VLS_44: {}, __VLS_46: {}, __VLS_49: {};
type __VLS_Slots = {} & {
  header?: (props: typeof __VLS_42) => any;
} & {
  title?: (props: typeof __VLS_44) => any;
} & {
  default?: (props: typeof __VLS_46) => any;
} & {
  footer?: (props: typeof __VLS_49) => any;
};
declare const __VLS_base: vue.DefineComponent<DialogProps, {
  /** @description whether the dialog is visible */visible: vue.Ref<boolean, boolean>;
  dialogContentRef: vue.Ref<any, any>;
  resetPosition: () => void;
  handleClose: () => void;
}, {}, {}, {}, vue.ComponentOptionsMixin, vue.ComponentOptionsMixin, {
  close: () => void;
  "update:modelValue": (value: boolean) => void;
  open: () => void;
  opened: () => void;
  closed: () => void;
  openAutoFocus: () => void;
  closeAutoFocus: () => void;
}, string, vue.PublicProps, Readonly<DialogProps> & Readonly<{
  onClose?: (() => any) | undefined;
  "onUpdate:modelValue"?: ((value: boolean) => any) | undefined;
  onOpen?: (() => any) | undefined;
  onOpened?: (() => any) | undefined;
  onClosed?: (() => any) | undefined;
  onOpenAutoFocus?: (() => any) | undefined;
  onCloseAutoFocus?: (() => any) | undefined;
}>, {
  title: string;
  appendTo: string | HTMLElement;
  transition: DialogTransition;
  overflow: boolean;
  draggable: boolean;
  alignCenter: boolean;
  showClose: boolean;
  closeOnPressEscape: boolean;
  closeOnClickModal: boolean;
  lockScroll: boolean;
  modal: boolean;
  openDelay: number;
  closeDelay: number;
  headerAriaLevel: string;
  ariaLevel: string;
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